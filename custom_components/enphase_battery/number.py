"""Number platform for Enphase Battery."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.const import PERCENTAGE
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DEVICE_INFO, DOMAIN
from .coordinator import EnphaseBatteryDataUpdateCoordinator

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from . import EnphaseBatteryConfigEntry

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: EnphaseBatteryConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Enphase Battery number platform."""
    coordinator = entry.runtime_data.coordinator

    entities = [
        BatteryBackupReserveNumber(coordinator),
    ]

    async_add_entities(entities)


class BatteryBackupReserveNumber(CoordinatorEntity[EnphaseBatteryDataUpdateCoordinator], NumberEntity):
    """Battery minimum discharge level (Very Low SOC) number entity."""

    # Use __slots__ to reduce memory footprint
    __slots__ = ()

    # Class-level device_info (shared across all instances)
    _attr_device_info = DEVICE_INFO
    _attr_has_entity_name = True

    def __init__(self, coordinator: EnphaseBatteryDataUpdateCoordinator) -> None:
        """Initialize the number entity."""
        super().__init__(coordinator)
        self._attr_translation_key = "battery_reserve"
        self._attr_unique_id = f"{coordinator.unique_id_prefix}_very_low_soc"
        self._attr_icon = "mdi:battery-alert"
        self._attr_native_unit_of_measurement = PERCENTAGE
        self._attr_mode = NumberMode.SLIDER

        # Limites découvertes dans l'API: 5-25%
        self._attr_native_min_value = 5
        self._attr_native_max_value = 25
        self._attr_native_step = 1

    @property
    def native_value(self) -> float | None:
        """Return the current value."""
        if not self.coordinator.data:
            return None

        return self.coordinator.data.get("very_low_soc", 5)  # type: ignore[no-any-return]

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        # Only available if coordinator has data AND cloud API is initialized
        return super().available and self.coordinator.api is not None

    async def async_set_native_value(self, value: float) -> None:
        """Set new value."""
        if not self.coordinator.api:
            _LOGGER.error("Cloud API not initialized. Enable cloud control in settings.")
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="cloud_api_not_initialized",
            )

        try:
            await self.coordinator.api.set_very_low_soc(int(value))
            await self.coordinator.async_request_refresh()
        except Exception as err:
            _LOGGER.error("Failed to set very low SOC: %s", err)
            raise
