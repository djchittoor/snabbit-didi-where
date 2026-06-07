#!/usr/bin/env python3
"""Verify a Snabbit OTP and save the auth token when requested."""

from __future__ import annotations

import argparse

from snabbit_api import DEFAULT_TOKEN_FILE, SnabbitClient, SnabbitHTTPError, find_auth_token, save_token


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify a Snabbit OTP.")
    parser.add_argument("--phone", required=True)
    parser.add_argument("--otp", required=True)
    parser.add_argument("--save-token", action="store_true", help=f"Save token to {DEFAULT_TOKEN_FILE}")
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

    print(f"token acquired: {token[:6]}...{token[-4:]} length={len(token)}")
    if args.save_token:
        save_token(token)
        print(f"token saved to {DEFAULT_TOKEN_FILE} with 0600 permissions")
    else:
        print("token was not saved; rerun with --save-token if you want the poller to use it")

    return 0


if __name__ == "__main__":
    raise SystemExit(run())
