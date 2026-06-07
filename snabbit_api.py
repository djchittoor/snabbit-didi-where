from __future__ import annotations

import base64
import json
import os
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Any
from urllib import error, parse, request


BASE_URL = "https://apis.maestroserve.com"
DEFAULT_TOKEN_FILE = ".snabbit_token"
NOW_AVAILABILITY_PATH = "/api/v2/schedules/now/availability"
OPENING_HOUR = 6


class SnabbitHTTPError(RuntimeError):
    def __init__(self, status: int, body: str) -> None:
        self.status = status
        self.body = body
        super().__init__(f"HTTP {status}: {body[:1000]}")


@dataclass
class SnabbitAPIErrorSummary:
    status: int
    code: str | None
    title: str | None
    message: str | None
    is_closed: bool = False

    @property
    def display_message(self) -> str:
        if self.is_closed:
            if self.message:
                return f"CLOSED: {self.message}"
            return "CLOSED: currently not serviceable"

        parts = [part for part in (self.title, self.message) if part]
        if parts:
            return f"ERROR: {' - '.join(parts)}"
        if self.code:
            return f"ERROR: {self.code}"
        return f"HTTP {self.status}"


@dataclass
class SavedAddress:
    id: str
    label: str
    lat: float
    lng: float
    text: str
    raw: dict[str, Any] = field(repr=False)


def env_value(name: str, default: str | None = None) -> str | None:
    value = os.environ.get(name)
    return default if value is None or value == "" else value


def load_token(path: str = DEFAULT_TOKEN_FILE) -> str | None:
    if not path or not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as token_file:
        token = token_file.read().strip()
    return token or None


def save_token(token: str, path: str = DEFAULT_TOKEN_FILE) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as token_file:
        token_file.write(token)
        token_file.write("\n")
    os.chmod(path, 0o600)


def decode_token_claims(token: str | None) -> dict[str, Any]:
    if not token or token.count(".") < 2:
        return {}

    payload = token.split(".", 2)[1]
    payload += "=" * (-len(payload) % 4)
    try:
        claims = json.loads(base64.urlsafe_b64decode(payload))
    except Exception:
        return {}
    return claims if isinstance(claims, dict) else {}


def token_customer_id(token: str | None) -> Any:
    return decode_token_claims(token).get("user_id")


def next_open_time(now: datetime | None = None) -> datetime:
    current = now or datetime.now()
    opens_at = datetime.combine(current.date(), time(hour=OPENING_HOUR))
    if current >= opens_at:
        opens_at += timedelta(days=1)
    return opens_at


def seconds_until_open(now: datetime | None = None) -> float:
    current = now or datetime.now()
    return max(0.0, (next_open_time(current) - current).total_seconds())


def parse_api_error(status: int, body: str) -> SnabbitAPIErrorSummary:
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return SnabbitAPIErrorSummary(status, None, None, body[:1000] or None)

    errors = payload.get("errors") if isinstance(payload, dict) else None
    first_error = errors[0] if isinstance(errors, list) and errors and isinstance(errors[0], dict) else {}
    code = first_error.get("code")
    title = first_error.get("title")
    message = first_error.get("message")
    return SnabbitAPIErrorSummary(
        status=status,
        code=str(code) if code is not None else None,
        title=str(title) if title is not None else None,
        message=str(message) if message is not None else None,
        is_closed=code == "TIMING_NOT_SERVICEABLE",
    )


def find_auth_token(value: Any) -> str | None:
    if isinstance(value, dict):
        for key, item in value.items():
            if key in {"access_token", "accessToken", "user_token", "token"} and isinstance(item, str) and item:
                return item
        for item in value.values():
            token = find_auth_token(item)
            if token:
                return token
    elif isinstance(value, list):
        for item in value:
            token = find_auth_token(item)
            if token:
                return token
    return None


