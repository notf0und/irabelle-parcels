"""Irabelle Parcels: track packages from almost any carrier."""

from __future__ import annotations

from datetime import timedelta
import logging
from pathlib import Path
from typing import Any

import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME, Platform
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
    callback,
)
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.dispatcher import (
    async_dispatcher_connect,
    async_dispatcher_send,
)
from homeassistant.helpers.storage import Store
from homeassistant.helpers.typing import ConfigType
from homeassistant.loader import async_get_integration

from .api import TrackingApi
from .const import (
    CARD_FILE,
    CONF_AUTO_ARCHIVE,
    CONF_COUNTRY,
    CONF_FINGERPRINT,
    CONF_LOCALE,
    CONF_POSTAL_CODE,
    CONF_SCAN_INTERVAL,
    DEFAULT_AUTO_ARCHIVE,
    DEFAULT_COUNTRY,
    DEFAULT_LOCALE,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    FRONTEND_URL,
    SIGNAL_PARCELS_UPDATED,
)
from .manager import (
    META_KEY,
    ParcelManager,
    duration_seconds,
    normalize_tracking,
    unique_id_for,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR]
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

STORAGE_VERSION = 1

ATTR_TRACKING_NUMBER = "tracking_number"
ATTR_CARRIER = "carrier"

