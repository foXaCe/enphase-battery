"""
Enphase Battery IQ 5P Integration for Home Assistant
Intégration pour batteries Enphase IQ 5P
"""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import DOMAIN, CONF_CONNECTION_MODE, CONNECTION_MODE_CLOUD
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
    _LOGGER.info("Checking if migration is needed for entry %s", entry.entry_id)

    # Check if this is an old config (before v2.0.0 - no connection_mode)
    if CONF_CONNECTION_MODE not in entry.data:
        _LOGGER.info("⚙️ Migrating old config entry to dual-mode format")

        # Old configs were always cloud-based
        new_data = {**entry.data, CONF_CONNECTION_MODE: CONNECTION_MODE_CLOUD}

        # Update config entry
        hass.config_entries.async_update_entry(entry, data=new_data)

        _LOGGER.info(
            "✅ Migration successful: Added connection_mode='cloud' to existing config"
        )

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Enphase Battery from a config entry."""
    _LOGGER.info("🔋 Configuration de l'intégration Enphase Battery IQ 5P")

    # Migrate old entries if needed
    await async_migrate_entry(hass, entry)

    hass.data.setdefault(DOMAIN, {})

    # Create and initialize coordinator
    coordinator = EnphaseBatteryDataUpdateCoordinator(hass, entry)

    # Setup coordinator (auth + optional MQTT)
    try:
        await coordinator._async_setup()
    except Exception as err:
        _LOGGER.error("Failed to setup coordinator: %s", err)
        return False

    # Fetch initial data
    await coordinator.async_config_entry_first_refresh()

    # Store coordinator
    hass.data[DOMAIN][entry.entry_id] = coordinator

    # Setup platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Listen for options updates (MQTT enable/disable)
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    _LOGGER.info("✅ Enphase Battery IQ 5P integration configured successfully")

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.info("Unloading Enphase Battery integration")

    # Unload platforms
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        # Cleanup coordinator
        coordinator: EnphaseBatteryDataUpdateCoordinator = hass.data[DOMAIN].pop(entry.entry_id)
        await coordinator.async_shutdown()

    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry when options change."""
    _LOGGER.info("Reloading Enphase Battery integration (options changed)")
    await hass.config_entries.async_reload(entry.entry_id)
