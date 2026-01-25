"""
Enphase Battery IQ 5P Integration for Home Assistant
Intégration pour batteries Enphase IQ 5P
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
import time
from typing import TYPE_CHECKING

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED, Platform

from .const import CONF_CONNECTION_MODE, CONNECTION_MODE_CLOUD, DOMAIN
from .coordinator import EnphaseBatteryDataUpdateCoordinator

if TYPE_CHECKING:
    from homeassistant.core import Event, HomeAssistant

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.SELECT,
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

    Optimized for fast startup (<2s):
    - Authentication is deferred to background task
    - Platforms are set up immediately (entities will be unavailable until first refresh)
    - First data refresh happens after HA startup or in background
    """
    start_time = time.perf_counter()
    _LOGGER.debug("Starting Enphase Battery setup")

    # Create coordinator (fast, no I/O)
    # Note: Migration is handled automatically by HA before this function is called
    coordinator = EnphaseBatteryDataUpdateCoordinator(hass, entry)

    # Store coordinator in runtime_data (modern pattern, replaces hass.data)
    entry.runtime_data = EnphaseBatteryRuntimeData(coordinator=coordinator)

    # Setup platforms immediately (entities will show as unavailable until first refresh)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Deferred setup: authentication + first refresh in background
    # This prevents blocking HA startup while still getting data quickly
    async def _async_deferred_setup(event: Event = None):
        """Setup coordinator and fetch first data after HA has started."""
        deferred_start = time.perf_counter()
        try:
            # Setup coordinator (authentication) - this is the slow part
            await coordinator._async_setup()
            auth_time = time.perf_counter() - deferred_start
            _LOGGER.debug("Enphase Battery auth completed in %.2fs", auth_time)
            # Fetch first data
            await coordinator.async_refresh()
            total_time = time.perf_counter() - deferred_start
            _LOGGER.debug("Enphase Battery first refresh completed in %.2fs", total_time)
        except Exception as err:
            _LOGGER.error("Deferred setup failed: %s", err)

    # If HA is already started, run deferred setup immediately in background
    # Otherwise, wait for HA to finish starting
    if hass.is_running:
        task = hass.async_create_background_task(_async_deferred_setup(), "enphase_battery_deferred_setup")
        # Use lambda to avoid returning True from task.cancel() which HA tries to await
        entry.async_on_unload(lambda: task.cancel())
    else:
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, _async_deferred_setup)

    # Listen for options updates
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    elapsed = time.perf_counter() - start_time
    _LOGGER.info("Enphase Battery setup completed in %.2fs (auth deferred)", elapsed)

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
