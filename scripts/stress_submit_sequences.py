from __future__ import annotations

import argparse
import json
import math
import os
import random
import sys
import threading
import time
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable, TextIO
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import requests

try:
    from tqdm import tqdm
except ImportError:  # pragma: no cover - optional runtime dependency
    tqdm = None


DEFAULT_API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8001")
SEQUENCE_EXTENSIONS = {".fa", ".faa", ".fasta", ".fna", ".txt"}
API_MAX_RECORDS_PER_REQUEST = 400
DEFAULT_RECORDS_PER_REQUEST = 400
DEFAULT_STREAM_BATCH_SIZE = 400
MAX_STREAM_BATCH_SIZE = 400
TERMINAL_STATUSES = {"completed", "failed", "cancelled"}
DEFAULT_MODEL = "ensemble"
DEFAULT_TOP_K = 10
DEFAULT_THRESHOLD = 0.01
DEFAULT_COMPLETION_TIMEOUT_SECONDS = 1800.0


@dataclass(frozen=True)
class SequenceRecord:
    protein_id: str
    sequence: str
    source_file: str
    record_index: int


@dataclass(frozen=True)
class RequestBatch:
    request_index: int
    records: list[SequenceRecord]


@dataclass
class SubmitResult:
    request_label: str
    record_count: int
    request_id: str | None
    status: str
    latency_ms: float
    error: str | None
    submit_latency_ms: float | None = None
    poll_count: int = 0
    stage_name: str | None = None
    batch_count: int = 0
    prediction_count: int = 0


class LatencyReservoir:
    """Reservoir sampler for large runs to estimate percentiles."""

    def __init__(self, size: int) -> None:
        self._size = max(1, size)
        self._values: list[float] = []
        self._seen = 0
        self._rng = random.Random(42)

    @property
    def values(self) -> list[float]:
        return self._values

    @property
    def seen(self) -> int:
        return self._seen

    def add(self, value: float) -> None:
        self._seen += 1
        if len(self._values) < self._size:
            self._values.append(value)
            return

        replace_index = self._rng.randint(0, self._seen - 1)
        if replace_index < self._size:
            self._values[replace_index] = value


