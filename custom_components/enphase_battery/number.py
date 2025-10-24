"""Number platform for Enphase Battery."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import EnphaseBatteryDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Enphase Battery number platform."""
    coordinator: EnphaseBatteryDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities = [
        BatteryBackupReserveNumber(coordinator),
    ]

    async_add_entities(entities)


class BatteryBackupReserveNumber(CoordinatorEntity, NumberEntity):
    """Battery minimum discharge level (Very Low SOC) number entity."""

    def __init__(self, coordinator: EnphaseBatteryDataUpdateCoordinator) -> None:
        """Initialize the number entity."""
        super().__init__(coordinator)
        self._attr_name = "Niveau d'arrêt de la batterie"
        self._attr_unique_id = f"{DOMAIN}_very_low_soc"
        self._attr_has_entity_name = True
        self._attr_icon = "mdi:battery-alert"
        self._attr_native_unit_of_measurement = PERCENTAGE
        self._attr_mode = NumberMode.SLIDER

        # Limites découvertes dans l'API: 5-25%
        self._attr_native_min_value = 5
        self._attr_native_max_value = 25
        self._attr_native_step = 1

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
    def native_value(self) -> float | None:
        """Return the current value."""
        if not self.coordinator.data:
            return None

        return self.coordinator.data.get("very_low_soc", 5)

    async def async_set_native_value(self, value: float) -> None:
        """Set new value."""
        try:
            await self.coordinator.api.set_very_low_soc(int(value))
            await self.coordinator.async_request_refresh()

        except Exception as err:
            _LOGGER.error(f"Failed to set very low SOC: {err}")
