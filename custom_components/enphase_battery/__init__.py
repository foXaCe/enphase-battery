"""
Enphase Battery IQ 5P Integration for Home Assistant
Intégration pour batteries Enphase IQ 5P
"""

from __future__ import annotations

import logging

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
    """Set up Enphase Battery from a config entry."""
    _LOGGER.info("Starting Enphase Battery setup")

    # Migrate old entries if needed
    await async_migrate_entry(hass, entry)

    hass.data.setdefault(DOMAIN, {})

    # Create and initialize coordinator
    coordinator = EnphaseBatteryDataUpdateCoordinator(hass, entry)

    # Setup coordinator (authentication)
    try:
        await coordinator._async_setup()
    except Exception as err:
        _LOGGER.error("Failed to setup coordinator: %s", err)
        return False

    # Store coordinator first
    hass.data[DOMAIN][entry.entry_id] = coordinator

    # Setup platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Wait for Home Assistant to finish startup before making API calls
    # This prevents blocking HA startup while still getting data quickly
    async def _async_first_refresh(event: Event = None):
        """Fetch first data after HA has started."""
        try:
            await coordinator.async_refresh()
        except Exception as err:
            _LOGGER.error("First data refresh failed: %s", err)

    # If HA is already started, fetch data immediately
    # Otherwise, wait for HA to finish starting
    if hass.is_running:
        task = hass.async_create_background_task(_async_first_refresh(), "enphase_battery_first_refresh")
        # Register task.cancel as the unload callback (not the Task object itself)
        entry.async_on_unload(task.cancel)
    else:
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, _async_first_refresh)

    # Listen for options updates
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    _LOGGER.info("Enphase Battery setup completed")

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
