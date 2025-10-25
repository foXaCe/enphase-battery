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
        # Diagnostic binary sensors
        BatteryGridTiedBinarySensor(coordinator),
        BatteryHealthyBinarySensor(coordinator),
        BatteryCommunicatingBinarySensor(coordinator),
        EnvoyConnectedBinarySensor(coordinator),
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
        return soc is not None and soc > 0

    @property
    def icon(self) -> str:
        """Return icon based on connection state."""
        if self.is_on:
            return "mdi:battery-check"
        return "mdi:battery-alert"


# Diagnostic Binary Sensors

class BatteryGridTiedBinarySensor(EnphaseBatteryBinarySensorBase):
    """Battery Grid-Tied binary sensor."""

    def __init__(self, coordinator: EnphaseBatteryDataUpdateCoordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, "grid_tied", "Connecté au réseau")
        self._attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
        self._attr_entity_category = "diagnostic"

    @property
    def is_on(self) -> bool | None:
        """Return true if battery is grid-tied."""
        if not self.coordinator.data:
            return None

        devices = self.coordinator.data.get("devices", [])
        if devices and len(devices) > 0:
            grid_state = devices[0].get("reported_enc_grid_state", "")
            return grid_state == "grid-tied"

        status = self.coordinator.data.get("status", "")
        return "grid-tied" in status.lower()

    @property
    def icon(self) -> str:
        """Return icon based on grid state."""
        if self.is_on:
            return "mdi:transmission-tower"
        return "mdi:transmission-tower-off"


class BatteryHealthyBinarySensor(EnphaseBatteryBinarySensorBase):
    """Battery Health Status binary sensor."""

    def __init__(self, coordinator: EnphaseBatteryDataUpdateCoordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, "healthy", "Batterie en bonne santé")
        self._attr_device_class = BinarySensorDeviceClass.PROBLEM
        self._attr_entity_category = "diagnostic"

    @property
    def is_on(self) -> bool | None:
        """Return true if battery has a problem (inverted for PROBLEM class)."""
        if not self.coordinator.data:
            return None

        # SOH below 80% indicates problem
        soh = self.coordinator.data.get("soh", 100)

        # Temperature too high (>50°C) indicates problem
        temp = self.coordinator.data.get("temperature")
        if temp and temp > 50:
            return True

        # SOH below 80% indicates problem
        return soh < 80

    @property
    def icon(self) -> str:
        """Return icon based on health state."""
        if self.is_on:  # Problem detected
            return "mdi:alert-circle"
        return "mdi:check-circle"


class BatteryCommunicatingBinarySensor(EnphaseBatteryBinarySensorBase):
    """Battery Communication Status binary sensor."""

    def __init__(self, coordinator: EnphaseBatteryDataUpdateCoordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, "communicating", "Batterie communique")
        self._attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
        self._attr_entity_category = "diagnostic"

    @property
    def is_on(self) -> bool | None:
        """Return true if battery is communicating."""
        if not self.coordinator.data:
            return None

        devices = self.coordinator.data.get("devices", [])
        if devices and len(devices) > 0:
            return devices[0].get("communicating", False)

        # Fallback: if we have recent data, battery is communicating
        return True

    @property
    def icon(self) -> str:
        """Return icon based on communication state."""
        if self.is_on:
            return "mdi:access-point-check"
        return "mdi:access-point-off"


class EnvoyConnectedBinarySensor(EnphaseBatteryBinarySensorBase):
    """Envoy Connection Status binary sensor."""

    def __init__(self, coordinator: EnphaseBatteryDataUpdateCoordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, "envoy_connected", "Envoy connecté")
        self._attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
        self._attr_entity_category = "diagnostic"

    @property
    def is_on(self) -> bool | None:
        """Return true if Envoy is connected and responding."""
        if not self.coordinator.data:
            return False

        # If we have any data at all, Envoy is connected
        return True

    @property
    def icon(self) -> str:
        """Return icon based on Envoy connection state."""
        if self.is_on:
            return "mdi:router-wireless"
        return "mdi:router-wireless-off"
