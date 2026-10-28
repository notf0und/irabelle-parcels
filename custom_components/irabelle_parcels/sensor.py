"""Sensor platform for Irabelle Parcels: one sensor per active parcel."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import ParcelsConfigEntry
from .const import ICON_MAP
from .manager import ParcelManager, unique_id_for


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ParcelsConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Create a sensor for every active parcel, and for parcels added later."""
    manager = entry.runtime_data

    @callback
    def add_sensor(tracking: str) -> None:
        async_add_entities([ParcelSensor(manager, tracking)])

    manager.add_sensor_cb = add_sensor
    async_add_entities(ParcelSensor(manager, t) for t in manager.active())


class ParcelSensor(CoordinatorEntity, SensorEntity):
    """Sensor for a single tracked parcel."""

    _attr_has_entity_name = False
    # The event history is shown by the cards; keep it out of the database.
    _unrecorded_attributes = frozenset({"statuses", "related_tracking_ids"})

    def __init__(self, manager: ParcelManager, tracking_number: str) -> None:
        """Initialize the sensor."""
        super().__init__(manager.coordinator)
        self._manager = manager
        self._tracking = tracking_number
        self._attr_unique_id = unique_id_for(tracking_number)

    @property
    def _parcel(self) -> dict[str, Any]:
        return self._manager.parcel_data(self._tracking)

    @property
    def name(self) -> str:
        """Return the display name of the parcel."""
        return self._parcel["name"]

    @property
    def native_value(self) -> str | None:
        """Return the parcel status as sensor state."""
        return self._parcel.get("state")

    @property
    def icon(self) -> str:
        """Return an icon matching the parcel status."""
        return ICON_MAP.get(self._parcel.get("state"), ICON_MAP["unknown"])

    @property
    def extra_state_attributes(self) -> Mapping[str, Any]:
        """Return the tracking details."""
        data = self._parcel
        attrs: dict[str, Any] = {
            "tracking_number": self._tracking,
            "carrier": data.get("carrier"),
            "carrier_slug": data.get("carrier_slug"),
            "carrier_requested": data.get("carrier_requested"),
            "status_text": data.get("status_text"),
            "last_update": data.get("last_update"),
            "origin": data.get("origin"),
            "destination": data.get("destination"),
            "expected_delivery": data.get("expected_delivery"),
            "days_in_transit": data.get("days_in_transit"),
            "related_tracking_ids": data.get("related_tracking_ids"),
            "tracking_url": data.get("tracking_url"),
        }
        if data.get("statuses"):
            attrs["statuses"] = data["statuses"]
        return attrs
