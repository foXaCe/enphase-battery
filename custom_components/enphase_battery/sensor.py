"""Sensor platform for Enphase Battery."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    UnitOfEnergy,
    UnitOfPower,
)
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DEVICE_INFO, DOMAIN, get_battery_device_info
from .coordinator import EnphaseBatteryDataUpdateCoordinator

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from . import EnphaseBatteryConfigEntry

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: EnphaseBatteryConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Enphase Battery sensor platform."""
    coordinator = entry.runtime_data.coordinator

    # System-level sensors (aggregated data for the whole battery system)
    entities: list[SensorEntity] = [
        BatterySOCSensor(coordinator),
        BatteryStateSensor(coordinator),
        BatteryPowerSensor(coordinator),
        BatteryChargePowerSensor(coordinator),
        BatteryDischargePowerSensor(coordinator),
        BatteryAvailableEnergySensor(coordinator),
        BatteryEnergyChargedTodaySensor(coordinator),
        BatteryEnergyDischargedTodaySensor(coordinator),
        BatteryConsumption24hSensor(coordinator),
        BatteryBackupTimeSensor(coordinator),
        # System diagnostic sensors
        BatteryHealthSensor(coordinator),
        BatteryGridModeSensor(coordinator),
        EnvoySerialNumberSensor(coordinator),
        EnvoyFirmwareSensor(coordinator),
    ]

    # Add entities immediately (system-level)
    async_add_entities(entities)

    # Track which batteries have been added (by serial number)
    added_batteries: set[str] = set()

    # Setup listener for individual battery entities (created when data is available)
    def _add_individual_batteries() -> None:
        """Add individual battery sensors when data becomes available."""
        nonlocal added_batteries

        if not coordinator.data:
            return

        devices = coordinator.data.get("devices", [])
        if not devices:
            return

        # Debug: log raw devices data
        _LOGGER.debug("Raw devices data: %s", devices)

        individual_entities: list[SensorEntity] = []
        battery_count = 0

        for idx, device in enumerate(devices):
            serial_num = device.get("serial_num")
            if not serial_num:
                _LOGGER.debug("Device %d has no serial number, skipping: %s", idx, device)
                continue

            # Filter: Only include actual ENCHARGE batteries (have part_num starting with 500-)
            part_num = device.get("part_num", "")
            device_type = device.get("type", device.get("device_type", ""))

            # Skip non-battery devices (ENPOWER controller, etc.)
            # ENCHARGE batteries have part_num like "500-00xxx" or type "ENCHARGE"
            is_battery = (
                (part_num and part_num.startswith("500-"))
                or device_type == "ENCHARGE"
                or "percentFull" in device  # Has battery-specific field
            )

            if not is_battery:
                _LOGGER.debug(
                    "Device %d (%s) is not an ENCHARGE battery, skipping. part_num=%s, type=%s",
                    idx,
                    serial_num,
                    part_num,
                    device_type,
                )
                continue

            # Skip if already added
            if serial_num in added_batteries:
                continue

            battery_count += 1

            _LOGGER.info(
                "Adding individual battery sensors for battery %d (serial: %s)",
                battery_count,
                serial_num,
            )

            # Create individual battery sensors
            individual_entities.extend(
                [
                    IndividualBatteryTemperatureSensor(coordinator, serial_num, part_num, battery_count),
                    IndividualBatteryMaxCellTempSensor(coordinator, serial_num, part_num, battery_count),
                    IndividualBatteryCapacitySensor(coordinator, serial_num, part_num, battery_count),
                    IndividualBatterySerialSensor(coordinator, serial_num, part_num, battery_count),
                    IndividualBatteryFirmwareSensor(coordinator, serial_num, part_num, battery_count),
                    IndividualBatterySOCSensor(coordinator, serial_num, part_num, battery_count),
                    IndividualBatteryGridStateSensor(coordinator, serial_num, part_num, battery_count),
                ]
            )

            # Mark as added
            added_batteries.add(serial_num)

        if individual_entities:
            async_add_entities(individual_entities)
            _LOGGER.info(
                "Added %d individual battery sensors for %d new batteries",
                len(individual_entities),
                len(individual_entities) // 7,  # 7 sensors per battery
            )

    # Register callback to add individual batteries when coordinator updates
    entry.async_on_unload(coordinator.async_add_listener(_add_individual_batteries))

    # Try to add immediately if data is already available
    _add_individual_batteries()


class EnphaseBatterySensorBase(CoordinatorEntity, SensorEntity):
    """Base class for Enphase Battery system-level sensors."""

    # Use __slots__ to reduce memory footprint (one dict per class instead of per instance)
    __slots__ = ("_sensor_type",)

    # Class-level device_info (shared across all system-level entities)
    _attr_device_info = DEVICE_INFO
    _attr_has_entity_name = True

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


