#!/usr/bin/env python3
"""Poll Snabbit instant availability for a saved address."""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import date, datetime
from typing import Any

from snabbit_api import (
    DEFAULT_TOKEN_FILE,
    SnabbitClient,
    SnabbitHTTPError,
    build_now_payload,
    env_value,
    find_saved_address,
    load_token,
    summarize_availability,
    token_customer_id,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Poll Snabbit instant availability.")
    parser.add_argument("--address-id", default=env_value("SNABBIT_ADDRESS_ID"), help="Saved Snabbit address ID")
    parser.add_argument("--service-id", default=env_value("SNABBIT_SERVICE_ID", "1"), help="Snabbit service ID; 1 is House Help")
    parser.add_argument("--interval", type=float, default=float(env_value("SNABBIT_INTERVAL_SECONDS", "60") or "60"))
    parser.add_argument("--once", action="store_true", help="Run one check and exit")
    parser.add_argument("--print-json", action="store_true", help="Print the full API response")
    return parser.parse_args()


def build_payload(client: SnabbitClient, address_id: str, service_id: str) -> dict[str, Any]:
    customer_id = token_customer_id(client.token)
    if not customer_id:
        raise RuntimeError("Could not determine customer_id from the saved token")

    address = find_saved_address(client.customer_profile(), address_id)
    today = date.today().isoformat()
    return build_now_payload(
        address_id=address.id,
        service_id=service_id,
        customer_id=customer_id,
        lat=address.lat,
        lng=address.lng,
        start_date=today,
        end_date=today,
    )


def print_check(data: Any, print_json: bool) -> None:
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {summarize_availability(data)}", flush=True)
    if print_json:
        print(json.dumps(data, indent=2, sort_keys=True), flush=True)


def run() -> int:
    args = parse_args()
    token = env_value("SNABBIT_TOKEN") or load_token()
    if not token:
        print(f"Missing token. Run snabbit_login_check.py with --save-token to create {DEFAULT_TOKEN_FILE}.", file=sys.stderr)
        return 2
    if not args.address_id:
        print("Missing address ID. Run ./snabbit_list_addresses.py and pass --address-id.", file=sys.stderr)
        return 2

    client = SnabbitClient(token=token)
    payload = build_payload(client, args.address_id, args.service_id)

    while True:
        try:
            print_check(client.now_availability(payload), args.print_json)
        except SnabbitHTTPError as exc:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            print(f"[{timestamp}] HTTP {exc.status}: {exc.body}", flush=True)
            if args.once:
                return 1
        except Exception as exc:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            print(f"[{timestamp}] ERROR: {exc}", flush=True)
            if args.once:
                return 1

        if args.once:
            return 0
        time.sleep(args.interval)


if __name__ == "__main__":
    raise SystemExit(run())
