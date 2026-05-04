from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


DEFAULT_API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")
SEQUENCE_EXTENSIONS = {".fa", ".faa", ".fasta", ".fna", ".txt"}


@dataclass(frozen=True)
class SequenceRecord:
    protein_id: str
    sequence: str
    source_file: str
    record_index: int


@dataclass
class SubmitResult:
    protein_id: str
    source_file: str
    request_id: str | None
    status: str
    latency_ms: float
    error: str | None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Gá»­i Ä‘á»“ng thá»i nhiá»u file sequence vÃ o Serving API Ä‘á»ƒ stress test "
            "luá»“ng inference tháº­t."
        ),
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        required=True,
        help="ThÆ° má»¥c chá»©a file .fa, .fasta, .faa, .fna hoáº·c .txt.",
    )
    parser.add_argument(
        "--api-base-url",
        default=DEFAULT_API_BASE_URL,
        help=f"URL Serving API. Máº·c Ä‘á»‹nh: {DEFAULT_API_BASE_URL}",
    )
    parser.add_argument(
        "--username",
        default=None,
        help="Operator username.",
    )
    parser.add_argument(
        "--password",
        default=None,
        help="Operator password.",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=4,
        help="Sá»‘ request gá»­i Ä‘á»“ng thá»i.",
    )
    parser.add_argument(
        "--repeat",
        type=int,
        default=1,
        help="Sá»‘ láº§n láº·p láº¡i má»—i sequence.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Giá»›i háº¡n sá»‘ record Ä‘áº§u vÃ o trÆ°á»›c khi nhÃ¢n repeat.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=90.0,
        help="Timeout má»—i HTTP request, tÃ­nh báº±ng giÃ¢y.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("stress-results.jsonl"),
        help="File JSONL ghi káº¿t quáº£ tá»«ng request.",
    )
    parser.add_argument(
        "--create-samples",
        type=int,
        default=0,
        help="Táº¡o N file FASTA máº«u trong input-dir trÆ°á»›c khi cháº¡y.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Chá»‰ Ä‘á»c file vÃ  in káº¿ hoáº¡ch, khÃ´ng gá»i API.",
    )
    parser.add_argument(
        "--progress-every",
        type=int,
        default=1,
        help="Print progress after every N completed requests.",
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


def load_records(input_dir: Path, limit: int | None, repeat: int) -> list[SequenceRecord]:
    records: list[SequenceRecord] = []
    for path in iter_sequence_files(input_dir):
        records.extend(parse_sequence_file(path))

    if limit is not None:
        records = records[:limit]

    if repeat <= 1:
        return records

    repeated: list[SequenceRecord] = []
    for round_index in range(repeat):
        for record in records:
            repeated.append(
                SequenceRecord(
                    protein_id=f"{record.protein_id}__r{round_index + 1}",
                    sequence=record.sequence,
                    source_file=record.source_file,
                    record_index=record.record_index,
                ),
            )
    return repeated


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
        return json.loads(response_body) if response_body else {}


def login(api_base_url: str, username: str, password: str, timeout: float) -> str:
    response = request_json(
        "POST",
        f"{api_base_url.rstrip('/')}/api/auth/login",
        {"username": username, "password": password},
        token=None,
        timeout=timeout,
    )
    token = response.get("access_token")
    if not isinstance(token, str) or not token:
        raise RuntimeError("API khÃ´ng tráº£ vá» access_token há»£p lá»‡.")
    return token


def submit_record(
    api_base_url: str,
    token: str,
    record: SequenceRecord,
    timeout: float,
) -> SubmitResult:
    started = time.perf_counter()
    try:
        response = request_json(
            "POST",
            f"{api_base_url.rstrip('/')}/api/inference-requests",
            {
                "protein_id": record.protein_id,
                "sequence": record.sequence,
                "source": "stress_file",
                "metadata": {
                    "source_file": record.source_file,
                    "record_index": record.record_index,
                },
            },
            token=token,
            timeout=timeout,
        )
        latency_ms = (time.perf_counter() - started) * 1000
        return SubmitResult(
            protein_id=record.protein_id,
            source_file=record.source_file,
            request_id=response.get("request_id"),
            status=str(response.get("current_status", "unknown")),
            latency_ms=latency_ms,
            error=None,
        )
    except HTTPError as error:
        latency_ms = (time.perf_counter() - started) * 1000
        detail = error.read().decode("utf-8", errors="replace")
        return SubmitResult(
            protein_id=record.protein_id,
            source_file=record.source_file,
            request_id=None,
            status="http_error",
            latency_ms=latency_ms,
            error=f"HTTP {error.code}: {detail}",
        )
    except (OSError, URLError) as error:
        latency_ms = (time.perf_counter() - started) * 1000
        return SubmitResult(
            protein_id=record.protein_id,
            source_file=record.source_file,
            request_id=None,
            status="network_error",
            latency_ms=latency_ms,
            error=str(error),
        )


def percentile(values: list[float], ratio: float) -> float:
    if not values:
        return 0.0
    index = max(0, min(len(values) - 1, round((len(values) - 1) * ratio)))
    return sorted(values)[index]


def write_results(path: Path, results: list[SubmitResult]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as output:
        for result in results:
            output.write(json.dumps(asdict(result), ensure_ascii=False) + "\n")


def print_summary(results: list[SubmitResult], elapsed_seconds: float) -> None:
    latencies = [result.latency_ms for result in results]
    status_counts: dict[str, int] = {}
    for result in results:
        status_counts[result.status] = status_counts.get(result.status, 0) + 1

    print("Káº¿t quáº£ stress test")
    print(f"- Tá»•ng request: {len(results)}")
    print(f"- Thá»i gian: {elapsed_seconds:.2f}s")
    print(f"- Throughput: {len(results) / elapsed_seconds:.2f} request/s")
    print(f"- Tráº¡ng thÃ¡i: {json.dumps(status_counts, ensure_ascii=False)}")
    print(f"- Latency trung bÃ¬nh: {statistics.mean(latencies):.2f} ms")
    print(f"- Latency p50: {percentile(latencies, 0.50):.2f} ms")
    print(f"- Latency p95: {percentile(latencies, 0.95):.2f} ms")

    failed = [result for result in results if result.error]
    if failed:
        print("- Lá»—i Ä‘áº§u tiÃªn:")
        for result in failed[:5]:
            print(f"  {result.protein_id}: {result.error}")


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    args = parse_args()
    if args.workers < 1:
        print("--workers pháº£i >= 1", file=sys.stderr)
        return 2
    if args.repeat < 1:
        print("--repeat pháº£i >= 1", file=sys.stderr)
        return 2
    if not args.dry_run and (not args.username or not args.password):
        print("--username and --password are required unless --dry-run is used.", file=sys.stderr)
        return 2

    if args.create_samples:
        create_sample_files(args.input_dir, args.create_samples)

    records = load_records(args.input_dir, args.limit, args.repeat)
    if not records:
        print("KhÃ´ng tÃ¬m tháº¥y sequence há»£p lá»‡ Ä‘á»ƒ gá»­i.", file=sys.stderr)
        return 2

    print(f"ÄÃ£ Ä‘á»c {len(records)} sequence tá»« {args.input_dir}.")
    print(f"Sá»‘ worker Ä‘á»“ng thá»i: {args.workers}.")

    print(f"Total requests to send: {len(records)}.")

    if args.dry_run:
        print("Dry run: khÃ´ng gá»i API.")
        return 0

    token = login(args.api_base_url, args.username, args.password, args.timeout)
    started = time.perf_counter()
    results: list[SubmitResult] = []

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = [
            executor.submit(
                submit_record,
                args.api_base_url,
                token,
                record,
                args.timeout,
            )
            for record in records
        ]
        total = len(futures)
        for completed, future in enumerate(as_completed(futures), start=1):
            result = future.result()
            results.append(result)
            if args.progress_every > 0 and (
                completed == 1
                or completed == total
                or completed % args.progress_every == 0
            ):
                print(
                    f"[{completed}/{total}] {result.protein_id}: "
                    f"{result.status} ({result.latency_ms:.0f} ms)"
                )

    elapsed_seconds = max(time.perf_counter() - started, 0.001)
    write_results(args.output, results)
    print_summary(results, elapsed_seconds)
    print(f"ÄÃ£ ghi chi tiáº¿t vÃ o {args.output}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
