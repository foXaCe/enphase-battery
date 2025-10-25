"""Sensor platform for Enphase Battery."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    UnitOfEnergy,
    UnitOfPower,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
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
    """Set up Enphase Battery sensor platform."""
    coordinator: EnphaseBatteryDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities = [
        BatterySOCSensor(coordinator),
        BatteryStateSensor(coordinator),  # NEW: État batterie avec icône dynamique
        BatteryPowerSensor(coordinator),
        BatteryChargePowerSensor(coordinator),
        BatteryDischargePowerSensor(coordinator),
        BatteryAvailableEnergySensor(coordinator),
        BatteryEnergyChargedTodaySensor(coordinator),
        BatteryEnergyDischargedTodaySensor(coordinator),
        BatteryConsumption24hSensor(coordinator),
        BatteryBackupTimeSensor(coordinator),
        # Diagnostic sensors
        BatteryTemperatureSensor(coordinator),
        BatteryMaxCellTempSensor(coordinator),
        BatteryHealthSensor(coordinator),
        BatterySerialNumberSensor(coordinator),
        BatteryPartNumberSensor(coordinator),
        BatteryFirmwareSensor(coordinator),
        BatteryCapacitySensor(coordinator),
        BatteryGridModeSensor(coordinator),
        EnvoySerialNumberSensor(coordinator),
        EnvoyFirmwareSensor(coordinator),
    ]

    async_add_entities(entities)


class EnphaseBatterySensorBase(CoordinatorEntity, SensorEntity):
    """Base class for Enphase Battery sensors."""

    def __init__(
        self,
        coordinator: EnphaseBatteryDataUpdateCoordinator,
        sensor_type: str,
        name: str,
    ) -> None:
        """Initialize the sensor."""
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


class BatterySOCSensor(EnphaseBatterySensorBase):
    """Battery State of Charge sensor."""

    def __init__(self, coordinator: EnphaseBatteryDataUpdateCoordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, "soc", "État de charge")
        self._attr_device_class = SensorDeviceClass.BATTERY
        self._attr_native_unit_of_measurement = PERCENTAGE
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_icon = "mdi:battery"

    @property
    def native_value(self) -> int | None:
        """Return the state of the sensor."""
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get("soc")

    @property
    def icon(self) -> str:
        """Return icon based on battery level."""
        soc = self.native_value
        if soc is None:
            return "mdi:battery-unknown"

        if soc >= 90:
            return "mdi:battery"
        elif soc >= 70:
            return "mdi:battery-70"
        elif soc >= 50:
            return "mdi:battery-50"
        elif soc >= 30:
            return "mdi:battery-30"
        elif soc >= 10:
            return "mdi:battery-10"
        else:
            return "mdi:battery-alert"


class BatteryStateSensor(EnphaseBatterySensorBase):
    """Battery State sensor with charging/discharging/idle states."""

    def __init__(self, coordinator: EnphaseBatteryDataUpdateCoordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, "state", "État Batterie")
        self._attr_device_class = SensorDeviceClass.ENUM
        self._attr_options = [
            "charging",
            "discharging",
            "idle",
            "full",
            "empty"
        ]

    @property
    def native_value(self) -> str | None:
        """Return the current battery state."""
        if not self.coordinator.data:
            return None

        soc = self.coordinator.data.get("soc", 0)
        power = self.coordinator.data.get("power", 0)

        # Determine state based on SOC and power
        if soc >= 100:
            return "full"
        elif soc <= 5:
            return "empty"
        elif power < -10:  # Charging (negative power, with 10W threshold)
            return "charging"
        elif power > 10:   # Discharging (positive power, with 10W threshold)
            return "discharging"
        else:
            return "idle"

    @property
    def icon(self) -> str:
        """Return icon based on battery state."""
        state = self.native_value
        soc = self.coordinator.data.get("soc", 0) if self.coordinator.data else 0

        if state == "charging":
            # Charging icons based on SOC
            if soc >= 90:
                return "mdi:battery-charging-100"
            elif soc >= 80:
                return "mdi:battery-charging-90"
            elif soc >= 70:
                return "mdi:battery-charging-80"
            elif soc >= 60:
                return "mdi:battery-charging-70"
            elif soc >= 50:
                return "mdi:battery-charging-60"
            elif soc >= 40:
                return "mdi:battery-charging-50"
            elif soc >= 30:
                return "mdi:battery-charging-40"
            elif soc >= 20:
                return "mdi:battery-charging-30"
            else:
                return "mdi:battery-charging-20"
        elif state == "discharging":
            # Discharging (arrow down) icons
            if soc >= 90:
                return "mdi:battery-arrow-down"
            elif soc >= 70:
                return "mdi:battery-70"
            elif soc >= 50:
                return "mdi:battery-50"
            elif soc >= 30:
                return "mdi:battery-30"
            elif soc >= 10:
                return "mdi:battery-10"
            else:
                return "mdi:battery-alert"
        elif state == "full":
            return "mdi:battery"
        elif state == "empty":
            return "mdi:battery-alert-variant-outline"
        else:  # idle
            if soc >= 90:
                return "mdi:battery-heart"
            elif soc >= 70:
                return "mdi:battery-70"
            elif soc >= 50:
                return "mdi:battery-50"
            else:
                return "mdi:battery-30"

    @property
    def translation_key(self) -> str:
        """Return translation key for state values."""
        return "battery_state"


class BatteryPowerSensor(EnphaseBatterySensorBase):
    """Battery Power sensor (net power, - = charging, + = discharging)."""

    def __init__(self, coordinator: EnphaseBatteryDataUpdateCoordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, "power", "Puissance")
        self._attr_device_class = SensorDeviceClass.POWER
        self._attr_native_unit_of_measurement = UnitOfPower.WATT
        self._attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self) -> int | None:
        """Return the state of the sensor."""
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get("power")

    @property
    def icon(self) -> str:
        """Return icon based on power direction."""
        power = self.native_value
        if power is None or power == 0:
            return "mdi:battery"
        elif power < 0:
            return "mdi:battery-charging"
        else:
            return "mdi:battery-arrow-down"


class BatteryChargePowerSensor(EnphaseBatterySensorBase):
    """Battery Charging Power sensor."""

    def __init__(self, coordinator: EnphaseBatteryDataUpdateCoordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, "charge_power", "Puissance de charge")
        self._attr_device_class = SensorDeviceClass.POWER
        self._attr_native_unit_of_measurement = UnitOfPower.WATT
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_icon = "mdi:battery-charging"

    @property
    def native_value(self) -> int | None:
        """Return the state of the sensor."""
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get("charge_power", 0)


class BatteryDischargePowerSensor(EnphaseBatterySensorBase):
    """Battery Discharging Power sensor."""

    def __init__(self, coordinator: EnphaseBatteryDataUpdateCoordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, "discharge_power", "Puissance de décharge")
        self._attr_device_class = SensorDeviceClass.POWER
        self._attr_native_unit_of_measurement = UnitOfPower.WATT
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_icon = "mdi:battery-arrow-down"

    @property
    def native_value(self) -> int | None:
        """Return the state of the sensor."""
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get("discharge_power", 0)


class BatteryAvailableEnergySensor(EnphaseBatterySensorBase):
    """Battery Available Energy sensor."""

    def __init__(self, coordinator: EnphaseBatteryDataUpdateCoordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, "available_energy", "Énergie disponible de la batterie")
        self._attr_device_class = SensorDeviceClass.ENERGY
        self._attr_native_unit_of_measurement = UnitOfEnergy.WATT_HOUR
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_icon = "mdi:battery-heart-variant"

    @property
    def native_value(self) -> int | None:
        """Return the state of the sensor."""
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get("available_energy", 0)


class BatteryEnergyChargedTodaySensor(EnphaseBatterySensorBase):
    """Battery Energy Charged Today sensor."""

    def __init__(self, coordinator: EnphaseBatteryDataUpdateCoordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, "energy_charged_today", "Énergie chargée aujourd'hui")
        self._attr_device_class = SensorDeviceClass.ENERGY
        self._attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
        self._attr_state_class = SensorStateClass.TOTAL_INCREASING
        self._attr_icon = "mdi:battery-plus"

    @property
    def native_value(self) -> float | None:
        """Return the state of the sensor."""
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get("energy_charged_today")


class BatteryEnergyDischargedTodaySensor(EnphaseBatterySensorBase):
    """Battery Energy Discharged Today sensor."""

    def __init__(self, coordinator: EnphaseBatteryDataUpdateCoordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, "energy_discharged_today", "Énergie déchargée aujourd'hui")
        self._attr_device_class = SensorDeviceClass.ENERGY
        self._attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
        self._attr_state_class = SensorStateClass.TOTAL_INCREASING
        self._attr_icon = "mdi:battery-minus"

    @property
    def native_value(self) -> float | None:
        """Return the state of the sensor."""
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get("energy_discharged_today")


class BatteryConsumption24hSensor(EnphaseBatterySensorBase):
    """Battery Consumption Last 24h sensor."""

    def __init__(self, coordinator: EnphaseBatteryDataUpdateCoordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, "consumption_24h", "Consommation 24h")
        # Note: device_class ENERGY requires TOTAL/TOTAL_INCREASING, not MEASUREMENT
        # Since this is a 24h rolling window, we use MEASUREMENT without device_class
        self._attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_icon = "mdi:home-lightning-bolt"

    @property
    def native_value(self) -> float | None:
        """Return the state of the sensor."""
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get("consumption_24h")


class BatteryBackupTimeSensor(EnphaseBatterySensorBase):
    """Estimated Battery Backup Time sensor."""

    def __init__(self, coordinator: EnphaseBatteryDataUpdateCoordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, "backup_time", "Temps de backup estimé")
        self._attr_native_unit_of_measurement = "min"
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_icon = "mdi:clock-outline"

    @property
    def native_value(self) -> int | None:
        """Return the state of the sensor."""
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get("estimated_backup_time")


# Diagnostic Sensors

class BatteryTemperatureSensor(EnphaseBatterySensorBase):
    """Battery Temperature sensor."""

    def __init__(self, coordinator: EnphaseBatteryDataUpdateCoordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, "temperature", "Température Batterie")
        self._attr_device_class = SensorDeviceClass.TEMPERATURE
        self._attr_native_unit_of_measurement = "°C"
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_icon = "mdi:thermometer"
        self._attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def native_value(self) -> int | None:
        """Return the state of the sensor."""
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get("temperature")


class BatteryMaxCellTempSensor(EnphaseBatterySensorBase):
    """Battery Max Cell Temperature sensor."""

    def __init__(self, coordinator: EnphaseBatteryDataUpdateCoordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, "max_cell_temp", "Température Max Cellule")
        self._attr_device_class = SensorDeviceClass.TEMPERATURE
        self._attr_native_unit_of_measurement = "°C"
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_icon = "mdi:thermometer-alert"
        self._attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def native_value(self) -> int | None:
        """Return the state of the sensor."""
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get("max_cell_temp")


class BatteryHealthSensor(EnphaseBatterySensorBase):
    """Battery State of Health (SOH) sensor."""

    def __init__(self, coordinator: EnphaseBatteryDataUpdateCoordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, "health", "État de Santé Batterie")
        self._attr_native_unit_of_measurement = PERCENTAGE
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_icon = "mdi:heart-pulse"
        self._attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def native_value(self) -> int | None:
        """Return the state of the sensor."""
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get("soh", 100)


class BatterySerialNumberSensor(EnphaseBatterySensorBase):
    """Battery Serial Number sensor."""

    def __init__(self, coordinator: EnphaseBatteryDataUpdateCoordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, "battery_serial", "Numéro de Série Batterie")
        self._attr_icon = "mdi:identifier"
        self._attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def native_value(self) -> str | None:
        """Return the state of the sensor."""
        if not self.coordinator.data:
            return None
        devices = self.coordinator.data.get("devices", [])
        if devices and len(devices) > 0:
            return devices[0].get("serial_num")
        return None


class BatteryPartNumberSensor(EnphaseBatterySensorBase):
    """Battery Part Number sensor."""

    def __init__(self, coordinator: EnphaseBatteryDataUpdateCoordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, "battery_part_number", "Référence Batterie")
        self._attr_icon = "mdi:barcode"
        self._attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def native_value(self) -> str | None:
        """Return the state of the sensor."""
        if not self.coordinator.data:
            return None
        devices = self.coordinator.data.get("devices", [])
        if devices and len(devices) > 0:
            return devices[0].get("part_num")
        return None


class BatteryFirmwareSensor(EnphaseBatterySensorBase):
    """Battery Firmware Version sensor."""

    def __init__(self, coordinator: EnphaseBatteryDataUpdateCoordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, "battery_firmware", "Firmware Batterie")
        self._attr_icon = "mdi:chip"
        self._attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def native_value(self) -> str | None:
        """Return the state of the sensor."""
        if not self.coordinator.data:
            return None
        devices = self.coordinator.data.get("devices", [])
        if devices and len(devices) > 0:
            return devices[0].get("img_pnum_running")
        return None


class BatteryCapacitySensor(EnphaseBatterySensorBase):
    """Battery Nominal Capacity sensor."""

    def __init__(self, coordinator: EnphaseBatteryDataUpdateCoordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, "battery_capacity", "Capacité Nominale Batterie")
        self._attr_device_class = SensorDeviceClass.ENERGY_STORAGE
        self._attr_native_unit_of_measurement = UnitOfEnergy.WATT_HOUR
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_icon = "mdi:battery-high"
        self._attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def native_value(self) -> int | None:
        """Return the state of the sensor."""
        if not self.coordinator.data:
            return None
        devices = self.coordinator.data.get("devices", [])
        if devices and len(devices) > 0:
            return devices[0].get("encharge_capacity")
        return self.coordinator.data.get("max_capacity")


class BatteryGridModeSensor(EnphaseBatterySensorBase):
    """Battery Grid Mode sensor."""

    def __init__(self, coordinator: EnphaseBatteryDataUpdateCoordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, "grid_mode", "Mode Réseau")
        self._attr_icon = "mdi:transmission-tower"
        self._attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def native_value(self) -> str | None:
        """Return the state of the sensor."""
        if not self.coordinator.data:
            return None
        devices = self.coordinator.data.get("devices", [])
        if devices and len(devices) > 0:
            return devices[0].get("reported_enc_grid_state", "unknown")
        return self.coordinator.data.get("status")


class EnvoySerialNumberSensor(EnphaseBatterySensorBase):
    """Envoy Serial Number sensor."""

    def __init__(self, coordinator: EnphaseBatteryDataUpdateCoordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, "envoy_serial", "Numéro de Série Envoy")
        self._attr_icon = "mdi:identifier"
        self._attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def native_value(self) -> str | None:
        """Return the state of the sensor."""
        # Get from coordinator's local_api or api
        if self.coordinator.is_local_mode and self.coordinator.local_api:
            return self.coordinator.local_api._serial_number
        return None


class EnvoyFirmwareSensor(EnphaseBatterySensorBase):
    """Envoy Firmware Version sensor."""

    def __init__(self, coordinator: EnphaseBatteryDataUpdateCoordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, "envoy_firmware", "Firmware Envoy")
        self._attr_icon = "mdi:chip"
        self._attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def native_value(self) -> str | None:
        """Return the state of the sensor."""
        # Get from coordinator's local_api or api
        if self.coordinator.is_local_mode and self.coordinator.local_api:
            return self.coordinator.local_api._firmware_version
        return None