def _headers(token: str | None = None, extra_headers: dict[str, str] | None = None) -> dict[str, str]:
    headers = {
        "accept": "application/json",
        "content-type": "application/json",
        "x-platform": "android",
        "x-version-code": "240",
        "x-android-version": "35",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if extra_headers:
        headers.update(extra_headers)
    return headers


@dataclass
class SnabbitClient:
    token: str | None = None
    base_url: str = BASE_URL
    timeout: float = 20

    def request_json(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        extra_headers: dict[str, str] | None = None,
        auth: bool = True,
    ) -> Any:
        url = path if path.startswith(("http://", "https://")) else f"{self.base_url.rstrip('/')}/{path.lstrip('/')}"
        method = method.upper()
        body = None

        if method == "GET" and payload:
            separator = "&" if "?" in url else "?"
            url = f"{url}{separator}{parse.urlencode(payload, doseq=True)}"
        elif payload is not None:
            body = json.dumps(payload).encode("utf-8")

        token = self.token if auth else None
        req = request.Request(url=url, data=body, headers=_headers(token, extra_headers), method=method)
        try:
            with request.urlopen(req, timeout=self.timeout) as response:
                response_body = response.read().decode("utf-8")
        except error.HTTPError as exc:
            response_body = exc.read().decode("utf-8", errors="replace")
            raise SnabbitHTTPError(exc.code, response_body) from exc

        if not response_body:
            return None
        try:
            return json.loads(response_body)
        except json.JSONDecodeError:
            return response_body

    def send_otp(self, phone: str, country_code: str = "+91", channel: str = "sms") -> Any:
        return self.request_json(
            "POST",
            "/api/v1/customers/login/send_otp",
            {"phone": phone, "country_code": country_code, "channel": channel},
            auth=False,
        )

    def verify_otp(self, phone: str, otp: str, country_code: str = "+91") -> Any:
        return self.request_json(
            "POST",
            "/api/v1/customers/login/verify_otp",
            {"phone": phone, "country_code": country_code, "otp": otp},
            auth=False,
        )

    def customer_profile(self) -> dict[str, Any]:
        profile = self.request_json("GET", "/api/v1/customers/me")
        if not isinstance(profile, dict):
            raise RuntimeError("Unexpected customer profile response")
        return profile

    def now_availability(self, payload: dict[str, Any], extra_headers: dict[str, str] | None = None) -> Any:
        return self.request_json("POST", NOW_AVAILABILITY_PATH, payload, extra_headers=extra_headers)


def _first_present(values: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if values.get(key) is not None:
            return values[key]
    return None


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_saved_address(address: dict[str, Any]) -> SavedAddress | None:
    address_id = _first_present(address, "id", "address_id", "addressId", "savedAddressId", "saved_address_id")
    lat = _first_present(address, "lat", "latitude")
    lng = _first_present(address, "lng", "longitude")

    location = address.get("location")
    if isinstance(location, dict):
        lat = lat if lat is not None else _first_present(location, "lat", "latitude")
        lng = lng if lng is not None else _first_present(location, "lng", "longitude")

    parsed_lat = _as_float(lat)
    parsed_lng = _as_float(lng)
    if address_id is None or parsed_lat is None or parsed_lng is None:
        return None

    label = _first_present(address, "tag", "address_tag", "label", "name", "type") or "saved address"
    text = _first_present(address, "geo_address", "address", "formatted_address", "address_line_1") or "(no address text)"
    return SavedAddress(str(address_id), str(label), parsed_lat, parsed_lng, " ".join(str(text).split()), address)


def saved_addresses(profile: dict[str, Any]) -> list[SavedAddress]:
    addresses = profile.get("addresses")
    if not isinstance(addresses, list):
        return []
    parsed = [parse_saved_address(address) for address in addresses if isinstance(address, dict)]
    return [address for address in parsed if address is not None]


def find_saved_address(profile: dict[str, Any], address_id: str) -> SavedAddress:
    for address in saved_addresses(profile):
        if address.id == str(address_id):
            return address
    raise RuntimeError(f"Saved address {address_id} was not found")


def build_now_payload(
    *,
    address_id: str,
    service_id: str,
    customer_id: Any,
    lat: float,
    lng: float,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict[str, Any]:
    today = date.today().isoformat()
    payload: dict[str, Any] = {
        "addressId": address_id,
        "service_id": service_id,
        "customer_id": customer_id,
        "location": {"lat": lat, "lng": lng},
        "date_range": [start_date or today, end_date or start_date or today],
    }
    return payload


def summarize_availability(data: Any) -> str:
    if isinstance(data, dict) and isinstance(data.get("durations"), list):
        available = [
            duration.get("duration_in_mins")
            for duration in data["durations"]
            if isinstance(duration, dict) and duration.get("is_available") is True
        ]
        if available:
            arrival = data.get("display_arrival_promise") or data.get("arrival_promise")
            suffix = f"; arrival {arrival}" if arrival else ""
            return f"AVAILABLE: {', '.join(str(duration) for duration in available)} min durations{suffix}"

        runners = data.get("all_runners")
        if isinstance(runners, list) and runners:
            statuses = Counter(runner.get("status", "UNKNOWN") for runner in runners if isinstance(runner, dict))
            if statuses.get("BUSY", 0) == len(runners):
                return f"UNAVAILABLE: {len(runners)}/{len(runners)} nearby runners busy"
            status_text = ", ".join(f"{status.lower()}={count}" for status, count in sorted(statuses.items()))
            return f"UNAVAILABLE: no instant durations available ({status_text})"
        return "UNAVAILABLE: no instant durations available"

    if isinstance(data, dict) and isinstance(data.get("slot_dates"), list):
        available_slots = 0
        for slot_date in data["slot_dates"]:
            if not isinstance(slot_date, dict):
                continue
            for preference in slot_date.get("preferences") or []:
                if not isinstance(preference, dict):
                    continue
                for duration in preference.get("durations") or []:
                    if not isinstance(duration, dict):
                        continue
                    if duration.get("is_available") is True:
                        available_slots += 1
                    for slot in duration.get("slots") or []:
                        if isinstance(slot, dict) and slot.get("is_available") is True:
                            available_slots += 1
        if available_slots:
            return f"AVAILABLE: {available_slots} scheduled slot options"
        return "UNAVAILABLE: no scheduled slots available"

    return "UNKNOWN: response did not match the known availability shapes"
