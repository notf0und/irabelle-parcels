"""Setup, actions, archive and migration."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import AsyncMock

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er

from custom_components.irabelle_parcels.const import DOMAIN

from .conftest import payload

TRACKING = "NZ123456789"


async def _setup(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


def _sensor(hass: HomeAssistant) -> str | None:
    return er.async_get(hass).async_get_entity_id("sensor", DOMAIN, f"{DOMAIN}_{TRACKING}")


async def _call(hass: HomeAssistant, service: str, **data: Any) -> Any:
    result = await hass.services.async_call(
        DOMAIN, service, data, blocking=True, return_response=service in ("add_parcel", "clear_archive")
    )
    await hass.async_block_till_done()
    return result


async def test_add_archive_restore_remove(
    hass: HomeAssistant, entry: MockConfigEntry, track: AsyncMock
) -> None:
    await _setup(hass, entry)
    manager = entry.runtime_data

    response = await _call(hass, "add_parcel", tracking_number=" nz123456789 ", name="Batteries")
    assert response == {"tracking_number": TRACKING}
    entity_id = _sensor(hass)
    state = hass.states.get(entity_id)
    assert state.state == "transit"
    assert state.name == "Batteries"
    assert state.attributes["tracking_number"] == TRACKING
    assert state.attributes["statuses"][0]["status"] == "Event 2"

    with pytest.raises(HomeAssistantError):
        await _call(hass, "add_parcel", tracking_number=TRACKING)

    await _call(hass, "archive_parcel", tracking_number=TRACKING)
    assert _sensor(hass) is None
    assert hass.states.get(entity_id) is None
    [parcel] = manager.as_list()
    assert parcel["archived"] is True
    assert parcel["entity_id"] is None
    assert parcel["statuses"], "the archive keeps the tracking history"

    # Archived parcels are not polled.
    track.reset_mock()
    await manager.coordinator.async_refresh()
    track.assert_not_called()

    await _call(hass, "unarchive_parcel", tracking_number=TRACKING)
    assert hass.states.get(_sensor(hass)).state == "transit"

    await _call(hass, "update_parcel", tracking_number=TRACKING, name="AA batteries")
    assert hass.states.get(_sensor(hass)).name == "AA batteries"

    await _call(hass, "remove_parcel", tracking_number=TRACKING)
    assert _sensor(hass) is None
    assert manager.as_list() == []


async def test_re_adding_an_archived_parcel_restores_it(
    hass: HomeAssistant, entry: MockConfigEntry, track: AsyncMock
) -> None:
    await _setup(hass, entry)
    await _call(hass, "add_parcel", tracking_number=TRACKING, name="Batteries")
    await _call(hass, "archive_parcel", tracking_number=TRACKING)
    await _call(hass, "add_parcel", tracking_number=TRACKING, name="Spare batteries")
    [parcel] = entry.runtime_data.as_list()
    assert parcel["archived"] is False
    assert parcel["name"] == "Spare batteries"


async def test_delivered_parcels_are_archived_after_the_delay(
    hass: HomeAssistant, entry: MockConfigEntry, track: AsyncMock
) -> None:
    track.return_value = payload("delivered")
    await _setup(hass, entry)
    manager = entry.runtime_data
    await _call(hass, "add_parcel", tracking_number=TRACKING)
    stored = manager.parcels[TRACKING]
    assert stored["delivered_at"] is not None
    assert not stored["archived"]

    stored["delivered_at"] = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
    await manager.coordinator.async_refresh()
    await hass.async_block_till_done()
    assert stored["archived"]
    assert _sensor(hass) is None


async def test_clear_archive(hass: HomeAssistant, entry: MockConfigEntry, track: AsyncMock) -> None:
    await _setup(hass, entry)
    await _call(hass, "add_parcel", tracking_number=TRACKING)
    await _call(hass, "add_parcel", tracking_number="NZ999999999")
    await _call(hass, "archive_parcel", tracking_number=TRACKING)
    assert await _call(hass, "clear_archive") == {"removed": 1}
    assert [p["tracking_number"] for p in entry.runtime_data.as_list()] == ["NZ999999999"]


async def test_websocket_subscription(
    hass: HomeAssistant, entry: MockConfigEntry, track: AsyncMock, hass_ws_client
) -> None:
    await _setup(hass, entry)
    client = await hass_ws_client(hass)
    await client.send_json_auto_id({"type": f"{DOMAIN}/subscribe"})
    assert (await client.receive_json())["success"]
    first = await client.receive_json()
    assert first["event"] == {"loaded": True, "parcels": []}

    await _call(hass, "add_parcel", tracking_number=TRACKING, name="Batteries")
    msg = await client.receive_json()
    while not msg["event"]["parcels"] or msg["event"]["parcels"][0]["state"] == "pending":
        msg = await client.receive_json()
    [parcel] = msg["event"]["parcels"]
    assert parcel["name"] == "Batteries"
    assert parcel["state"] == "transit"
    assert parcel["entity_id"] == _sensor(hass)