class BenchmarkStats:
    def __init__(self, latency_sample_size: int) -> None:
        self.total = 0
        self.total_sequences = 0
        self.failure_count = 0
        self.status_counts: dict[str, int] = {}
        self.latency_sum = 0.0
        self.latency_min = float("inf")
        self.latency_max = 0.0
        self.failed_examples: list[dict[str, str]] = []
        self.latencies = LatencyReservoir(latency_sample_size)

    def observe(self, result: SubmitResult) -> None:
        self.total += 1
        self.total_sequences += result.record_count
        self.status_counts[result.status] = self.status_counts.get(result.status, 0) + 1
        if result.error:
            self.failure_count += 1
            if len(self.failed_examples) < 5:
                self.failed_examples.append(
                    {
                        "request_label": result.request_label,
                        "error": result.error,
                    },
                )

        self.latency_sum += result.latency_ms
        self.latency_min = min(self.latency_min, result.latency_ms)
        self.latency_max = max(self.latency_max, result.latency_ms)
        self.latencies.add(result.latency_ms)

    @staticmethod
    def _percentile_from_sorted(sorted_values: list[float], ratio: float) -> float:
        if not sorted_values:
            return 0.0
        index = max(0, min(len(sorted_values) - 1, round((len(sorted_values) - 1) * ratio)))
        return sorted_values[index]

    def to_summary(
        self,
        planned_total_requests: int,
        planned_total_sequences: int,
        elapsed_seconds: float,
    ) -> dict:
        elapsed = max(elapsed_seconds, 0.001)
        sample = sorted(self.latencies.values)
        avg_latency = self.latency_sum / self.total if self.total else 0.0
        failure_rate = self.failure_count / self.total if self.total else 0.0
        throughput_requests = self.total / elapsed
        throughput_sequences = self.total_sequences / elapsed

        return {
            "planned_total_requests": planned_total_requests,
            "planned_total_sequences": planned_total_sequences,
            "completed_requests": self.total,
            "completed_sequences": self.total_sequences,
            "elapsed_seconds": elapsed,
            "throughput_rps": throughput_requests,
            "throughput_seq_per_sec": throughput_sequences,
            "failure_count": self.failure_count,
            "failure_rate": failure_rate,
            "status_counts": self.status_counts,
            "latency_ms": {
                "avg": avg_latency,
                "min": 0.0 if self.latency_min == float("inf") else self.latency_min,
                "p50_est": self._percentile_from_sorted(sample, 0.50),
                "p95_est": self._percentile_from_sorted(sample, 0.95),
                "p99_est": self._percentile_from_sorted(sample, 0.99),
                "max": self.latency_max,
                "sample_size": len(sample),
                "sample_coverage": len(sample) / self.latencies.seen if self.latencies.seen else 0.0,
            },
            "failed_examples": self.failed_examples,
        }

    def checkpoint(self, elapsed_seconds: float) -> dict:
        elapsed = max(elapsed_seconds, 0.001)
        return {
            "completed_requests": self.total,
            "completed_sequences": self.total_sequences,
            "elapsed_seconds": elapsed,
            "throughput_rps": self.total / elapsed,
            "throughput_seq_per_sec": self.total_sequences / elapsed,
            "failure_count": self.failure_count,
            "failure_rate": (self.failure_count / self.total) if self.total else 0.0,
            "status_counts": self.status_counts,
        }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Stress test Serving API by submitting protein sequences with N concurrent "
            "end-to-end requests. Each concurrency slot waits for completed/failed "
            "before submitting its next request."
        ),
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        required=True,
        help="Directory containing .fa/.fasta/.faa/.fna/.txt files.",
    )
    parser.add_argument(
        "--api-base-url",
        default=DEFAULT_API_BASE_URL,
        help=f"Serving API base URL. Default: {DEFAULT_API_BASE_URL}",
    )
    parser.add_argument(
        "--direct-sse-url",
        default=os.getenv("CAFA6_GRAPH_AWARE_PREDICT_SSE_URL", ""),
        help=(
            "Call the graph-aware Modal SSE endpoint directly instead of "
            "Serving API /api/inference-requests. Defaults to "
            "CAFA6_GRAPH_AWARE_PREDICT_SSE_URL if set."
        ),
    )
    parser.add_argument("--username", default=None, help="Operator username.")
    parser.add_argument("--password", default=None, help="Operator password.")
    parser.add_argument(
        "--concurrency",
        type=int,
        default=None,
        help="Number of end-to-end inference requests to keep running at the same time.",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=None,
        help="Deprecated alias for --concurrency.",
    )
    parser.add_argument(
        "--max-inflight",
        type=int,
        default=0,
        help=(
            "Maximum in-flight futures. 0 means exactly --concurrency. "
            "Values higher than --concurrency are ignored in completion-wait mode."
        ),
    )
    parser.add_argument(
        "--repeat",
        type=int,
        default=1,
        help="Repeat all loaded records this many times (ignored if --total-requests is set).",
    )
    parser.add_argument(
        "--total-requests",
        type=int,
        default=None,
        help=(
            "Total number of requests to send. If set, overrides --repeat and cycles loaded "
            "records until reaching this total."
        ),
    )
    parser.add_argument(
        "--records-per-request",
        type=int,
        default=DEFAULT_RECORDS_PER_REQUEST,
        help=(
            "Number of sequence records included in each HTTP request payload "
            "under `records`."
        ),
    )
    parser.add_argument(
        "--stream-batch-size",
        type=int,
        default=DEFAULT_STREAM_BATCH_SIZE,
        help=(
            "SSE stream batch size sent to the direct Modal endpoint. "
            f"Default: {DEFAULT_STREAM_BATCH_SIZE}; max: {MAX_STREAM_BATCH_SIZE}."
        ),
    )
    parser.add_argument(
        "--include-branch-predictions",
        action="store_true",
        help="Ask the direct SSE endpoint to include per-branch predictions.",
    )
    parser.add_argument(
        "--model",
        choices=["ensemble", "esm_mlp", "protcnn", "bilstm"],
        default=DEFAULT_MODEL,
        help=f"Inference model to request. Default: {DEFAULT_MODEL}.",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=DEFAULT_TOP_K,
        help=f"Top K terms to request. Default: {DEFAULT_TOP_K}.",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=DEFAULT_THRESHOLD,
        help=f"Prediction score threshold to request. Default: {DEFAULT_THRESHOLD}.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit number of base records loaded before repeat/cycling.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=1000.0,
        help="Timeout per HTTP request in seconds.",
    )
    parser.add_argument(
        "--login-timeout",
        type=float,
        default=30.0,
        help="Timeout for login request in seconds.",
    )
    parser.add_argument(
        "--login-retries",
        type=int,
        default=5,
        help="Retry attempts for login when timeout/network errors occur.",
    )
    parser.add_argument(
        "--login-retry-delay",
        type=float,
        default=2.0,
        help="Base delay (seconds) between login retries with exponential backoff.",
    )
    parser.add_argument(
        "--wait-timeout",
        type=float,
        default=1.0,
        help=(
            "Max seconds to wait for FIRST_COMPLETED before emitting heartbeat checks. "
            "Lower values make hangs visible sooner."
        ),
    )
    parser.add_argument(
        "--stall-report-seconds",
        type=float,
        default=30.0,
        help=(
            "Emit heartbeat if no request completes for this many seconds. "
            "0 disables heartbeat."
        ),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("stress-results.jsonl"),
        help="JSONL file for per-request details (if result logging is enabled).",
    )
    parser.add_argument(
        "--no-result-log",
        action="store_true",
        help="Disable per-request JSONL output to reduce disk usage in very large runs.",
    )
    parser.add_argument(
        "--summary-output",
        type=Path,
        default=None,
        help="Optional path to write final summary as JSON.",
    )
    parser.add_argument(
        "--checkpoint-output",
        type=Path,
        default=None,
        help="Optional JSONL file for periodic checkpoint snapshots.",
    )
    parser.add_argument(
        "--create-samples",
        type=int,
        default=0,
        help="Create N sample FASTA files inside --input-dir before running.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only read files and print the execution plan; do not call API.",
    )
    parser.add_argument(
        "--progress-every",
        type=int,
        default=0,
        help="Print per-request progress every N completed requests (0 disables).",
    )
    parser.add_argument(
        "--no-tqdm",
        action="store_true",
        help="Disable tqdm progress bar.",
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=5.0,
        help="Seconds between status polls while waiting for a submitted request to finish.",
    )
    parser.add_argument(
        "--completion-timeout",
        type=float,
        default=DEFAULT_COMPLETION_TIMEOUT_SECONDS,
        help=(
            "Maximum seconds to wait for one request to reach a terminal status. "
            f"Default: {DEFAULT_COMPLETION_TIMEOUT_SECONDS:.0f}. 0 means no limit."
        ),
    )
    parser.add_argument(
        "--no-start-gate",
        action="store_true",
        help=(
            "Disable the start gate that releases the first concurrency wave together. "
            "By default the first N requests start as close together as threads allow."
        ),
    )
    parser.add_argument(
        "--checkpoint-every",
        type=int,
        default=0,
        help="Print cumulative checkpoint every N completed requests (0 disables).",
    )
    parser.add_argument(
        "--latency-sample-size",
        type=int,
        default=200_000,
        help="Reservoir size for latency percentile estimation in large runs.",
    )
    return parser.parse_args()


