"""
Enphase Battery IQ 5P Integration for Home Assistant
Intégration pour batteries Enphase IQ 5P
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import TYPE_CHECKING

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import callback
from homeassistant.helpers import entity_registry as er, issue_registry as ir

from .const import (
    CONF_CONNECTION_MODE,
    CONF_ENABLE_CLOUD_CONTROL,
    CONNECTION_MODE_CLOUD,
    DOMAIN,
)
from .coordinator import EnphaseBatteryDataUpdateCoordinator

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.device_registry import DeviceEntry

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
]


@dataclass(slots=True)
class EnphaseBatteryRuntimeData:
    """Runtime data for Enphase Battery integration."""

    coordinator: EnphaseBatteryDataUpdateCoordinator


# Type alias for ConfigEntry with runtime_data
# Use TYPE_CHECKING guard for Python 3.11 compatibility (ConfigEntry is not subscriptable at runtime)
if TYPE_CHECKING:
    EnphaseBatteryConfigEntry = ConfigEntry[EnphaseBatteryRuntimeData]
else:
    EnphaseBatteryConfigEntry = ConfigEntry


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate old config entries to the current format.

    Migration history:
    - Version 1: Initial version (cloud-only mode)
    - Version 2: Added connection_mode field for dual-mode support
    - Version 3: Entity unique IDs scoped to the config entry (multi-instance safe)
    """
    _LOGGER.debug("Migrating Enphase Battery entry from version %s", entry.version)

    if entry.version == 1:
        # v1 -> v2: old configs were always cloud-based.
        new_data = {**entry.data}
        new_data.setdefault(CONF_CONNECTION_MODE, CONNECTION_MODE_CLOUD)
        hass.config_entries.async_update_entry(entry, data=new_data, version=2)
        _LOGGER.info("Migrated entry to version 2 (added connection_mode='cloud')")

    if entry.version == 2:
        # v2 -> v3: rewrite the legacy DOMAIN-prefixed unique IDs to be scoped
        # to the config entry, so two Enphase systems can coexist.
        await _async_migrate_unique_ids(hass, entry)
        hass.config_entries.async_update_entry(entry, version=3)
        _LOGGER.info("Migrated entry to version 3 (entry-scoped unique IDs)")

    return True


async def _async_migrate_unique_ids(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Rewrite entity unique IDs from the legacy ``DOMAIN`` prefix to the entry id."""
    legacy_prefix = f"{DOMAIN}_"
    new_prefix = f"{entry.entry_id}_"

    @callback
    def _update_unique_id(reg_entry: er.RegistryEntry) -> dict[str, str] | None:
        if reg_entry.unique_id.startswith(legacy_prefix):
            return {"new_unique_id": new_prefix + reg_entry.unique_id[len(legacy_prefix) :]}
        return None

    await er.async_migrate_entries(hass, entry.entry_id, _update_unique_id)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: EnphaseBatteryConfigEntry,
) -> bool:
    """Set up Enphase Battery from a config entry.

    Authentication and the first data fetch run through
    ``async_config_entry_first_refresh``. The coordinator's ``_async_setup``
    raises ``ConfigEntryAuthFailed`` on bad credentials (triggers the reauth
    flow) and ``ConfigEntryNotReady`` on a connection failure (HA retries with
    exponential backoff). Migration is handled by HA before this runs.
    """
    coordinator = EnphaseBatteryDataUpdateCoordinator(hass, entry)

    # Authenticate (coordinator._async_setup) and fetch the first data set.
    await coordinator.async_config_entry_first_refresh()

    # Store coordinator in runtime_data (modern pattern, replaces hass.data)
    entry.runtime_data = EnphaseBatteryRuntimeData(coordinator=coordinator)

    # Set up platforms now that the first data is available.
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Surface a repair issue when battery control is unavailable.
    _async_manage_control_issue(hass, entry, coordinator)

    # Reload the entry when its options change.
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    return True


@callback
def _async_manage_control_issue(
    hass: HomeAssistant,
    entry: ConfigEntry,
    coordinator: EnphaseBatteryDataUpdateCoordinator,
) -> None:
    """Create/clear the repair issue for control unavailable in local-only mode.

    In local mode without cloud control, firmware 8.x cannot be controlled via
    the local API, so the switches/select/number are not created. The user can
    fix this by enabling cloud control (reconfigure).
    """
    issue_id = f"control_disabled_{entry.entry_id}"
    if coordinator.is_local_mode and not entry.data.get(CONF_ENABLE_CLOUD_CONTROL, False):
        ir.async_create_issue(
            hass,
            DOMAIN,
            issue_id,
            is_fixable=False,
            severity=ir.IssueSeverity.WARNING,
            translation_key="control_disabled",
        )
    else:
        ir.async_delete_issue(hass, DOMAIN, issue_id)


async def async_unload_entry(
    hass: HomeAssistant,
    entry: EnphaseBatteryConfigEntry,
) -> bool:
    """Unload a config entry."""
    # Unload platforms
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        # Cleanup coordinator (runtime_data is automatically cleaned up)
        await entry.runtime_data.coordinator.async_shutdown()

    return unload_ok


async def async_reload_entry(
    hass: HomeAssistant,
    entry: EnphaseBatteryConfigEntry,
) -> None:
    """Reload config entry when options change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_remove_config_entry_device(
    hass: HomeAssistant,
    config_entry: EnphaseBatteryConfigEntry,
    device_entry: DeviceEntry,
) -> bool:
    """Allow removing a battery device that the system no longer reports.

    The system (hub) device cannot be removed while the entry exists; an
    individual battery can be removed only once it is no longer present in the
    coordinator data (so a battery temporarily offline is kept).
    """
    coordinator = config_entry.runtime_data.coordinator
    known_serials = {
        device["serial_num"] for device in (coordinator.data or {}).get("devices", []) if device.get("serial_num")
    }
    for domain, identifier in device_entry.identifiers:
        if domain != DOMAIN:
            continue
        if identifier == "enphase_battery_system":
            return False
        if identifier.startswith("battery_"):
            return identifier.removeprefix("battery_") not in known_serials
    return True
