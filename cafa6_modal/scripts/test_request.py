import argparse
import json

import requests


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("url", help="Modal cafa6-predict URL")
    parser.add_argument("--top-k", type=int, default=20)
    parser.add_argument(
        "--sequence",
        default="MTEYKLVVVGAGGVGKSALTIQLIQNHFVDEYDPTIEDSYRKQV",
    )
    args = parser.parse_args()

    payload = {
        "records": [{"id": "example_protein_1", "sequence": args.sequence}],
        "top_k": args.top_k,
    }
    response = requests.post(args.url, json=payload, timeout=900)
    response.raise_for_status()
    print(json.dumps(response.json(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

