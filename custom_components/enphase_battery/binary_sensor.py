"""Binary sensor platform for Enphase Battery."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
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
    """Set up Enphase Battery binary sensor platform."""
    coordinator: EnphaseBatteryDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities = [
        BatteryChargingBinarySensor(coordinator),
        BatteryConnectedBinarySensor(coordinator),
    ]

    async_add_entities(entities)


class EnphaseBatteryBinarySensorBase(CoordinatorEntity, BinarySensorEntity):
    """Base class for Enphase Battery binary sensors."""

    def __init__(
        self,
        coordinator: EnphaseBatteryDataUpdateCoordinator,
        sensor_type: str,
        name: str,
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator)
        self._sensor_type = sensor_type
        self._attr_name = name
        self._attr_unique_id = f"{DOMAIN}_{sensor_type}"
        self._attr_has_entity_name = True

    @property
    def device_info(self) -> dict[str, Any]:
        """Return device information."""
        return {
            "identifiers": {(DOMAIN, "enphase_battery")},
            "name": "Enphase Battery IQ 5P",
            "manufacturer": "Enphase Energy",
            "model": "IQ Battery 5P",
        }


class BatteryChargingBinarySensor(EnphaseBatteryBinarySensorBase):
    """Battery Charging binary sensor."""

    def __init__(self, coordinator: EnphaseBatteryDataUpdateCoordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, "charging", "Batterie en charge")
        self._attr_device_class = BinarySensorDeviceClass.BATTERY_CHARGING

    @property
    def is_on(self) -> bool | None:
        """Return true if battery is charging."""
        if not self.coordinator.data:
            return None
        return self.coordinator.is_charging

    @property
    def icon(self) -> str:
        """Return icon based on charging state."""
        if self.is_on:
            return "mdi:battery-charging"
        return "mdi:battery"


class BatteryConnectedBinarySensor(EnphaseBatteryBinarySensorBase):
    """Battery Connected binary sensor."""

    def __init__(self, coordinator: EnphaseBatteryDataUpdateCoordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, "connected", "Batterie connectée")
        self._attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    @property
    def is_on(self) -> bool | None:
        """Return true if battery is connected."""
        if not self.coordinator.data:
            return None

        # Battery is connected if we have valid SOC data
        soc = self.coordinator.data.get("soc")
        status = self.coordinator.data.get("status")

        return soc is not None and status == "normal"

    @property
    def icon(self) -> str:
        """Return icon based on connection state."""
        if self.is_on:
            return "mdi:battery-check"
        return "mdi:battery-alert"
