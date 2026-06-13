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

from .const import CONF_CONNECTION_MODE, CONNECTION_MODE_CLOUD, DOMAIN
from .coordinator import EnphaseBatteryDataUpdateCoordinator

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

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
    """Migrate old config entries to new format.

    Migration history:
    - Version 1: Initial version (cloud-only mode)
    - Version 2: Added connection_mode field for dual-mode support
    """
    _LOGGER.debug("Migrating from version %s to %s", entry.version, 2)

    if entry.version == 1:
        # Migrate from v1 to v2: Add connection_mode field
        # Old configs were always cloud-based
        new_data = {**entry.data}
        if CONF_CONNECTION_MODE not in new_data:
            new_data[CONF_CONNECTION_MODE] = CONNECTION_MODE_CLOUD

        hass.config_entries.async_update_entry(entry, data=new_data, version=2)
        _LOGGER.info("Migrated config entry from version 1 to 2: added connection_mode='cloud'")

    return True


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

    # Reload the entry when its options change.
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    return True


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
