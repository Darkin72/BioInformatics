import argparse
import json
import os
from pathlib import Path
import time

import requests


ENV_PATH = Path(__file__).resolve().parents[1] / ".env"


def load_env_file(path):
    if not path.exists():
        return
    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def post_json(url, payload, timeout):
    started = time.time()
    response = requests.post(url, json=payload, timeout=timeout)
    elapsed = time.time() - started
    response.raise_for_status()
    return response.json(), elapsed


def get_json(url, timeout):
    started = time.time()
    response = requests.get(url, timeout=timeout)
    elapsed = time.time() - started
    response.raise_for_status()
    return response.json(), elapsed


def main():
    load_env_file(ENV_PATH)
    parser = argparse.ArgumentParser(description="Call the deployed CAFA-6 Modal endpoint.")
    parser.add_argument(
        "--predict-url",
        default=os.environ.get("CAFA6_PREDICT_URL"),
    )
    parser.add_argument(
        "--health-url",
        default=os.environ.get("CAFA6_HEALTH_URL"),
    )
    parser.add_argument("--skip-health", action="store_true")
    parser.add_argument("--top-k", type=int, default=20)
    parser.add_argument("--timeout", type=int, default=900)
    parser.add_argument("--id", default="example_protein_1")
    parser.add_argument(
        "--sequence",
        action="append",
        default=None,
        help="Protein sequence. Can be repeated for multiple records.",
    )
    args = parser.parse_args()

    if not args.skip_health:
        health, elapsed = get_json(args.health_url, args.timeout)
        print(f"[health] {elapsed:.2f}s")
        print(json.dumps(health, ensure_ascii=False, indent=2))

    sequences = args.sequence or ["MTEYKLVVVGAGGVGKSALTIQLIQNHFVDEYDPTIEDSYRKQV"]
    records = [{"id": args.id, "sequence": sequences[0]}]
    for idx, sequence in enumerate(sequences[1:], start=2):
        records.append({"id": f"example_protein_{idx}", "sequence": sequence})

    payload = {
        "records": records,
        "top_k": args.top_k,
        "threshold": None,
        "include_branch_predictions": False,
    }
    result, elapsed = post_json(args.predict_url, payload, args.timeout)
    print(f"[predict] {elapsed:.2f}s")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