type ParcelsConfigEntry = ConfigEntry[ParcelManager]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the actions, the websocket API and the Lovelace cards."""
    _register_services(hass)
    websocket_api.async_register_command(hass, ws_subscribe)

    integration = await async_get_integration(hass, DOMAIN)
    await hass.http.async_register_static_paths(
        [
            StaticPathConfig(
                FRONTEND_URL, str(Path(__file__).parent / "frontend"), cache_headers=False
            )
        ]
    )
    # Loaded on every frontend page: no Lovelace resource to add by hand.
    add_extra_js_url(hass, f"{FRONTEND_URL}/{CARD_FILE}?v={integration.version}")
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ParcelsConfigEntry) -> bool:
    """Set up the integration from a config entry."""
    settings = {**entry.data, **entry.options}
    store: Store[dict[str, Any]] = Store(hass, STORAGE_VERSION, DOMAIN)
    stored = await store.async_load() or {}
    meta: dict[str, Any] = stored.pop(META_KEY, {})
    parcels: dict[str, dict[str, Any]] = {
        k: v for k, v in stored.items() if not k.startswith("_")
    }

    # The tracking service caches results per device fingerprint, so the
    # fingerprint must stay STABLE across restarts — otherwise every restart
    # creates a fresh cache key and loses the warm cache. The mobile app
    # behaves the same way (its fingerprint comes from immutable device
    # properties). Persist the generated fingerprint in the store.
    fingerprint = settings.get(CONF_FINGERPRINT)
    if fingerprint is None:
        fingerprint = meta.get("fingerprint")
        if fingerprint is None:
            fingerprint = TrackingApi._make_fingerprint(None)
            meta["fingerprint"] = fingerprint

    api = TrackingApi(
        async_get_clientsession(hass),
        country=settings.get(CONF_COUNTRY, DEFAULT_COUNTRY),
        locale=settings.get(CONF_LOCALE, DEFAULT_LOCALE),
        postal_code=settings.get(CONF_POSTAL_CODE),
        fingerprint=fingerprint,
    )
    manager = ParcelManager(
        hass,
        entry,
        api,
        store,
        parcels,
        meta,
        auto_archive_after=duration_seconds(
            settings.get(CONF_AUTO_ARCHIVE, DEFAULT_AUTO_ARCHIVE)
        ),
        update_interval=timedelta(
            seconds=int(settings.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL))
        ),
    )
    entry.runtime_data = manager

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    _purge_orphaned_entities(hass, manager)
    await manager.coordinator.async_config_entry_first_refresh()

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


@callback
def _purge_orphaned_entities(hass: HomeAssistant, manager: ParcelManager) -> None:
    """Remove sensors of parcels that were removed or archived."""
    registry = er.async_get(hass)
    wanted = {unique_id_for(t) for t in manager.active()}
    for entry in er.async_entries_for_config_entry(registry, manager.entry.entry_id):
        if entry.unique_id not in wanted:
            _LOGGER.info("Removing orphaned entity %s", entry.entity_id)
            registry.async_remove(entry.entity_id)


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle config entry updates (options flow)."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ParcelsConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        # Tell open cards that the parcel list is gone.
        async_dispatcher_send(hass, SIGNAL_PARCELS_UPDATED)
    return unload_ok


@callback
def get_manager(hass: HomeAssistant) -> ParcelManager | None:
    """Return the manager of the loaded config entry, if any."""
    for entry in hass.config_entries.async_loaded_entries(DOMAIN):
        return entry.runtime_data
    return None


def _require_manager(hass: HomeAssistant) -> ParcelManager:
    manager = get_manager(hass)
    if manager is None:
        raise ServiceValidationError("Irabelle Parcels is not set up")
    return manager


TRACKING_SCHEMA = vol.Schema({vol.Required(ATTR_TRACKING_NUMBER): cv.string})


@callback
def _register_services(hass: HomeAssistant) -> None:
    """Register the parcel actions."""

    async def add_parcel(call: ServiceCall) -> ServiceResponse:
        tracking = await _require_manager(hass).async_add(
            call.data[ATTR_TRACKING_NUMBER],
            call.data.get(CONF_NAME),
            call.data.get(ATTR_CARRIER),
        )
        return {ATTR_TRACKING_NUMBER: tracking}

    async def remove_parcel(call: ServiceCall) -> None:
        await _require_manager(hass).async_remove(_tracking(call))

    async def update_parcel(call: ServiceCall) -> None:
        await _require_manager(hass).async_update(
            _tracking(call), call.data.get(CONF_NAME), call.data.get(ATTR_CARRIER)
        )

    async def archive_parcel(call: ServiceCall) -> None:
        await _require_manager(hass).async_archive(_tracking(call))

    async def unarchive_parcel(call: ServiceCall) -> None:
        await _require_manager(hass).async_unarchive(_tracking(call))

    async def clear_archive(call: ServiceCall) -> ServiceResponse:
        return {"removed": await _require_manager(hass).async_clear_archive()}

    hass.services.async_register(
        DOMAIN,
        "add_parcel",
        add_parcel,
        schema=vol.Schema(
            {
                vol.Required(ATTR_TRACKING_NUMBER): cv.string,
                vol.Optional(CONF_NAME): cv.string,
                vol.Optional(ATTR_CARRIER): cv.string,
            }
        ),
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN,
        "update_parcel",
        update_parcel,
        schema=vol.Schema(
            {
                vol.Required(ATTR_TRACKING_NUMBER): cv.string,
                vol.Optional(CONF_NAME): cv.string,
                vol.Optional(ATTR_CARRIER): cv.string,
            }
        ),
    )
    for name, handler in (
        ("remove_parcel", remove_parcel),
        ("archive_parcel", archive_parcel),
        ("unarchive_parcel", unarchive_parcel),
    ):
        hass.services.async_register(DOMAIN, name, handler, schema=TRACKING_SCHEMA)
    hass.services.async_register(
        DOMAIN,
        "clear_archive",
        clear_archive,
        supports_response=SupportsResponse.OPTIONAL,
    )


def _tracking(call: ServiceCall) -> str:
    value = str(call.data[ATTR_TRACKING_NUMBER]).strip()
    return normalize_tracking(value) or value


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/subscribe"})
@callback
def ws_subscribe(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Stream the full parcel list (active + archived) to a card."""

    @callback
    def send() -> None:
        manager = get_manager(hass)
        connection.send_message(
            websocket_api.event_message(
                msg["id"],
                {
                    "loaded": manager is not None,
                    "parcels": manager.as_list() if manager else [],
                },
            )
        )

    connection.subscriptions[msg["id"]] = async_dispatcher_connect(
        hass, SIGNAL_PARCELS_UPDATED, send
    )
    connection.send_result(msg["id"])
    send()
