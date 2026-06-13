"""Sensor platform for Enphase Battery."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, ClassVar

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    EntityCategory,
    UnitOfEnergy,
    UnitOfPower,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import BatteryDevice
from .const import DEVICE_INFO, get_battery_device_info
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


class EnphaseBatterySensorBase(CoordinatorEntity[EnphaseBatteryDataUpdateCoordinator], SensorEntity):
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
        translation_key: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._sensor_type = sensor_type
        self._attr_translation_key = translation_key
        self._attr_unique_id = f"{coordinator.unique_id_prefix}_{sensor_type}"


class IndividualBatterySensorBase(CoordinatorEntity[EnphaseBatteryDataUpdateCoordinator], SensorEntity):
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
        translation_key: str,
    ) -> None:
        """Initialize the individual battery sensor."""
        super().__init__(coordinator)
        self._serial_num = serial_num
        self._battery_num = battery_num
        self._sensor_type = sensor_type
        self._attr_translation_key = translation_key
        self._attr_unique_id = f"{coordinator.unique_id_prefix}_battery_{serial_num}_{sensor_type}"
        self._attr_device_info = get_battery_device_info(serial_num, part_num)

    def _get_device_data(self) -> BatteryDevice | None:
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
        super().__init__(coordinator, "soc", "battery_soc")
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
        super().__init__(coordinator, "state", "battery_state")
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


class BatteryPowerSensor(EnphaseBatterySensorBase):
    """Battery Power sensor (net power, - = charging, + = discharging)."""

    def __init__(self, coordinator: EnphaseBatteryDataUpdateCoordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, "power", "battery_power")
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
        super().__init__(coordinator, "charge_power", "battery_charge_power")
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
        super().__init__(coordinator, "discharge_power", "battery_discharge_power")
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
        super().__init__(coordinator, "available_energy", "battery_available_energy")
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
        super().__init__(coordinator, "energy_charged_today", "battery_energy_charged")
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
        super().__init__(coordinator, "energy_discharged_today", "battery_energy_discharged")
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
        super().__init__(coordinator, "consumption_24h", "battery_consumption_24h")
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
        super().__init__(coordinator, "backup_time", "battery_backup_time")
        self._attr_native_unit_of_measurement = UnitOfTime.MINUTES
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
        super().__init__(coordinator, "health", "battery_health")
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

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options: ClassVar[list[str]] = ["grid_tied", "grid_forming", "unknown"]  # type: ignore[misc]

    def __init__(self, coordinator: EnphaseBatteryDataUpdateCoordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, "grid_mode", "battery_grid_mode")
        self._attr_icon = "mdi:transmission-tower"
        self._attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def native_value(self) -> str | None:
        """Return the state of the sensor."""
        if not self.coordinator.data:
            return None
        devices = self.coordinator.data.get("devices", [])
        if devices and len(devices) > 0:
            raw = devices[0].get("reported_enc_grid_state", "unknown")
            return raw.replace("-", "_")
        status = self.coordinator.data.get("status")
        return status.replace("-", "_") if status else None


class EnvoySerialNumberSensor(EnphaseBatterySensorBase):
    """Envoy Serial Number sensor."""

    def __init__(self, coordinator: EnphaseBatteryDataUpdateCoordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, "envoy_serial", "envoy_serial")
        self._attr_icon = "mdi:identifier"
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_entity_registry_enabled_default = False

    @property
    def native_value(self) -> str | None:
        """Return the state of the sensor."""
        return self.coordinator.envoy_serial


class EnvoyFirmwareSensor(EnphaseBatterySensorBase):
    """Envoy Firmware Version sensor."""

    def __init__(self, coordinator: EnphaseBatteryDataUpdateCoordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, "envoy_firmware", "envoy_firmware")
        self._attr_icon = "mdi:chip"
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_entity_registry_enabled_default = False

    @property
    def native_value(self) -> str | None:
        """Return the state of the sensor."""
        return self.coordinator.envoy_firmware


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
        super().__init__(coordinator, serial_num, part_num, battery_num, "temperature", "individual_temperature")
        self._attr_device_class = SensorDeviceClass.TEMPERATURE
        self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_icon = "mdi:thermometer"
        self._attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def native_value(self) -> float | None:
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
        super().__init__(coordinator, serial_num, part_num, battery_num, "max_cell_temp", "individual_max_cell_temp")
        self._attr_device_class = SensorDeviceClass.TEMPERATURE
        self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_icon = "mdi:thermometer-alert"
        self._attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def native_value(self) -> float | None:
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
        super().__init__(coordinator, serial_num, part_num, battery_num, "capacity", "individual_capacity")
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
        super().__init__(coordinator, serial_num, part_num, battery_num, "serial", "individual_serial")
        self._attr_icon = "mdi:identifier"
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_entity_registry_enabled_default = False

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
        super().__init__(coordinator, serial_num, part_num, battery_num, "firmware", "individual_firmware")
        self._attr_icon = "mdi:chip"
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_entity_registry_enabled_default = False

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
        super().__init__(coordinator, serial_num, part_num, battery_num, "soc", "individual_soc")
        self._attr_device_class = SensorDeviceClass.BATTERY
        self._attr_native_unit_of_measurement = PERCENTAGE
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_icon = "mdi:battery"

    @property
    def native_value(self) -> float | None:
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
        super().__init__(coordinator, serial_num, part_num, battery_num, "grid_state", "individual_grid_state")
        self._attr_icon = "mdi:transmission-tower"
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_device_class = SensorDeviceClass.ENUM
        self._attr_options = ["grid_tied", "grid_forming", "unknown"]

    @property
    def native_value(self) -> str | None:
        """Return the grid state of this specific battery."""
        device = self._get_device_data()
        if device:
            raw = device.get("reported_enc_grid_state", "unknown")
            return raw.replace("-", "_")
        return None
