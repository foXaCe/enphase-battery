"""Diagnostics support for Enphase Battery."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME

from .coordinator import EnphaseBatteryDataUpdateCoordinator

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from . import EnphaseBatteryConfigEntry

# Keys to redact from diagnostics
TO_REDACT = {
    CONF_PASSWORD,
    CONF_USERNAME,
    "cloud_password",
    "cloud_username",
    "serial",
    "serial_number",
    "sn",
    "token",
    "jwt_token",
    "session_id",
    "site_id",
    "user_id",
}


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: EnphaseBatteryConfigEntry) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator: EnphaseBatteryDataUpdateCoordinator = entry.runtime_data.coordinator

    diagnostics_data = {
        "config_entry": {
            "entry_id": entry.entry_id,
            "version": entry.version,
            "domain": entry.domain,
            "title": entry.title,
            "data": async_redact_data(entry.data, TO_REDACT),
            "options": async_redact_data(dict(entry.options), TO_REDACT),
        },
        "coordinator": {
            "last_update_success": coordinator.last_update_success,
            "is_local_mode": coordinator.is_local_mode,
            "update_interval": str(coordinator.update_interval),
        },
        "data": async_redact_data(coordinator.data, TO_REDACT) if coordinator.data else None,
    }

    # Add local API info if available
    if coordinator.local_api:
        diagnostics_data["local_api"] = {
            "host": coordinator.local_api._host,
            "firmware_version": coordinator.local_api._firmware_version,
            "has_token": coordinator.local_api._jwt_token is not None,
        }

    # Add cloud API info if available
    if coordinator.api:
        diagnostics_data["cloud_api"] = {
            "authenticated": coordinator.api._session_token is not None,
            "site_id": "**REDACTED**" if coordinator.api._site_id else None,
            "user_id": "**REDACTED**" if coordinator.api._user_id else None,
        }

    return diagnostics_data
