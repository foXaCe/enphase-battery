"""
Enphase Battery IQ 5P Integration for Home Assistant
Intégration pour batteries Enphase IQ 5P
"""

from __future__ import annotations

import logging
import time

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED, Platform
from homeassistant.core import Event, HomeAssistant

from .const import CONF_CONNECTION_MODE, CONNECTION_MODE_CLOUD, DOMAIN
from .coordinator import EnphaseBatteryDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.SELECT,
    Platform.SWITCH,
]


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate old config entries to new format with connection_mode."""
    # Check if this is an old config (before v2.0.0 - no connection_mode)
    if CONF_CONNECTION_MODE not in entry.data:
        _LOGGER.info("⚙️ Migrating old config entry to dual-mode format")

        # Old configs were always cloud-based
        new_data = {**entry.data, CONF_CONNECTION_MODE: CONNECTION_MODE_CLOUD}

        # Update config entry
        hass.config_entries.async_update_entry(entry, data=new_data)

        _LOGGER.info("Migration successful: Added connection_mode='cloud' to existing config")

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Enphase Battery from a config entry.

    Optimized for fast startup (<2s):
    - Authentication is deferred to background task
    - Platforms are set up immediately (entities will be unavailable until first refresh)
    - First data refresh happens after HA startup or in background
    """
    start_time = time.perf_counter()
    _LOGGER.info("Starting Enphase Battery setup")

    # Migrate old entries if needed (fast, no I/O)
    await async_migrate_entry(hass, entry)

    hass.data.setdefault(DOMAIN, {})

    # Create coordinator (fast, no I/O)
    coordinator = EnphaseBatteryDataUpdateCoordinator(hass, entry)

    # Store coordinator immediately so platforms can access it
    hass.data[DOMAIN][entry.entry_id] = coordinator

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
        entry.async_on_unload(task.cancel)
    else:
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, _async_deferred_setup)

    # Listen for options updates
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    elapsed = time.perf_counter() - start_time
    _LOGGER.info("Enphase Battery setup completed in %.2fs (auth deferred)", elapsed)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    # Unload platforms
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        # Cleanup coordinator
        coordinator: EnphaseBatteryDataUpdateCoordinator = hass.data[DOMAIN].pop(entry.entry_id)
        await coordinator.async_shutdown()

    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry when options change."""
    await hass.config_entries.async_reload(entry.entry_id)
