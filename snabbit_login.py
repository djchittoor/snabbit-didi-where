#!/usr/bin/env python3
"""Log in to Snabbit with an OTP and save the auth token."""

from __future__ import annotations

import argparse

from snabbit_api import DEFAULT_TOKEN_FILE, SnabbitClient, SnabbitHTTPError, find_auth_token, save_token


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Log in to Snabbit with an OTP and save the auth token.")
    parser.add_argument("--phone", required=True)
    parser.add_argument("--otp", required=True)
    return parser.parse_args()


def run() -> int:
    args = parse_args()
    client = SnabbitClient()

    try:
        response = client.verify_otp(args.phone, args.otp)
    except SnabbitHTTPError as exc:
        print(f"verify_otp failed: HTTP {exc.status}: {exc.body[:1000]}")
        return 1

    token = find_auth_token(response)
    if not token:
        print("verify_otp succeeded but no token was found in the response")
        return 1

    save_token(token)
    print(f"token saved to {DEFAULT_TOKEN_FILE} with 0600 permissions")

    return 0


if __name__ == "__main__":
    raise SystemExit(run())
