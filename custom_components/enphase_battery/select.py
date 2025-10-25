"""Select platform for Enphase Battery."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    BATTERY_MODE_BACKUP_ONLY,
    BATTERY_MODE_COST_SAVINGS,
    BATTERY_MODE_EXPERT,
    BATTERY_MODE_SELF_CONSUMPTION,
    DOMAIN,
)
from .coordinator import EnphaseBatteryDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Enphase Battery select platform."""
    coordinator: EnphaseBatteryDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities = []

    # Battery Mode select available in:
    # 1. Cloud mode (always)
    # 2. Local mode with cloud control enabled (hybrid mode)
    # Local API no longer supports this since firmware 8.2.4225 (confirmed by Home Assistant docs)
    enable_cloud_control = entry.data.get("enable_cloud_control", False)

    if not coordinator.is_local_mode or enable_cloud_control:
        entities.append(BatteryModeSelect(coordinator))
        mode_desc = "Cloud mode" if not coordinator.is_local_mode else "Hybrid mode (Local data + Cloud control)"
        _LOGGER.info(f"Battery Mode select enabled ({mode_desc})")
    else:
        _LOGGER.warning(
            "Battery Mode select disabled. "
            "Envoy firmware 8.x no longer supports battery control via local API. "
            "Enable 'Cloud Control' option in integration settings or use Enphase app."
        )

    if entities:
        async_add_entities(entities)


class BatteryModeSelect(CoordinatorEntity, SelectEntity):
    """Battery Operation Mode select entity."""

    def __init__(self, coordinator: EnphaseBatteryDataUpdateCoordinator) -> None:
        """Initialize the select entity."""
        super().__init__(coordinator)
        self._attr_name = "Mode de la batterie"
        self._attr_unique_id = f"{DOMAIN}_battery_mode"
        self._attr_has_entity_name = True
        self._attr_icon = "mdi:battery-sync"

        # Options basées sur les modes disponibles dans l'app Enphase
        # Note: backup_only et expert sont souvent cachés selon la configuration
        self._attr_options = [
            "Autoconsommation",  # self-consumption
            "Optimisation IA",   # cost_savings (AI optimization)
        ]

        # Mapping API <-> UI
        self._mode_api_to_ui = {
            BATTERY_MODE_SELF_CONSUMPTION: "Autoconsommation",
            BATTERY_MODE_COST_SAVINGS: "Optimisation IA",
            # Modes cachés mais conservés pour compatibilité
            BATTERY_MODE_BACKUP_ONLY: "Backup uniquement",
            BATTERY_MODE_EXPERT: "Expert",
        }

        self._mode_ui_to_api = {v: k for k, v in self._mode_api_to_ui.items()}

    @property
    def device_info(self) -> dict[str, Any]:
        """Return device information."""
        return {
            "identifiers": {(DOMAIN, "enphase_battery")},
            "name": "Enphase Battery IQ 5P",
            "manufacturer": "Enphase Energy",
            "model": "IQ Battery 5P",
        }

    @property
    def current_option(self) -> str | None:
        """Return the current selected option."""
        if not self.coordinator.data:
            return None

        api_mode = self.coordinator.battery_mode
        if not api_mode:
            return None

        return self._mode_api_to_ui.get(api_mode)

    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""
        api_mode = self._mode_ui_to_api.get(option)

        if not api_mode:
            _LOGGER.error(f"Invalid mode selected: {option}")
            return

        try:
            # Always use cloud API (pure cloud mode or hybrid mode)
            if not self.coordinator.api:
                raise Exception("Cloud API not initialized. Enable cloud control in settings.")
            await self.coordinator.api.set_battery_mode(api_mode)
            await self.coordinator.async_request_refresh()

        except Exception as err:
            _LOGGER.error(f"Failed to change battery mode: {err}")
            raise
