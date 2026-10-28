"""Parcel list, polling and archive handling for Irabelle Parcels."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta, timezone
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .api import ParcelsApiError, TrackingApi
from .const import (
    AUTO_DETECT,
    DOMAIN,
    EVENT_NEW_EVENT,
    FINAL_STATES,
    SIGNAL_PARCELS_UPDATED,
)

_LOGGER = logging.getLogger(__name__)

META_KEY = "_meta"


def normalize_tracking(value: Any) -> str | None:
    """Uppercase and validate a tracking number the way the mobile app does."""
    tracking = str(value or "").strip()
    if not tracking or tracking.startswith("_") or "{{" in tracking or "}}" in tracking:
        return None
    if tracking.lower() in ("unknown", "unavailable", "none"):
        return None
    if not (tracking.startswith("http") or tracking.endswith("RRMA")):
        tracking = tracking.upper()
    if len(tracking) < 5:
        return None
    return tracking


def duration_seconds(value: Any) -> int:
    """Interpret a stored duration in seconds.

    The value is a duration dict from the config-flow selector. The selector
    only exposes days/hours/minutes, but the frontend can leak a spurious
    'seconds' component from the pre-filled default (e.g. 604800 = 7 days
    next to days: 2) — those extra units must be ignored, otherwise the
    effective threshold becomes days+7d. A plain-seconds number is also
    accepted for legacy stored values.
    """
    if isinstance(value, dict):
        try:
            return int(
                timedelta(
                    days=int(value.get("days", 0)),
                    hours=int(value.get("hours", 0)),
                    minutes=int(value.get("minutes", 0)),
                ).total_seconds()
            )
        except (TypeError, ValueError):
            return 0
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def normalize_duration(value: dict[str, Any]) -> dict[str, int]:
    """Normalize a duration dict to days/hours/minutes only (selector units)."""
    units = {}
    for unit in ("days", "hours", "minutes"):
        try:
            units[unit] = int(value.get(unit, 0))
        except (TypeError, ValueError):
            units[unit] = 0
    return {k: v for k, v in units.items() if v}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def unique_id_for(tracking: str) -> str:
    """Return the sensor unique_id of a parcel."""
    return f"{DOMAIN}_{tracking}"


class ParcelManager:
    """Owns the parcel list: storage, polling, archive and change signals.

    Stored layout (one dict keyed by tracking number, plus `_meta`):
        {"_meta": {"fingerprint": {...}},
         "<tracking>": {"name", "carrier", "data", "added_at",
                        "archived", "archived_at", "delivered_at"}}
    Archived parcels keep their last tracking data but are not polled and
    have no sensor.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        api: TrackingApi,
        store: Store,
        parcels: dict[str, dict[str, Any]],
        meta: dict[str, Any],
        auto_archive_after: int,
        update_interval: timedelta,
    ) -> None:
        self.hass = hass
        self.entry = entry
        self.api = api
        self.store = store
        self.parcels = parcels
        self.meta = meta
        self.auto_archive_after = auto_archive_after
        # Set by the sensor platform: adds/removes the sensor of a parcel.
        self.add_sensor_cb: Callable[[str], None] | None = None
        self.coordinator = DataUpdateCoordinator[dict[str, dict[str, Any]]](
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_method=self._async_update,
            update_interval=update_interval,
        )
        self.coordinator.async_add_listener(self._notify)

    # -- queries -----------------------------------------------------------

    def active(self) -> list[str]:
        """Tracking numbers that are polled and have a sensor."""
        return [t for t, p in self.parcels.items() if not p.get("archived")]

    def get(self, tracking: str) -> dict[str, Any]:
        """Return a stored parcel or raise a user-facing error."""
        parcel = self.parcels.get(tracking)
        if parcel is None:
            raise ServiceValidationError(f"Parcel {tracking} is not being tracked")
        return parcel

    def parcel_data(self, tracking: str) -> dict[str, Any]:
        """Latest tracking data of a parcel (empty until the first poll)."""
        parcel = self.parcels.get(tracking) or {}
        data = dict(parcel.get("data") or {})
        data["name"] = parcel.get("name") or tracking
        data["tracking_number"] = tracking
        data["carrier_requested"] = parcel.get("carrier", AUTO_DETECT)
        return data

    @callback
    def as_list(self) -> list[dict[str, Any]]:
        """All parcels (active and archived) for the frontend cards."""
        registry = er.async_get(self.hass)
        result = []
        for tracking, parcel in self.parcels.items():
            data = self.parcel_data(tracking)
            data.pop("raw_error", None)
            data.update(
                {
                    "state": data.get("state") or "pending",
                    "archived": bool(parcel.get("archived")),
                    "archived_at": parcel.get("archived_at"),
                    "added_at": parcel.get("added_at"),
                    "delivered_at": parcel.get("delivered_at"),
                    "entity_id": None
                    if parcel.get("archived")
                    else registry.async_get_entity_id(
                        Platform.SENSOR, DOMAIN, unique_id_for(tracking)
                    ),
                }
            )
            result.append(data)
        return result

    # -- mutations ---------------------------------------------------------

    async def async_add(self, tracking_number: str, name: str | None, carrier: str | None) -> str:
        """Start tracking a parcel. Re-adding an archived parcel restores it."""
        tracking = normalize_tracking(tracking_number)
        if tracking is None:
            raise ServiceValidationError(
                f"Invalid tracking number: {tracking_number!r}"
            )
        name = str(name or "").strip()
        carrier = str(carrier or "").strip() or AUTO_DETECT
        existing = self.parcels.get(tracking)
        if existing is not None:
            if not existing.get("archived"):
                raise HomeAssistantError(f"Parcel {tracking} is already being tracked")
            if name:
                existing["name"] = name
            await self.async_unarchive(tracking)
            return tracking
        self.parcels[tracking] = {
            "name": name or tracking,
            "carrier": carrier,
            "data": None,
            "added_at": _now().isoformat(),
            "archived": False,
        }
        await self._async_save()
        self._add_sensor(tracking)
        await self.coordinator.async_request_refresh()
        return tracking

    async def async_update(
        self, tracking: str, name: str | None = None, carrier: str | None = None
    ) -> None:
        """Rename a parcel and/or change its carrier."""
        parcel = self.get(tracking)
        if name is not None and name.strip():
            parcel["name"] = name.strip()
        if carrier is not None and carrier.strip():
            parcel["carrier"] = carrier.strip()
        await self._async_save()
        if carrier is not None and not parcel.get("archived"):
            await self.coordinator.async_request_refresh()
        else:
            self.coordinator.async_update_listeners()

    async def async_remove(self, tracking: str) -> None:
        """Forget a parcel completely (active or archived)."""
        self.get(tracking)
        self.parcels.pop(tracking)
        self._remove_sensor(tracking)
        await self._async_save()
        self._notify()

    async def async_archive(self, tracking: str) -> None:
        """Stop polling a parcel and move it to the archive."""
        parcel = self.get(tracking)
        if parcel.get("archived"):
            return
        self._archive(tracking, parcel)
        await self._async_save()
        self._notify()

    async def async_unarchive(self, tracking: str) -> None:
        """Move an archived parcel back to the active list and poll it."""
        parcel = self.get(tracking)
        if not parcel.get("archived"):
            return
        parcel["archived"] = False
        parcel["archived_at"] = None
        # Restart the auto-archive clock, otherwise a delivered parcel would
        # be archived again on the next poll.
        parcel["delivered_at"] = None
        await self._async_save()
        self._add_sensor(tracking)
        await self.coordinator.async_request_refresh()
        self._notify()

    async def async_clear_archive(self) -> int:
        """Delete every archived parcel. Returns how many were deleted."""
        archived = [t for t, p in self.parcels.items() if p.get("archived")]
        for tracking in archived:
            self.parcels.pop(tracking)
        await self._async_save()
        self._notify()
        return len(archived)

    # -- internals ---------------------------------------------------------

    def _archive(self, tracking: str, parcel: dict[str, Any]) -> None:
        parcel["archived"] = True
        parcel["archived_at"] = _now().isoformat()
        self._remove_sensor(tracking)

    def _add_sensor(self, tracking: str) -> None:
        if self.add_sensor_cb is not None:
            self.add_sensor_cb(tracking)

    def _remove_sensor(self, tracking: str) -> None:
        registry = er.async_get(self.hass)
        entity_id = registry.async_get_entity_id(
            Platform.SENSOR, DOMAIN, unique_id_for(tracking)
        )
        if entity_id:
            registry.async_remove(entity_id)

    @callback
    def _notify(self) -> None:
        async_dispatcher_send(self.hass, SIGNAL_PARCELS_UPDATED)

    async def _async_save(self) -> None:
        await self.store.async_save({META_KEY: self.meta, **self.parcels})

    async def _async_update(self) -> dict[str, dict[str, Any]]:
        """Poll every active parcel; archive delivered ones when due."""
        results: dict[str, dict[str, Any]] = {}
        active = self.active()
        for tracking in active:
            parcel = self.parcels.get(tracking)
            if parcel is None or parcel.get("archived"):
                # Removed or archived while this poll was running.
                continue
            previous = parcel.get("data")
            name = parcel.get("name") or tracking
            try:
                payload = await self.api.track(
                    tracking,
                    name,
                    carrier=parcel.get("carrier", AUTO_DETECT),
                    parcel_count=len(active),
                )
                data = self.api.parse(payload, name)
            except ParcelsApiError as err:
                _LOGGER.warning("Failed to track %s: %s", tracking, err)
                data = previous or {
                    "state": "error",
                    "status_text": f"Update failed: {err}",
                    "carrier": None,
                    "statuses": [],
                }
                data["raw_error"] = str(err)
            parcel["data"] = data

            if data.get("state") in FINAL_STATES:
                parcel["delivered_at"] = parcel.get("delivered_at") or _now().isoformat()
            else:
                parcel["delivered_at"] = None

            delivered_at = _parse_time(parcel.get("delivered_at"))
            if (
                self.auto_archive_after
                and delivered_at
                and (_now() - delivered_at).total_seconds() > self.auto_archive_after
            ):
                _LOGGER.info("Archiving delivered parcel %s (%s)", tracking, name)
                self._archive(tracking, parcel)
                continue

            results[tracking] = data

            if (
                previous
                and previous.get("last_update")
                and previous.get("last_update") != data.get("last_update")
            ):
                self.hass.bus.async_fire(
                    EVENT_NEW_EVENT,
                    {
                        "tracking_number": tracking,
                        "name": name,
                        "carrier": data.get("carrier"),
                        "carrier_slug": data.get("carrier_slug"),
                        "status_text": data.get("status_text"),
                        "last_update": data.get("last_update"),
                        "state": data.get("state"),
                    },
                )
                _LOGGER.info(
                    "New event for %s (%s): %s",
                    tracking,
                    data.get("carrier"),
                    data.get("status_text"),
                )
        await self._async_save()
        return results