class IndividualBatterySensorBase(CoordinatorEntity, SensorEntity):
    """Base class for individual battery sensors."""

    __slots__ = ("_battery_num", "_sensor_type", "_serial_num")

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: EnphaseBatteryDataUpdateCoordinator,
        serial_num: str,
        part_num: str | None,
        battery_num: int,
        sensor_type: str,
        name: str,
    ) -> None:
        """Initialize the individual battery sensor."""
        super().__init__(coordinator)
        self._serial_num = serial_num
        self._battery_num = battery_num
        self._sensor_type = sensor_type
        self._attr_name = name
        self._attr_unique_id = f"{DOMAIN}_battery_{serial_num}_{sensor_type}"
        self._attr_device_info = get_battery_device_info(serial_num, part_num)

    def _get_device_data(self) -> dict | None:
        """Get the device data for this specific battery."""
        if not self.coordinator.data:
            return None
        devices = self.coordinator.data.get("devices", [])
        for device in devices:
            if device.get("serial_num") == self._serial_num:
                return device
        return None


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
        self._attr_options = ["charging", "discharging", "idle", "full", "empty"]

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
        elif power > 10:  # Discharging (positive power, with 10W threshold)
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
        # No state_class for available energy (not cumulative, fluctuates)
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


# =============================================================================
# Individual Battery Sensors (per-battery entities)
# =============================================================================


class IndividualBatteryTemperatureSensor(IndividualBatterySensorBase):
    """Individual battery temperature sensor."""

    def __init__(
        self,
        coordinator: EnphaseBatteryDataUpdateCoordinator,
        serial_num: str,
        part_num: str | None,
        battery_num: int,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, serial_num, part_num, battery_num, "temperature", "Température")
        self._attr_device_class = SensorDeviceClass.TEMPERATURE
        self._attr_native_unit_of_measurement = "°C"
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_icon = "mdi:thermometer"
        self._attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def native_value(self) -> int | None:
        """Return the temperature of this specific battery."""
        device = self._get_device_data()
        if device:
            return device.get("temperature")
        return None


class IndividualBatteryMaxCellTempSensor(IndividualBatterySensorBase):
    """Individual battery max cell temperature sensor."""

    def __init__(
        self,
        coordinator: EnphaseBatteryDataUpdateCoordinator,
        serial_num: str,
        part_num: str | None,
        battery_num: int,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, serial_num, part_num, battery_num, "max_cell_temp", "Température Max Cellule")
        self._attr_device_class = SensorDeviceClass.TEMPERATURE
        self._attr_native_unit_of_measurement = "°C"
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_icon = "mdi:thermometer-alert"
        self._attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def native_value(self) -> int | None:
        """Return the max cell temperature of this specific battery."""
        device = self._get_device_data()
        if device:
            return device.get("maxCellTemp")
        return None


class IndividualBatteryCapacitySensor(IndividualBatterySensorBase):
    """Individual battery capacity sensor."""

    def __init__(
        self,
        coordinator: EnphaseBatteryDataUpdateCoordinator,
        serial_num: str,
        part_num: str | None,
        battery_num: int,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, serial_num, part_num, battery_num, "capacity", "Capacité")
        self._attr_device_class = SensorDeviceClass.ENERGY_STORAGE
        self._attr_native_unit_of_measurement = UnitOfEnergy.WATT_HOUR
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_icon = "mdi:battery-high"
        self._attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def native_value(self) -> int | None:
        """Return the capacity of this specific battery."""
        device = self._get_device_data()
        if device:
            return device.get("encharge_capacity")
        return None


class IndividualBatterySerialSensor(IndividualBatterySensorBase):
    """Individual battery serial number sensor."""

    def __init__(
        self,
        coordinator: EnphaseBatteryDataUpdateCoordinator,
        serial_num: str,
        part_num: str | None,
        battery_num: int,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, serial_num, part_num, battery_num, "serial", "Numéro de Série")
        self._attr_icon = "mdi:identifier"
        self._attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def native_value(self) -> str | None:
        """Return the serial number of this specific battery."""
        return self._serial_num


class IndividualBatteryFirmwareSensor(IndividualBatterySensorBase):
    """Individual battery firmware version sensor."""

    def __init__(
        self,
        coordinator: EnphaseBatteryDataUpdateCoordinator,
        serial_num: str,
        part_num: str | None,
        battery_num: int,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, serial_num, part_num, battery_num, "firmware", "Firmware")
        self._attr_icon = "mdi:chip"
        self._attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def native_value(self) -> str | None:
        """Return the firmware version of this specific battery."""
        device = self._get_device_data()
        if device:
            return device.get("img_pnum_running")
        return None


class IndividualBatterySOCSensor(IndividualBatterySensorBase):
    """Individual battery state of charge sensor."""

    def __init__(
        self,
        coordinator: EnphaseBatteryDataUpdateCoordinator,
        serial_num: str,
        part_num: str | None,
        battery_num: int,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, serial_num, part_num, battery_num, "soc", "État de charge")
        self._attr_device_class = SensorDeviceClass.BATTERY
        self._attr_native_unit_of_measurement = PERCENTAGE
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_icon = "mdi:battery"

    @property
    def native_value(self) -> int | None:
        """Return the SOC of this specific battery."""
        device = self._get_device_data()
        if device:
            # Try percentFull first, fallback to other possible fields
            return device.get("percentFull") or device.get("soc")
        return None

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


class IndividualBatteryGridStateSensor(IndividualBatterySensorBase):
    """Individual battery grid state sensor."""

    def __init__(
        self,
        coordinator: EnphaseBatteryDataUpdateCoordinator,
        serial_num: str,
        part_num: str | None,
        battery_num: int,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, serial_num, part_num, battery_num, "grid_state", "État Réseau")
        self._attr_icon = "mdi:transmission-tower"
        self._attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def native_value(self) -> str | None:
        """Return the grid state of this specific battery."""
        device = self._get_device_data()
        if device:
            return device.get("reported_enc_grid_state", "unknown")
        return None
