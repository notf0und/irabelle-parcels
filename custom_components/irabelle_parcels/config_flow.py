"""Config flow for the Irabelle Parcels integration."""

from __future__ import annotations

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow

from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.selector import selector

from .const import (
    CONF_AUTO_ARCHIVE,
    CONF_COUNTRY,
    CONF_FINGERPRINT,
    CONF_LOCALE,
    CONF_POSTAL_CODE,
    CONF_SCAN_INTERVAL,
    COUNTRIES,
    DEFAULT_AUTO_ARCHIVE,
    DEFAULT_COUNTRY,
    DEFAULT_LOCALE,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    NAME,
)
from .manager import normalize_duration, normalize_tracking

SCAN_INTERVAL_CHOICES = {
    300: "5 minutes",
    600: "10 minutes",
    900: "15 minutes",
    1800: "30 minutes",
    3600: "1 hour",
    7200: "2 hours",
    10800: "3 hours",
    21600: "6 hours",
    43200: "12 hours",
    86400: "24 hours",
}


def _country_choices() -> list[str]:
    return sorted(set(COUNTRIES.values()))


def _base_schema(entry_data: dict | None = None) -> vol.Schema:
    data = entry_data or {}
    return vol.Schema(
        {
            vol.Optional(
                CONF_COUNTRY,
                default=data.get(CONF_COUNTRY, DEFAULT_COUNTRY),
            ): vol.In(_country_choices()),
            vol.Optional(CONF_POSTAL_CODE, default=data.get(CONF_POSTAL_CODE, "")): cv.string,
            vol.Optional(
                CONF_SCAN_INTERVAL,
                default=int(data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)),
            ): vol.In(SCAN_INTERVAL_CHOICES),
            vol.Optional(
                CONF_AUTO_ARCHIVE,
                default=data.get(CONF_AUTO_ARCHIVE, DEFAULT_AUTO_ARCHIVE),
            ): selector({"duration": {"enable_day": True, "enable_second": False}}),
        }
    )


class IrabelleParcelsConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for the integration."""

    VERSION = 1

    async def async_step_user(self, user_input: dict | None = None) -> FlowResult:
        """Handle the initial step."""
        if user_input is None:
            return self.async_show_form(step_id="user", data_schema=_base_schema())

        user_input[CONF_LOCALE] = DEFAULT_LOCALE
        if not user_input.get(CONF_POSTAL_CODE):
            user_input.pop(CONF_POSTAL_CODE, None)
        if isinstance(user_input.get(CONF_AUTO_ARCHIVE), dict):
            user_input[CONF_AUTO_ARCHIVE] = normalize_duration(user_input[CONF_AUTO_ARCHIVE])
        return self.async_create_entry(title=NAME, data=user_input)

    @staticmethod
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return IrabelleParcelsOptionsFlow()


class IrabelleParcelsOptionsFlow(OptionsFlow):
    """Handle options (add/remove parcels, polling frequency, country, postal code)."""

    async def async_step_init(self, user_input: dict | None = None) -> FlowResult:
        """Show the menu."""
        return self.async_show_menu(
            step_id="init",
            menu_options=["add_parcel", "remove_parcel", "settings", "fingerprint"],
        )

    async def async_step_add_parcel(self, user_input: dict | None = None) -> FlowResult:
        """Add a new parcel."""
        errors: dict[str, str] = {}
        if user_input is not None:
            manager = self.config_entry.runtime_data
            tracking = normalize_tracking(user_input.get("tracking_number"))
            if not tracking:
                errors["base"] = "invalid_tracking"
            elif tracking in manager.active():
                errors["base"] = "already_tracked"
            else:
                await manager.async_add(
                    tracking, user_input.get("name"), user_input.get("carrier")
                )
                return self.async_create_entry(data=dict(self.config_entry.options))

        return self.async_show_form(
            step_id="add_parcel",
            data_schema=vol.Schema(
                {
                    vol.Required("tracking_number"): cv.string,
                    vol.Optional("name", default=""): cv.string,
                    vol.Optional("carrier", default="Auto Detect"): cv.string,
                }
            ),
            errors=errors,
        )

    async def async_step_remove_parcel(self, user_input: dict | None = None) -> FlowResult:
        """Remove an existing parcel."""
        manager = self.config_entry.runtime_data
        if user_input is not None:
            await manager.async_remove(user_input["tracking_number"])
            return self.async_create_entry(data=dict(self.config_entry.options))

        return self.async_show_form(
            step_id="remove_parcel",
            data_schema=vol.Schema(
                {
                    vol.Required("tracking_number"): vol.In(
                        {
                            t: p.get("name", t) + (" (archived)" if p.get("archived") else "")
                            for t, p in manager.parcels.items()
                        }
                    )
                }
            ),
        )

    async def async_step_settings(self, user_input: dict | None = None) -> FlowResult:
        """Adjust country, postal code and polling frequency."""
        if user_input is not None:
            if not user_input.get(CONF_POSTAL_CODE):
                user_input.pop(CONF_POSTAL_CODE, None)
            if isinstance(user_input.get(CONF_AUTO_ARCHIVE), dict):
                user_input[CONF_AUTO_ARCHIVE] = normalize_duration(user_input[CONF_AUTO_ARCHIVE])
            return self.async_create_entry(data=user_input)

        current = {**self.config_entry.data, **self.config_entry.options}
        return self.async_show_form(
            step_id="settings",
            data_schema=_base_schema(current),
        )

    async def async_step_fingerprint(self, user_input: dict | None = None) -> FlowResult:
        """Optionally override the auto-generated device fingerprint."""
        if user_input is not None:
            fingerprint = {k: v for k, v in user_input.items() if v}
            options = dict(self.config_entry.options)
            if fingerprint:
                options[CONF_FINGERPRINT] = fingerprint
            else:
                options.pop(CONF_FINGERPRINT, None)
            return self.async_create_entry(data=options)

        current = {**self.config_entry.data, **self.config_entry.options}
        fp = current.get(CONF_FINGERPRINT, {})
        return self.async_show_form(
            step_id="fingerprint",
            description_placeholders={"note": "Leave all fields empty to use the automatic fingerprint."},
            data_schema=vol.Schema(
                {
                    vol.Optional("unique_id", default=fp.get("unique_id", "")): cv.string,
                    vol.Optional("model", default=fp.get("model", "")): cv.string,
                    vol.Optional("device_id", default=fp.get("device_id", "")): cv.string,
                    vol.Optional("manufacturer", default=fp.get("manufacturer", "")): cv.string,
                    vol.Optional("version", default=fp.get("version", "")): cv.string,
                }
            ),
        )
