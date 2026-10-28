"""Shared fixtures."""

from __future__ import annotations

from collections.abc import Generator
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.irabelle_parcels.const import DOMAIN


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Load the integration from custom_components."""


def payload(status: str = "transit", events: int = 2) -> dict[str, Any]:
    """A tracking response shaped like the tracking API's."""
    return {
        "status": status,
        "states": [
            {"date": f"2026-10-2{i}T10:00:00Z", "status": f"Event {i}", "location": "Auckland"}
            for i in range(events, 0, -1)
        ],
        "carriers": ["NZ Post"],
        "carrier": 0,
        "detectedCarrier": {"slug": "nz-post", "name": "NZ Post"},
        "origin": "China",
        "destination": "New Zealand",
        "eta": {"startDate": "2026-10-30T00:00:00Z", "endDate": "2026-11-01T00:00:00Z"},
        "externalTracking": [{"url": "https://example.com/track"}],
        "attributes": [{"l": "days_transit", "val": "6"}],
    }


@pytest.fixture
def track() -> Generator[AsyncMock]:
    """Patch the tracking request; set `.return_value` to change the answer."""
    with patch(
        "custom_components.irabelle_parcels.api.TrackingApi.track",
        new=AsyncMock(return_value=payload()),
    ) as mock:
        yield mock


@pytest.fixture
def entry() -> MockConfigEntry:
    """A configured entry."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="Irabelle Parcels",
        data={"country": "New Zealand", "locale": "en", "scan_interval": 1800},
        options={"auto_archive_after": {"days": 2}},
    )