def create_sample_files(input_dir: Path, count: int) -> None:
    input_dir.mkdir(parents=True, exist_ok=True)
    seeds = [
        "MTEYKLVVVGAGGVGKSALTIQLIQNHFVDEYDPTIEDSYRKQV",
        "MADQLTEEQIAEFKEAFSLFDKDGDGTITTKELGTVMRSLGQNPTEAEL",
        "MGSSHHHHHHSSGLVPRGSHMASMTGGQQMGRDLYDDDDKDRWGSM",
        "MVLSPADKTNVKAAWGKVGAHAGEYGAEALERMFLSFPTTKTYFPHF",
    ]

    for index in range(count):
        sequence = seeds[index % len(seeds)]
        output_path = input_dir / f"stress_sample_{index + 1:04d}.fasta"
        output_path.write_text(
            f">stress_sample_{index + 1:04d}\n{sequence}\n",
            encoding="utf-8",
        )


def iter_sequence_files(input_dir: Path) -> Iterable[Path]:
    for path in sorted(input_dir.rglob("*")):
        if path.is_file() and path.suffix.lower() in SEQUENCE_EXTENSIONS:
            yield path


def parse_sequence_file(path: Path) -> list[SequenceRecord]:
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return []

    if not text.startswith(">"):
        sequence = "".join(text.split()).upper()
        return [
            SequenceRecord(
                protein_id=path.stem,
                sequence=sequence,
                source_file=str(path),
                record_index=0,
            ),
        ]

    records: list[SequenceRecord] = []
    current_id: str | None = None
    current_lines: list[str] = []

    def flush() -> None:
        if current_id is None:
            return
        sequence = "".join(current_lines).replace(" ", "").upper()
        if sequence:
            records.append(
                SequenceRecord(
                    protein_id=current_id,
                    sequence=sequence,
                    source_file=str(path),
                    record_index=len(records),
                ),
            )

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith(">"):
            flush()
            current_id = line[1:].strip().split()[0] or path.stem
            current_lines = []
        else:
            current_lines.append(line)

    flush()
    return records


def load_base_records(input_dir: Path, limit: int | None) -> list[SequenceRecord]:
    records: list[SequenceRecord] = []
    for path in iter_sequence_files(input_dir):
        records.extend(parse_sequence_file(path))
        if limit is not None and len(records) >= limit:
            records = records[:limit]
            break
    return records


