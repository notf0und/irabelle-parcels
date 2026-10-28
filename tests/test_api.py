"""Response parsing."""

from __future__ import annotations

from custom_components.irabelle_parcels.api import TrackingApi

from .conftest import payload


def _api() -> TrackingApi:
    return TrackingApi(None, country="New Zealand")


def test_parse_transit() -> None:
    data = _api().parse(payload(), "Batteries")
    assert data["state"] == "transit"
    assert data["status_text"] == "Event 2"
    assert data["last_update"] == "2026-10-22T10:00:00Z"
    assert data["carrier"] == "NZ Post"
    assert data["expected_delivery"] == "2026-11-01T00:00:00Z"
    assert data["days_in_transit"] == 6
    assert data["tracking_url"] == "https://example.com/track"


def test_parse_maps_archive_to_delivered() -> None:
    assert _api().parse(payload("archive"), "x")["state"] == "delivered"
    assert _api().parse(payload("pickup"), "x")["state"] == "pickup"


def test_parse_no_data() -> None:
    assert _api().parse({"error": "NO_DATA"}, "x")["state"] == "no_data"
