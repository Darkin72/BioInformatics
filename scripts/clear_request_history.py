from __future__ import annotations

import argparse
import json
import os
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


DEFAULT_API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")
DEFAULT_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
DEFAULT_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Clear request, prediction, timeline, and metric history via the admin API.",
    )
    parser.add_argument("--api-base-url", default=DEFAULT_API_BASE_URL)
    parser.add_argument("--username", default=DEFAULT_USERNAME)
    parser.add_argument("--password", default=DEFAULT_PASSWORD)
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Confirm deletion without an interactive prompt.",
    )
    return parser.parse_args()


def request_json(
    method: str,
    url: str,
    payload: dict | None = None,
    token: str | None = None,
) -> dict:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = Request(url, data=data, method=method)
    request.add_header("Accept", "application/json")
    if payload is not None:
        request.add_header("Content-Type", "application/json")
    if token:
        request.add_header("Authorization", f"Bearer {token}")

    with urlopen(request, timeout=60) as response:
        body = response.read().decode("utf-8")
        return json.loads(body) if body else {}


def login(api_base_url: str, username: str, password: str) -> str:
    response = request_json(
        "POST",
        f"{api_base_url.rstrip('/')}/api/auth/login",
        {"username": username, "password": password},
    )
    token = response.get("access_token")
    if not isinstance(token, str) or not token:
        raise RuntimeError("Admin login did not return an access token.")
    return token


def main() -> int:
    args = parse_args()
    if not args.yes:
        answer = input(
            "This will truncate request/prediction/metric history. Type DELETE to continue: "
        )
        if answer != "DELETE":
            print("Canceled.")
            return 1

    try:
        token = login(args.api_base_url, args.username, args.password)
        result = request_json(
            "DELETE",
            f"{args.api_base_url.rstrip('/')}/api/admin/request-history",
            token=token,
        )
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        print(f"HTTP {exc.code}: {detail}", file=sys.stderr)
        return 1
    except (OSError, URLError, RuntimeError) as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