def iter_request_records(
    base_records: list[SequenceRecord],
    total_sequences: int,
) -> Iterable[SequenceRecord]:
    base_count = len(base_records)
    for index in range(total_sequences):
        base = base_records[index % base_count]
        round_index = (index // base_count) + 1
        protein_id = base.protein_id if round_index == 1 else f"{base.protein_id}__r{round_index}"
        yield SequenceRecord(
            protein_id=protein_id,
            sequence=base.sequence,
            source_file=base.source_file,
            record_index=base.record_index,
        )


def iter_request_batches(
    base_records: list[SequenceRecord],
    total_sequences: int,
    records_per_request: int,
) -> Iterable[RequestBatch]:
    request_index = 1
    sequence_iter = iter(iter_request_records(base_records, total_sequences))
    while True:
        request_records: list[SequenceRecord] = []
        for _ in range(records_per_request):
            try:
                request_records.append(next(sequence_iter))
            except StopIteration:
                break
        if not request_records:
            break
        yield RequestBatch(
            request_index=request_index,
            records=request_records,
        )
        request_index += 1


def request_json(
    method: str,
    url: str,
    payload: dict | None,
    token: str | None,
    timeout: float,
) -> dict:
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = Request(url, data=body, method=method)
    request.add_header("Accept", "application/json")
    if payload is not None:
        request.add_header("Content-Type", "application/json")
    if token:
        request.add_header("Authorization", f"Bearer {token}")

    with urlopen(request, timeout=timeout) as response:
        response_body = response.read().decode("utf-8")
        if not response_body:
            return {}
        try:
            return json.loads(response_body)
        except json.JSONDecodeError as error:
            compact = " ".join(response_body.split())
            if len(compact) > 400:
                compact = compact[:400] + "..."
            raise RuntimeError(f"Invalid JSON response from {url}: {compact}") from error


def login(api_base_url: str, username: str, password: str, timeout: float) -> str:
    url = f"{api_base_url.rstrip('/')}/api/auth/login"
    try:
        response = request_json(
            "POST",
            url,
            {"username": username, "password": password},
            token=None,
            timeout=timeout,
        )
    except HTTPError as error:
        try:
            detail = error.read().decode("utf-8", errors="replace")
        except Exception:
            detail = "<unable to decode error body>"
        detail = " ".join(detail.split())
        if len(detail) > 400:
            detail = detail[:400] + "..."
        message = f"HTTP {error.code}"
        if detail:
            message = f"{message}: {detail}"
        raise RuntimeError(f"Login failed at {url}: {message}") from error
    except (OSError, URLError) as error:
        raise RuntimeError(f"Login failed at {url}: {error}") from error
    except Exception as error:
        raise RuntimeError(f"Login failed at {url}: {type(error).__name__}: {error}") from error

    token = response.get("access_token")
    if not isinstance(token, str) or not token:
        raise RuntimeError("API did not return a valid access_token.")
    return token


def login_with_retry(
    api_base_url: str,
    username: str,
    password: str,
    timeout: float,
    retries: int,
    retry_delay: float,
) -> str:
    last_error: RuntimeError | None = None
    for attempt in range(1, retries + 1):
        try:
            return login(api_base_url, username, password, timeout)
        except RuntimeError as error:
            last_error = error
            if attempt >= retries:
                break
            sleep_seconds = retry_delay * (2 ** (attempt - 1))
            print(
                f"Login attempt {attempt}/{retries} failed: {error}. "
                f"Retrying in {sleep_seconds:.1f}s..."
            )
            if sleep_seconds > 0:
                time.sleep(sleep_seconds)
    raise RuntimeError(str(last_error) if last_error else "Login failed.")


def request_label_from_batch(batch: RequestBatch) -> str:
    if len(batch.records) == 1:
        return batch.records[0].protein_id
    return f"batch#{batch.request_index}:{len(batch.records)} records"


def iter_sse_events(response: requests.Response) -> Iterable[tuple[str, str]]:
    event_name = "message"
    data_lines: list[str] = []
    for raw_line in response.iter_lines(decode_unicode=True):
        if raw_line is None:
            continue
        line = raw_line.rstrip("\n")
        if line == "":
            if data_lines:
                yield event_name, "\n".join(data_lines)
            event_name = "message"
            data_lines = []
            continue
        if line.startswith("event:"):
            event_name = line.split(":", 1)[1].strip() or "message"
        elif line.startswith("data:"):
            data_lines.append(line.split(":", 1)[1].strip())

    if data_lines:
        yield event_name, "\n".join(data_lines)

def submit_direct_sse_batch(
    direct_sse_url: str,
    batch: RequestBatch,
    timeout: float,
    model: str,
    top_k: int,
    threshold: float,
    stream_batch_size: int,
    include_branch_predictions: bool,
    start_gate: threading.Event | None = None,
) -> SubmitResult:
    label = request_label_from_batch(batch)
    payload_records = [
        {"id": record.protein_id, "sequence": record.sequence}
        for record in batch.records
    ]
    payload = {
        "records": payload_records,
        "model": model,
        "top_k": top_k,
        "threshold": threshold,
        "stream_batch_size": stream_batch_size,
        "include_branch_predictions": include_branch_predictions,
    }
    if start_gate is not None:
        start_gate.wait()

    started = time.perf_counter()
    first_event_ms: float | None = None
    batch_count = 0
    streamed_record_count = 0
    prediction_count = 0
    status = "unknown"
    error: str | None = None
    try:
        with requests.post(
            direct_sse_url,
            json=payload,
            headers={"Accept": "text/event-stream"},
            stream=True,
            timeout=timeout,
        ) as response:
            response.raise_for_status()
            for event_name, raw_data in iter_sse_events(response):
                if first_event_ms is None:
                    first_event_ms = (time.perf_counter() - started) * 1000
                try:
                    data: dict[str, Any] = json.loads(raw_data)
                except json.JSONDecodeError:
                    data = {}

                if event_name == "batch":
                    batch_count += 1
                    records = data.get("records", [])
                    predictions = data.get("predictions", [])
                    if isinstance(records, list):
                        streamed_record_count += len(records)
                    if isinstance(predictions, list):
                        prediction_count += len(predictions)
                elif event_name == "error":
                    status = "modal_error"
                    error = str(data.get("message") or raw_data)
                elif event_name == "done":
                    status = "completed"

        if status == "unknown":
            status = "completed_without_done"
        if status == "completed" and streamed_record_count and streamed_record_count != len(batch.records):
            status = "record_count_mismatch"
            error = (
                f"SSE returned {streamed_record_count} records for "
                f"{len(batch.records)} submitted records."
            )
    except requests.HTTPError as exc:
        status = "http_error"
        error = str(exc)
    except requests.RequestException as exc:
        status = "request_error"
        error = str(exc)
    except Exception as exc:
        status = "unexpected_error"
        error = f"{exc.__class__.__name__}: {exc}"

    latency_ms = (time.perf_counter() - started) * 1000
    return SubmitResult(
        request_label=label,
        record_count=len(batch.records),
        request_id=None,
        status=status,
        latency_ms=latency_ms,
        error=error,
        submit_latency_ms=first_event_ms,
        poll_count=0,
        stage_name="direct_sse",
        batch_count=batch_count,
        prediction_count=prediction_count,
    )

def submit_batch(
    api_base_url: str,
    token: str,
    batch: RequestBatch,
    timeout: float,
    model: str,
    top_k: int,
    threshold: float,
    start_gate: threading.Event | None = None,
) -> SubmitResult:
    label = request_label_from_batch(batch)
    payload_records = [
        {
            "id": record.protein_id,
            "sequence": record.sequence,
        }
        for record in batch.records
    ]
    if start_gate is not None:
        start_gate.wait()
    started = time.perf_counter()
    try:
        response = request_json(
            "POST",
            f"{api_base_url.rstrip('/')}/api/inference-requests",
            {
                "records": payload_records,
                "source": "stress_file",
                "model": model,
                "top_k": top_k,
                "threshold": threshold,
                "metadata": {
                    "record_count": len(batch.records),
                    "request_index": batch.request_index,
                    "model": model,
                    "top_k": top_k,
                    "threshold": threshold,
                },
            },
            token=token,
            timeout=timeout,
        )
        latency_ms = (time.perf_counter() - started) * 1000
        return SubmitResult(
            request_label=label,
            record_count=len(batch.records),
            request_id=response.get("request_id"),
            status=str(response.get("current_status", "unknown")),
            latency_ms=latency_ms,
            error=None,
            submit_latency_ms=latency_ms,
            stage_name=(
                str(response.get("stage_name"))
                if response.get("stage_name") is not None
                else None
            ),
        )
    except HTTPError as error:
        latency_ms = (time.perf_counter() - started) * 1000
        try:
            detail = error.read().decode("utf-8", errors="replace")
        except Exception:
            detail = "<unable to decode error body>"
        detail = " ".join(detail.split())
        if len(detail) > 400:
            detail = detail[:400] + "..."
        message = f"HTTP {error.code}"
        if detail:
            message = f"{message}: {detail}"
        return SubmitResult(
            request_label=label,
            record_count=len(batch.records),
            request_id=None,
            status="http_error",
            latency_ms=latency_ms,
            error=message,
            submit_latency_ms=latency_ms,
        )
    except (OSError, URLError) as error:
        latency_ms = (time.perf_counter() - started) * 1000
        return SubmitResult(
            request_label=label,
            record_count=len(batch.records),
            request_id=None,
            status="network_error",
            latency_ms=latency_ms,
            error=str(error),
            submit_latency_ms=latency_ms,
        )
    except Exception as error:
        latency_ms = (time.perf_counter() - started) * 1000
        return SubmitResult(
            request_label=label,
            record_count=len(batch.records),
            request_id=None,
            status="unexpected_error",
            latency_ms=latency_ms,
            error=f"{type(error).__name__}: {error}",
            submit_latency_ms=latency_ms,
        )

def get_request_status(
    api_base_url: str,
    token: str,
    request_id: str,
    timeout: float,
) -> dict:
    return request_json(
        "GET",
        f"{api_base_url.rstrip('/')}/api/inference-requests/{request_id}",
        payload=None,
        token=token,
        timeout=timeout,
    )

def submit_and_wait_batch(
    api_base_url: str,
    token: str,
    batch: RequestBatch,
    timeout: float,
    model: str,
    top_k: int,
    threshold: float,
    poll_interval: float,
    completion_timeout: float,
    start_gate: threading.Event | None = None,
) -> SubmitResult:
    started = time.perf_counter()
    result = submit_batch(
        api_base_url=api_base_url,
        token=token,
        batch=batch,
        timeout=timeout,
        model=model,
        top_k=top_k,
        threshold=threshold,
        start_gate=start_gate,
    )
    submit_latency_ms = result.submit_latency_ms or result.latency_ms
    if result.error or not result.request_id:
        result.latency_ms = (time.perf_counter() - started) * 1000
        result.submit_latency_ms = submit_latency_ms
        return result

    status = result.status.lower()
    stage_name = result.stage_name
    poll_count = 0

    while status not in TERMINAL_STATUSES:
        elapsed = time.perf_counter() - started
        if completion_timeout > 0 and elapsed >= completion_timeout:
            return SubmitResult(
                request_label=result.request_label,
                record_count=result.record_count,
                request_id=result.request_id,
                status="completion_timeout",
                latency_ms=elapsed * 1000,
                error=(
                    f"Request did not reach a terminal status within "
                    f"{completion_timeout:.1f}s; last status={status}, stage={stage_name}"
                ),
                submit_latency_ms=submit_latency_ms,
                poll_count=poll_count,
                stage_name=stage_name,
            )

        sleep_seconds = poll_interval
        if completion_timeout > 0:
            sleep_seconds = min(sleep_seconds, max(0.0, completion_timeout - elapsed))
        if sleep_seconds > 0:
            time.sleep(sleep_seconds)

        try:
            payload = get_request_status(api_base_url, token, result.request_id, timeout)
        except HTTPError as error:
            latency_ms = (time.perf_counter() - started) * 1000
            return SubmitResult(
                request_label=result.request_label,
                record_count=result.record_count,
                request_id=result.request_id,
                status="status_http_error",
                latency_ms=latency_ms,
                error=f"HTTP {error.code} while polling request status",
                submit_latency_ms=submit_latency_ms,
                poll_count=poll_count,
                stage_name=stage_name,
            )
        except (OSError, URLError) as error:
            latency_ms = (time.perf_counter() - started) * 1000
            return SubmitResult(
                request_label=result.request_label,
                record_count=result.record_count,
                request_id=result.request_id,
                status="status_network_error",
                latency_ms=latency_ms,
                error=str(error),
                submit_latency_ms=submit_latency_ms,
                poll_count=poll_count,
                stage_name=stage_name,
            )

        poll_count += 1
        status = str(payload.get("current_status", "unknown")).lower()
        stage_name = (
            str(payload.get("stage_name"))
            if payload.get("stage_name") is not None
            else None
        )

    latency_ms = (time.perf_counter() - started) * 1000
    return SubmitResult(
        request_label=result.request_label,
        record_count=result.record_count,
        request_id=result.request_id,
        status=status,
        latency_ms=latency_ms,
        error=None if status == "completed" else f"Terminal status: {status}",
        submit_latency_ms=submit_latency_ms,
        poll_count=poll_count,
        stage_name=stage_name,
    )


def write_result_line(output: TextIO, result: SubmitResult) -> None:
    output.write(json.dumps(asdict(result), ensure_ascii=False) + "\n")


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

def effective_concurrency(args: argparse.Namespace) -> int:
    if args.concurrency is not None:
        return args.concurrency
    if args.workers is not None:
        return args.workers
    return 4


def print_summary(summary: dict) -> None:
    latency = summary["latency_ms"]
    print("Stress test summary")
    print(f"- Planned requests: {summary['planned_total_requests']}")
    print(f"- Planned sequences: {summary['planned_total_sequences']}")
    print(f"- Completed requests: {summary['completed_requests']}")
    print(f"- Completed sequences: {summary['completed_sequences']}")
    print(f"- Elapsed: {summary['elapsed_seconds']:.2f}s")
    print(f"- Throughput: {summary['throughput_rps']:.2f} request/s")
    print(f"- Throughput: {summary['throughput_seq_per_sec']:.2f} sequence/s")
    print(f"- Failure count: {summary['failure_count']}")
    print(f"- Failure rate: {summary['failure_rate']:.4%}")
    print(f"- Status counts: {json.dumps(summary['status_counts'], ensure_ascii=False)}")
    print(f"- End-to-end latency avg: {latency['avg']:.2f} ms")
    print(f"- End-to-end latency p50 est: {latency['p50_est']:.2f} ms")
    print(f"- End-to-end latency p95 est: {latency['p95_est']:.2f} ms")
    print(f"- End-to-end latency p99 est: {latency['p99_est']:.2f} ms")
    print(f"- End-to-end latency min/max: {latency['min']:.2f}/{latency['max']:.2f} ms")
    print(
        "- End-to-end latency sample: "
        f"{latency['sample_size']} ({latency['sample_coverage']:.2%} of all requests)"
    )
    if summary["failed_examples"]:
        print("- First errors:")
        for item in summary["failed_examples"]:
            print(f"  {item['request_label']}: {item['error']}")


def validate_args(args: argparse.Namespace) -> int:
    if args.concurrency is not None and args.concurrency < 1:
        print("--concurrency must be >= 1", file=sys.stderr)
        return 2
    if args.workers is not None and args.workers < 1:
        print("--workers must be >= 1", file=sys.stderr)
        return 2
    if (
        args.concurrency is not None
        and args.workers is not None
        and args.concurrency != args.workers
    ):
        print(
            "--concurrency and --workers were both set with different values; "
            "use only --concurrency to avoid ambiguity.",
            file=sys.stderr,
        )
        return 2
    if args.max_inflight < 0:
        print("--max-inflight must be >= 0", file=sys.stderr)
        return 2
    if args.repeat < 1:
        print("--repeat must be >= 1", file=sys.stderr)
        return 2
    if args.total_requests is not None and args.total_requests < 1:
        print("--total-requests must be >= 1", file=sys.stderr)
        return 2
    if args.records_per_request < 1:
        print("--records-per-request must be >= 1", file=sys.stderr)
        return 2
    if args.records_per_request > API_MAX_RECORDS_PER_REQUEST:
        print(
            f"--records-per-request must be <= {API_MAX_RECORDS_PER_REQUEST}",
            file=sys.stderr,
        )
        return 2
    if args.stream_batch_size < 1:
        print("--stream-batch-size must be >= 1", file=sys.stderr)
        return 2
    if args.stream_batch_size > MAX_STREAM_BATCH_SIZE:
        print(
            f"--stream-batch-size must be <= {MAX_STREAM_BATCH_SIZE}",
            file=sys.stderr,
        )
        return 2
    if args.limit is not None and args.limit < 1:
        print("--limit must be >= 1", file=sys.stderr)
        return 2
    if args.timeout <= 0:
        print("--timeout must be > 0", file=sys.stderr)
        return 2
    if args.login_timeout <= 0:
        print("--login-timeout must be > 0", file=sys.stderr)
        return 2
    if args.login_retries < 1:
        print("--login-retries must be >= 1", file=sys.stderr)
        return 2
    if args.login_retry_delay < 0:
        print("--login-retry-delay must be >= 0", file=sys.stderr)
        return 2
    if args.wait_timeout <= 0:
        print("--wait-timeout must be > 0", file=sys.stderr)
        return 2
    if args.poll_interval <= 0:
        print("--poll-interval must be > 0", file=sys.stderr)
        return 2
    if args.completion_timeout < 0:
        print("--completion-timeout must be >= 0", file=sys.stderr)
        return 2
    if args.top_k < 1:
        print("--top-k must be >= 1", file=sys.stderr)
        return 2
    if args.threshold < 0 or args.threshold > 1:
        print("--threshold must be between 0 and 1", file=sys.stderr)
        return 2
    if args.stall_report_seconds < 0:
        print("--stall-report-seconds must be >= 0", file=sys.stderr)
        return 2
    if args.progress_every < 0:
        print("--progress-every must be >= 0", file=sys.stderr)
        return 2
    if args.checkpoint_every < 0:
        print("--checkpoint-every must be >= 0", file=sys.stderr)
        return 2
    if args.latency_sample_size < 1:
        print("--latency-sample-size must be >= 1", file=sys.stderr)
        return 2
    if not args.direct_sse_url and not args.dry_run and (not args.username or not args.password):
        print("--username and --password are required unless --dry-run is used.", file=sys.stderr)
        return 2
    return 0


def run_stress_test(
    args: argparse.Namespace,
    token: str | None,
    base_records: list[SequenceRecord],
    planned_total_requests: int,
    planned_total_sequences: int,
) -> dict:
    stats = BenchmarkStats(args.latency_sample_size)
    concurrency = effective_concurrency(args)
    max_inflight = concurrency
    progress_bar = None
    use_tqdm = tqdm is not None and not args.no_tqdm
    start_gate = threading.Event() if not args.no_start_gate else None

    if use_tqdm:
        progress_bar = tqdm(
            total=planned_total_requests,
            desc=f"Completing ({concurrency} concurrent)",
            unit="req",
            dynamic_ncols=True,
        )
    elif not args.no_tqdm and tqdm is None:
        print("tqdm is not installed; falling back to plain progress logs.")

    def emit_line(message: str) -> None:
        if progress_bar is not None:
            progress_bar.write(message)
        else:
            print(message)

    output_file: TextIO | None = None
    checkpoint_file: TextIO | None = None
    if not args.no_result_log:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        output_file = args.output.open("w", encoding="utf-8")
    if args.checkpoint_output:
        args.checkpoint_output.parent.mkdir(parents=True, exist_ok=True)
        checkpoint_file = args.checkpoint_output.open("w", encoding="utf-8")

    started = time.perf_counter()
    last_completion_at = started
    last_heartbeat_at = started
    batch_iter = iter(
        iter_request_batches(
            base_records=base_records,
            total_sequences=planned_total_sequences,
            records_per_request=args.records_per_request,
        )
    )

    try:
        with ThreadPoolExecutor(max_workers=concurrency) as executor:
            inflight: set[Future[SubmitResult]] = set()
            future_context: dict[Future[SubmitResult], RequestBatch] = {}
            submitted = 0

            def submit_next() -> bool:
                nonlocal submitted
                if submitted >= planned_total_requests:
                    return False
                try:
                    batch = next(batch_iter)
                except StopIteration:
                    return False
                future = executor.submit(
                    submit_direct_sse_batch if args.direct_sse_url else submit_and_wait_batch,
                    **(
                        {
                            "direct_sse_url": args.direct_sse_url,
                            "batch": batch,
                            "timeout": args.timeout,
                            "model": args.model,
                            "top_k": args.top_k,
                            "threshold": args.threshold,
                            "stream_batch_size": args.stream_batch_size,
                            "include_branch_predictions": args.include_branch_predictions,
                            "start_gate": start_gate,
                        }
                        if args.direct_sse_url
                        else {
                            "api_base_url": args.api_base_url,
                            "token": token,
                            "batch": batch,
                            "timeout": args.timeout,
                            "model": args.model,
                            "top_k": args.top_k,
                            "threshold": args.threshold,
                            "poll_interval": args.poll_interval,
                            "completion_timeout": args.completion_timeout,
                            "start_gate": start_gate,
                        }
                    ),
                )
                inflight.add(future)
                future_context[future] = batch
                submitted += 1
                return True

            initial_inflight = min(max_inflight, planned_total_requests)
            for _ in range(initial_inflight):
                submit_next()
            if start_gate is not None:
                start_gate.set()

            while inflight:
                completed_futures, inflight = wait(
                    inflight,
                    timeout=args.wait_timeout,
                    return_when=FIRST_COMPLETED,
                )
                now = time.perf_counter()
                if not completed_futures:
                    if (
                        args.stall_report_seconds > 0
                        and now - last_heartbeat_at >= args.stall_report_seconds
                    ):
                        stalled_for = now - last_completion_at
                        emit_line(
                            "[heartbeat] "
                            f"terminal={stats.total}/{planned_total_requests} "
                            f"submitted={submitted}/{planned_total_requests} "
                            f"seq_completed={stats.total_sequences}/{planned_total_sequences} "
                            f"active={len(inflight)} "
                            f"no_terminal_for={stalled_for:.1f}s"
                        )
                        last_heartbeat_at = now
                    continue

                for future in completed_futures:
                    context_batch = future_context.pop(future, None)
                    try:
                        result = future.result()
                    except Exception as error:
                        request_label = (
                            request_label_from_batch(context_batch)
                            if context_batch
                            else "<unknown>"
                        )
                        record_count = len(context_batch.records) if context_batch else 0
                        result = SubmitResult(
                            request_label=request_label,
                            record_count=record_count,
                            request_id=None,
                            status="worker_exception",
                            latency_ms=0.0,
                            error=f"{type(error).__name__}: {error}",
                        )

                    stats.observe(result)
                    last_completion_at = now
                    last_heartbeat_at = now
                    if progress_bar is not None:
                        progress_bar.update(1)
                        if (
                            stats.total == planned_total_requests
                            or stats.total % 100 == 0
                            or result.error is not None
                        ):
                            elapsed = max(time.perf_counter() - started, 0.001)
                            progress_bar.set_postfix(
                                fail=stats.failure_count,
                                rps=f"{stats.total / elapsed:.1f}",
                            )

                    if output_file:
                        write_result_line(output_file, result)

                    completed = stats.total
                    if args.progress_every > 0 and (
                        completed == 1
                        or completed == planned_total_requests
                        or completed % args.progress_every == 0
                    ):
                        emit_line(
                            f"[{completed}/{planned_total_requests}] {result.request_label}: "
                            f"{result.status} ({result.latency_ms:.0f} ms, "
                            f"submit/first_event={result.submit_latency_ms or 0:.0f} ms, "
                            f"polls={result.poll_count}, records={result.record_count}, "
                            f"batches={result.batch_count}, preds={result.prediction_count}, "
                            f"stage={result.stage_name or '-'})"
                        )

                    if args.checkpoint_every > 0 and (
                        completed == planned_total_requests or completed % args.checkpoint_every == 0
                    ):
                        checkpoint = stats.checkpoint(time.perf_counter() - started)
                        emit_line(
                            "[checkpoint] "
                            f"completed={checkpoint['completed_requests']} "
                            f"throughput={checkpoint['throughput_rps']:.2f} req/s "
                            f"throughput_seq={checkpoint['throughput_seq_per_sec']:.2f} seq/s "
                            f"failure_rate={checkpoint['failure_rate']:.4%}"
                        )
                        if checkpoint_file:
                            checkpoint_file.write(json.dumps(checkpoint, ensure_ascii=False) + "\n")
                            checkpoint_file.flush()

                    while len(inflight) < max_inflight and submitted < planned_total_requests:
                        submit_next()

        elapsed_seconds = max(time.perf_counter() - started, 0.001)
        return stats.to_summary(
            planned_total_requests=planned_total_requests,
            planned_total_sequences=planned_total_sequences,
            elapsed_seconds=elapsed_seconds,
        )
    finally:
        if progress_bar is not None:
            progress_bar.close()
        if output_file:
            output_file.close()
        if checkpoint_file:
            checkpoint_file.close()


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    args = parse_args()
    validation_code = validate_args(args)
    if validation_code:
        return validation_code

    if args.create_samples:
        create_sample_files(args.input_dir, args.create_samples)

    base_records = load_base_records(args.input_dir, args.limit)
    if not base_records:
        print("No valid sequence records found.", file=sys.stderr)
        return 2

    if args.total_requests is not None:
        planned_total_requests = args.total_requests
        planned_total_sequences = args.total_requests * args.records_per_request
        if args.repeat != 1:
            print("Note: --total-requests is set, so --repeat is ignored.")
    else:
        planned_total_sequences = len(base_records) * args.repeat
        planned_total_requests = math.ceil(planned_total_sequences / args.records_per_request)

    concurrency = effective_concurrency(args)
    max_inflight = concurrency

    print(f"Loaded {len(base_records)} base sequence records from {args.input_dir}.")
    if args.direct_sse_url:
        print(f"Mode: direct Modal SSE ({args.direct_sse_url}).")
        print(f"Stream batch size: {args.stream_batch_size}.")
    else:
        print(f"Mode: Serving API ({args.api_base_url.rstrip('/')}/api/inference-requests).")
    print(f"Records per request: {args.records_per_request}.")
    print(f"Model / Top K / Threshold: {args.model} / {args.top_k} / {args.threshold}.")
    print(f"Planned requests: {planned_total_requests}.")
    print(f"Planned sequences: {planned_total_sequences}.")
    print(
        f"Concurrency: {concurrency} end-to-end request(s), "
        f"max active futures: {max_inflight}."
    )
    if args.max_inflight > concurrency:
        print("Note: --max-inflight is ignored above --concurrency in completion-wait mode.")
    if args.workers is not None:
        print("Note: --workers is deprecated; use --concurrency for new runs.")
    if not args.no_start_gate:
        print("Start gate: enabled for the first concurrency wave.")
    heartbeat_text = (
        "disabled"
        if args.stall_report_seconds == 0
        else f"every {args.stall_report_seconds:.1f}s"
    )
    print(
        "Wait timeout / stall heartbeat: "
        f"{args.wait_timeout:.1f}s / {heartbeat_text}."
    )
    completion_timeout_text = (
        "disabled"
        if args.completion_timeout == 0
        else f"{args.completion_timeout:.1f}s"
    )
    print(
        (
            "Direct SSE completion: waits for done/error event."
            if args.direct_sse_url
            else "Completion polling: "
            f"every {args.poll_interval:.1f}s, timeout {completion_timeout_text}."
        )
    )

    if args.dry_run:
        print("Dry run: no API calls will be made.")
        return 0

    token: str | None = None
    if not args.direct_sse_url:
        try:
            token = login_with_retry(
                args.api_base_url,
                args.username,
                args.password,
                args.login_timeout,
                args.login_retries,
                args.login_retry_delay,
            )
        except RuntimeError as error:
            print(str(error), file=sys.stderr)
            return 1
    summary = run_stress_test(
        args=args,
        token=token,
        base_records=base_records,
        planned_total_requests=planned_total_requests,
        planned_total_sequences=planned_total_sequences,
    )
    print_summary(summary)

    if not args.no_result_log:
        print(f"Per-request result log: {args.output}")
    else:
        print("Per-request result log: disabled (--no-result-log).")
    if args.checkpoint_output:
        print(f"Checkpoint log: {args.checkpoint_output}")
    if args.summary_output:
        write_json(args.summary_output, summary)
        print(f"Summary JSON: {args.summary_output}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
