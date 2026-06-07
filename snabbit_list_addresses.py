#!/usr/bin/env python3
"""List saved Snabbit addresses."""

from __future__ import annotations

import argparse
import shlex
import sys

from snabbit_api import DEFAULT_TOKEN_FILE, SnabbitClient, env_value, find_saved_address, load_token, saved_addresses


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="List saved Snabbit addresses.")
    parser.add_argument("--address-id", help="Only print this address")
    parser.add_argument("--shell", action="store_true", help="Print shell assignments for the selected or first address")
    return parser.parse_args()


def print_shell(address_id: str, lat: float, lng: float) -> None:
    print(f"SNABBIT_ADDRESS_ID={shlex.quote(address_id)}")
    print(f"SNABBIT_LATITUDE={shlex.quote(str(lat))}")
    print(f"SNABBIT_LONGITUDE={shlex.quote(str(lng))}")


def run() -> int:
    args = parse_args()
    token = env_value("SNABBIT_TOKEN") or load_token()
    if not token:
        print(f"Missing token. Run snabbit_login_check.py with --save-token to create {DEFAULT_TOKEN_FILE}.", file=sys.stderr)
        return 2

    profile = SnabbitClient(token=token).customer_profile()
    addresses = [find_saved_address(profile, args.address_id)] if args.address_id else saved_addresses(profile)

    if not addresses:
        print("No saved addresses with coordinates found.", file=sys.stderr)
        return 1

    if args.shell:
        address = addresses[0]
        print_shell(address.id, address.lat, address.lng)
        return 0

    for index, address in enumerate(addresses, start=1):
        print(f"{index}. id={address.id} label={address.label} lat={address.lat} lng={address.lng}")
        print(f"   {address.text}")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
