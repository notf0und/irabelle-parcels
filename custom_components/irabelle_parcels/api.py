"""API client for the parcel tracking service.

The public tracking API used by a popular parcel tracking mobile app. No
authentication is required.

Request shape:
  POST {API_BASE}{tracking}/{carrier}/{locale}/{country}/{name}/{platform}
  body: [{"slug":"extra","data":{...}}, {"slug":"ahkref","data":[fingerprint..., hash]}]
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Any

import aiohttp

from .const import (
    API_BASE,
    APP_VERSION,
    AUTO_DETECT,
    DEFAULT_LOCALE,
    MAX_STATUSES,
    PLATFORM,
    SEED,
    STATUS_MAP,
    UA,
)

_LOGGER = logging.getLogger(__name__)


def hash_32_gc(text: str, seed: int) -> int:
    """MurmurHash-3-32 variant used by the app to fingerprint requests."""
    m = 0xFFFFFFFF
    length = len(text)
    u = (seed ^ length) & m
    c = 0
    s = length
    while s >= 4:
        o = (
            ord(text[c])
            | (ord(text[c + 1]) << 8)
            | (ord(text[c + 2]) << 16)
            | (ord(text[c + 3]) << 24)
        ) & m
        o = 1540483477 * (o & 0xFFFF) + (((1540483477 * (o >> 16)) & 0xFFFF) << 16)
        o = o & m
        acc = 1540483477 * (u & 0xFFFF) + (((1540483477 * (u >> 16)) & 0xFFFF) << 16)
        o = o ^ (o >> 24)
        o = 1540483477 * (o & 0xFFFF) + (((1540483477 * (o >> 16)) & 0xFFFF) << 16)
        u = ((acc & m) ^ o) & m
        s -= 4
        c += 4
    if s == 3:
        u = (u ^ (ord(text[c + 2]) << 16)) & m
    if s >= 2:
        u = (u ^ (ord(text[c + 1]) << 8)) & m
    if s >= 1:
        u = u ^ ord(text[c])
        u = 1540483477 * (u & 0xFFFF) + (((1540483477 * (u >> 16)) & 0xFFFF) << 16)
    u = (u & m) ^ ((u & m) >> 13)
    u = 1540483477 * (u & 0xFFFF) + (((1540483477 * (u >> 16)) & 0xFFFF) << 16)
    u = (u & m) ^ ((u & m) >> 15)
    return u & m


class ParcelsApiError(Exception):
    """Raised when the tracking API cannot be queried."""


class TrackingApi:
    """Client for the parcel tracking API."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        country: str,
        locale: str = DEFAULT_LOCALE,
        postal_code: str | None = None,
        fingerprint: dict[str, Any] | None = None,
    ) -> None:
        self._session = session
        self._country = country
        self._locale = locale
        self._postal_code = postal_code
        self._fp = self._make_fingerprint(fingerprint)

    @staticmethod
    def _make_fingerprint(override: dict[str, Any] | None) -> dict[str, Any]:
        """Build a well-formed device fingerprint.

        The tracking API requires an `ahkref` device fingerprint that
        looks like a real app install. Any well-formed fingerprint is accepted
        (a random 16-hex ANDROID_ID-like unique id, plausible device values and
        a correct request hash); no registration is needed. Users can override
        the generated values with their own app install's identity.
        """
        defaults = {
            "push": True,
            "subscribed": True,
            "installed_at": int(time.time() * 1000) - 200 * 86400 * 1000,
            "goods": 0,
            "app_opens": 50,
            "model": "Pixel 6",
            "device_id": "oriole",
            "unique_id": uuid.uuid4().hex[:16],
            "manufacturer": "Google",
            "installer": None,
            "version": APP_VERSION,
        }
        fp = {**defaults, **(override or {})}
        return fp

    def _fingerprint(self, tracking_number: str, parcel_count: int) -> list[Any]:
        data = [
            self._fp["push"],  # push enabled
            self._fp["subscribed"],  # subscribed
            self._fp["installed_at"],  # installedAt (ms)
            self._fp["goods"],  # goods
            self._fp["app_opens"],  # appOpens
            parcel_count,
            False,
            self._fp["model"],  # model
            self._fp["device_id"],  # deviceId
            self._fp["unique_id"],  # uniqueId
            self._fp["manufacturer"],  # manufacturer
            self._fp["installer"],  # installer
            self._fp["version"],  # app version
            tracking_number,
        ]
        serialized = json.dumps(data, separators=(",", ":"))
        data.append(hash_32_gc(serialized, SEED))
        return data

    def _body(self, tracking_number: str, parcel_count: int) -> list[dict[str, Any]]:
        trackers: list[dict[str, Any]] = []
        if self._postal_code:
            trackers.append({"slug": "extra", "data": {"defaultPostalCode": self._postal_code}})
        trackers.append(
            {"slug": "ahkref", "data": self._fingerprint(tracking_number, parcel_count)}
        )
        return trackers

    async def track(
        self,
        tracking_number: str,
        name: str,
        carrier: str = AUTO_DETECT,
        parcel_count: int = 1,
    ) -> dict[str, Any]:
        """Query tracking info for a parcel. Returns the raw API payload."""
        tracking_number = tracking_number.strip()
        if not (tracking_number.startswith("http") or tracking_number.endswith("RRMA")):
            tracking_number = tracking_number.upper()
        url = (
            f"{API_BASE}{tracking_number}/{carrier}/{self._locale}/"
            f"{self._country}/{name}/{PLATFORM}"
        )
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Accept-Encoding": "gzip",
            "User-Agent": UA,
        }
        body = self._body(tracking_number, parcel_count)
        try:
            async with self._session.post(
                url, headers=headers, data=json.dumps(body), timeout=aiohttp.ClientTimeout(total=60)
            ) as resp:
                payload = await resp.json(content_type=None)
        except (aiohttp.ClientError, TimeoutError, json.JSONDecodeError) as err:
            raise ParcelsApiError(f"Request failed: {err}") from err
        return payload

    def parse(self, payload: dict[str, Any], name: str) -> dict[str, Any]:
        """Normalize a raw API payload into sensor-ready data."""
        if isinstance(payload, dict) and payload.get("error"):
            error = payload["error"]
            if error == "NO_DATA":
                return {
                    "name": name,
                    "state": "no_data",
                    "status_text": "No tracking information available",
                    "last_update": None,
                    "carrier": None,
                    "carrier_slug": None,
                    "origin": None,
                    "destination": None,
                    "expected_delivery": None,
                    "statuses": [],
                    "tracking_url": None,
                    "raw_error": error,
                }
            raise ParcelsApiError(f"API error: {error}")

        states = payload.get("states") or []
        status = payload.get("status") or "unknown"
        sub_status = payload.get("sub_status")
        if sub_status in ("delivered", "cancelled", "returned"):
            status = sub_status
        status = STATUS_MAP.get(status, status)

        events = []
        for ev in states:
            events.append(
                {
                    "date": ev.get("date"),
                    "status": ev.get("status"),
                    "location": ev.get("location"),
                }
            )

        carriers = payload.get("carriers") or []
        carrier_index = payload.get("carrier")
        carrier = payload.get("detectedCarrier") or {}
        carrier_name = carrier.get("name")
        if not carrier_name and isinstance(carrier_index, int) and carrier_index < len(carriers):
            carrier_name = carriers[carrier_index]
        carrier_slug = carrier.get("slug")

        eta = payload.get("eta")
        expected = None
        eta_data = None
        if isinstance(eta, dict) and (eta.get("startDate") or eta.get("endDate")):
            eta_data = {
                "start": eta.get("startDate"),
                "end": eta.get("endDate"),
                "min_days": eta.get("minDays"),
                "max_days": eta.get("maxDays"),
            }
            expected = eta.get("endDate") or eta.get("startDate")

        last = events[0] if events else None
        status_text = last["status"] if last else status

        # "Days in transit" and related tracking ids — same as the app shows.
        days_in_transit = None
        for attr in payload.get("attributes") or []:
            if attr.get("l") == "days_transit":
                try:
                    days_in_transit = int(attr.get("val"))
                except (TypeError, ValueError):
                    days_in_transit = attr.get("val")
                break

        related = payload.get("next_tracking_ids") or []
        related_tracking_ids = [str(x) for x in related if x]

        return {
            "name": name,
            "state": status,
            "status_text": status_text,
            "last_update": last["date"] if last else None,
            "carrier": carrier_name,
            "carrier_slug": carrier_slug,
            "origin": payload.get("origin"),
            "destination": payload.get("destination"),
            "expected_delivery": expected,
            "eta": eta_data,
            "days_in_transit": days_in_transit,
            "related_tracking_ids": related_tracking_ids,
            "statuses": events[:MAX_STATUSES],
            "tracking_url": self._tracking_url(payload),
            "raw_error": None,
        }

    @staticmethod
    def _tracking_url(payload: dict[str, Any]) -> str | None:
        ext = payload.get("externalTracking") or []
        if ext:
            return ext[0].get("url")
        return None
