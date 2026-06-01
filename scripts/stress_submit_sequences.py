from __future__ import annotations

import argparse
import json
import math
import os
import random
import sys
import time
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, TextIO
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

try:
    from tqdm import tqdm
except ImportError:  # pragma: no cover - optional runtime dependency
    tqdm = None


DEFAULT_API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8001")
SEQUENCE_EXTENSIONS = {".fa", ".faa", ".fasta", ".fna", ".txt"}
API_MAX_RECORDS_PER_REQUEST = 400


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
            "Stress test Serving API by submitting many protein sequences with bounded concurrency. "
            "Designed for long-running big-volume experiments."
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
    parser.add_argument("--username", default=None, help="Operator username.")
    parser.add_argument("--password", default=None, help="Operator password.")
    parser.add_argument(
        "--workers",
        type=int,
        default=4,
        help="Number of concurrent worker threads.",
    )
    parser.add_argument(
        "--max-inflight",
        type=int,
        default=0,
        help=(
            "Maximum in-flight futures. 0 means auto (workers * 4). "
            "Set this to keep memory bounded in large runs."
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
        default=1,
        help=(
            "Number of sequence records included in each HTTP request payload "
            "under `records`."
        ),
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


def submit_batch(
    api_base_url: str,
    token: str,
    batch: RequestBatch,
    timeout: float,
) -> SubmitResult:
    label = request_label_from_batch(batch)
    payload_records = [
        {
            "id": record.protein_id,
            "sequence": record.sequence,
        }
        for record in batch.records
    ]
    started = time.perf_counter()
    try:
        response = request_json(
            "POST",
            f"{api_base_url.rstrip('/')}/api/inference-requests",
            {
                "records": payload_records,
                "source": "stress_file",
                "metadata": {
                    "record_count": len(batch.records),
                    "request_index": batch.request_index,
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
        )


def write_result_line(output: TextIO, result: SubmitResult) -> None:
    output.write(json.dumps(asdict(result), ensure_ascii=False) + "\n")


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


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
    print(f"- Latency avg: {latency['avg']:.2f} ms")
    print(f"- Latency p50 est: {latency['p50_est']:.2f} ms")
    print(f"- Latency p95 est: {latency['p95_est']:.2f} ms")
    print(f"- Latency p99 est: {latency['p99_est']:.2f} ms")
    print(f"- Latency min/max: {latency['min']:.2f}/{latency['max']:.2f} ms")
    print(
        "- Latency sample: "
        f"{latency['sample_size']} ({latency['sample_coverage']:.2%} of all requests)"
    )
    if summary["failed_examples"]:
        print("- First errors:")
        for item in summary["failed_examples"]:
            print(f"  {item['request_label']}: {item['error']}")


def validate_args(args: argparse.Namespace) -> int:
    if args.workers < 1:
        print("--workers must be >= 1", file=sys.stderr)
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
    if not args.dry_run and (not args.username or not args.password):
        print("--username and --password are required unless --dry-run is used.", file=sys.stderr)
        return 2
    return 0


def run_stress_test(
    args: argparse.Namespace,
    token: str,
    base_records: list[SequenceRecord],
    planned_total_requests: int,
    planned_total_sequences: int,
) -> dict:
    stats = BenchmarkStats(args.latency_sample_size)
    max_inflight = args.max_inflight if args.max_inflight > 0 else args.workers * 4
    max_inflight = max(max_inflight, args.workers)
    progress_bar = None
    use_tqdm = tqdm is not None and not args.no_tqdm

    if use_tqdm:
        progress_bar = tqdm(
            total=planned_total_requests,
            desc="Submitting requests",
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
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
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
                    submit_batch,
                    args.api_base_url,
                    token,
                    batch,
                    args.timeout,
                )
                inflight.add(future)
                future_context[future] = batch
                submitted += 1
                return True

            initial_inflight = min(max_inflight, planned_total_requests)
            for _ in range(initial_inflight):
                submit_next()

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
                            f"completed={stats.total}/{planned_total_requests} "
                            f"submitted={submitted}/{planned_total_requests} "
                            f"seq_completed={stats.total_sequences}/{planned_total_sequences} "
                            f"inflight={len(inflight)} "
                            f"stalled_for={stalled_for:.1f}s"
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
                            f"records={result.record_count})"
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

    max_inflight = args.max_inflight if args.max_inflight > 0 else args.workers * 4
    max_inflight = max(max_inflight, args.workers)

    print(f"Loaded {len(base_records)} base sequence records from {args.input_dir}.")
    print(f"Records per request: {args.records_per_request}.")
    print(f"Planned requests: {planned_total_requests}.")
    print(f"Planned sequences: {planned_total_sequences}.")
    print(f"Workers: {args.workers}, max in-flight futures: {max_inflight}.")
    heartbeat_text = (
        "disabled"
        if args.stall_report_seconds == 0
        else f"every {args.stall_report_seconds:.1f}s"
    )
    print(
        "Wait timeout / stall heartbeat: "
        f"{args.wait_timeout:.1f}s / {heartbeat_text}."
    )

    if args.dry_run:
        print("Dry run: no API calls will be made.")
        return 0

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
