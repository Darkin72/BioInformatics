from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

import requests


DEFAULT_SEQUENCE = "MTEYKLVVVGAGGVGKSALTIQLIQNHFVDEYDPTIEDSYRKQV"
ENV_PATH = Path(__file__).resolve().parents[1] / ".env"
DEFAULT_URL_ENV = "CAFA6_GRAPH_AWARE_PREDICT_SSE_URL"


def load_env(path: Path = ENV_PATH):
    if not path.exists():
        return
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def iter_sse_lines(response):
    event = None
    data_lines = []
    for raw_line in response.iter_lines(decode_unicode=True):
        if raw_line is None:
            continue
        line = raw_line.rstrip("\n")
        if line == "":
            if event or data_lines:
                data = "\n".join(data_lines)
                yield event or "message", data
            event = None
            data_lines = []
            continue
        if line.startswith("event:"):
            event = line.split(":", 1)[1].strip()
        elif line.startswith("data:"):
            data_lines.append(line.split(":", 1)[1].strip())


def main():
    load_env()
    parser = argparse.ArgumentParser(
        description="Call a graph-aware CAFA-6 Modal SSE endpoint."
    )
    parser.add_argument(
        "--model",
        choices=["ensemble", "esm_mlp", "protcnn", "bilstm"],
        default="ensemble",
        help="Model branch to run inside the single SSE endpoint.",
    )
    parser.add_argument(
        "--url",
        default="",
        help="Streaming SSE predict URL. Defaults to CAFA6_GRAPH_AWARE_PREDICT_SSE_URL.",
    )
    parser.add_argument("--id", action="append", dest="ids", help="Protein ID. Repeatable.")
    parser.add_argument(
        "--sequence", action="append", dest="sequences", help="Protein sequence. Repeatable."
    )
    parser.add_argument("--top-k", type=int, default=20)
    parser.add_argument("--threshold", type=float, default=None)
    parser.add_argument("--stream-batch-size", type=int, default=2)
    parser.add_argument("--include-branch-predictions", action="store_true")
    parser.add_argument("--timeout", type=float, default=900)
    args = parser.parse_args()

    url = args.url or os.environ.get(DEFAULT_URL_ENV, "")
    if not url:
        raise SystemExit(
            "Missing --url or CAFA6_GRAPH_AWARE_PREDICT_SSE_URL in "
            "cafa6_graph_aware_modal_streaming/.env"
        )

    sequences = args.sequences or [DEFAULT_SEQUENCE]
    ids = args.ids or [f"protein_{i + 1}" for i in range(len(sequences))]
    if len(ids) < len(sequences):
        ids += [f"protein_{i + 1}" for i in range(len(ids), len(sequences))]

    payload = {
        "model": args.model,
        "records": [{"id": pid, "sequence": seq} for pid, seq in zip(ids, sequences)],
        "top_k": args.top_k,
        "threshold": args.threshold,
        "stream_batch_size": args.stream_batch_size,
        "include_branch_predictions": args.include_branch_predictions,
    }

    started_at = time.time()
    with requests.post(url, json=payload, stream=True, timeout=args.timeout) as response:
        response.raise_for_status()
        for event, data in iter_sse_lines(response):
            elapsed = time.time() - started_at
            try:
                obj = json.loads(data)
            except json.JSONDecodeError:
                obj = data
            if event == "progress":
                print(
                    f"[{elapsed:.2f}s] progress model={obj.get('model')} "
                    f"step={obj.get('step')} status={obj.get('status')} "
                    f"batch={obj.get('batch_index', '-')}/{obj.get('total_batches', '-')}"
                )
            elif event == "batch":
                print(
                    f"[{elapsed:.2f}s] model={args.model} batch {obj['batch_index'] + 1}/{obj['total_batches']} "
                    f"records={len(obj.get('records', []))} predictions={len(obj.get('predictions', []))}"
                )
                print(json.dumps(obj, ensure_ascii=False, indent=2)[:4000])
            else:
                print(f"[{elapsed:.2f}s] event={event} model={args.model}")
                print(json.dumps(obj, ensure_ascii=False, indent=2) if isinstance(obj, dict) else obj)


if __name__ == "__main__":
    main()
