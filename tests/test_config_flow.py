"""Config and options flows."""

from __future__ import annotations

from unittest.mock import AsyncMock

from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.config_entries import SOURCE_USER
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.irabelle_parcels.const import DOMAIN


async def test_user_flow(hass: HomeAssistant, track: AsyncMock) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            "country": "New Zealand",
            "postal_code": "",
            "scan_interval": 1800,
            "auto_archive_after": {"days": 3, "hours": 0, "minutes": 0, "seconds": 604800},
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Irabelle Parcels"
    assert result["data"]["auto_archive_after"] == {"days": 3}
    assert "postal_code" not in result["data"]


async def test_options_add_and_remove(
    hass: HomeAssistant, entry: MockConfigEntry, track: AsyncMock
) -> None:
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.MENU
    result = await hass.config_entries.options.async_configure(result["flow_id"], {"next_step_id": "add_parcel"})
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"tracking_number": "x", "name": "", "carrier": "Auto Detect"}
    )
    assert result["errors"] == {"base": "invalid_tracking"}
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"tracking_number": "nz123456789", "name": "Batteries", "carrier": "Auto Detect"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert "NZ123456789" in entry.runtime_data.parcels

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(result["flow_id"], {"next_step_id": "remove_parcel"})
    result = await hass.config_entries.options.async_configure(result["flow_id"], {"tracking_number": "NZ123456789"})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.runtime_data.parcels == {}
