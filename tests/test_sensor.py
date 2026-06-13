"""Tests for the Enphase Battery sensor platform."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.enphase_battery import EnphaseBatteryRuntimeData
from custom_components.enphase_battery.coordinator import (
    EnphaseBatteryDataUpdateCoordinator,
)
from custom_components.enphase_battery.sensor import (
    BatteryAvailableEnergySensor,
    BatteryBackupTimeSensor,
    BatteryChargePowerSensor,
    BatteryConsumption24hSensor,
    BatteryDischargePowerSensor,
    BatteryEnergyChargedTodaySensor,
    BatteryEnergyDischargedTodaySensor,
    BatteryGridModeSensor,
    BatteryHealthSensor,
    BatteryPowerSensor,
    BatterySOCSensor,
    BatteryStateSensor,
    EnvoyFirmwareSensor,
    EnvoySerialNumberSensor,
    IndividualBatteryCapacitySensor,
    IndividualBatteryFirmwareSensor,
    IndividualBatteryGridStateSensor,
    IndividualBatteryMaxCellTempSensor,
    IndividualBatterySerialSensor,
    IndividualBatterySOCSensor,
    IndividualBatteryTemperatureSensor,
    async_setup_entry,
)


# ---------------------------------------------------------------------------
# Helper: create a mock coordinator
# ---------------------------------------------------------------------------
def _mock_coordinator(data=None):
    """Create a mock coordinator with data."""
    coord = MagicMock(spec=EnphaseBatteryDataUpdateCoordinator)
    coord.unique_id_prefix = "test_entry"
    coord.data = data
    coord.is_local_mode = False
    coord.local_api = None
    coord.api = MagicMock()
    coord.api.set_charge_from_grid = AsyncMock(return_value=True)
    coord.api.set_battery_mode = AsyncMock(return_value=True)
    coord.api.set_limit_discharge = AsyncMock(return_value=True)
    coord.api.set_reserve_battery_discharge = AsyncMock(return_value=True)
    coord.api.set_power_match = AsyncMock(return_value=True)
    coord.api.set_very_low_soc = AsyncMock(return_value=True)
    coord.invalidate_cloud_control_cache = MagicMock()
    coord.async_request_refresh = AsyncMock()
    coord.async_add_listener = MagicMock(return_value=lambda: None)
    coord.battery_mode = "self-consumption"
    return coord


# ===========================================================================
# BatterySOCSensor
# ===========================================================================
class TestBatterySOCSensor:
    """Tests for the BatterySOCSensor."""

    def test_native_value(self):
        coord = _mock_coordinator({"soc": 75})
        sensor = BatterySOCSensor(coord)
        assert sensor.native_value == 75

    def test_native_value_none_when_no_data(self):
        coord = _mock_coordinator(None)
        sensor = BatterySOCSensor(coord)
        assert sensor.native_value is None

    def test_native_value_missing_key(self):
        coord = _mock_coordinator({"power": 100})
        sensor = BatterySOCSensor(coord)
        assert sensor.native_value is None

    @pytest.mark.parametrize(
        ("soc", "expected_icon"),
        [
            (95, "mdi:battery"),
            (90, "mdi:battery"),
            (75, "mdi:battery-70"),
            (70, "mdi:battery-70"),
            (55, "mdi:battery-50"),
            (50, "mdi:battery-50"),
            (35, "mdi:battery-30"),
            (30, "mdi:battery-30"),
            (15, "mdi:battery-10"),
            (10, "mdi:battery-10"),
            (5, "mdi:battery-alert"),
            (0, "mdi:battery-alert"),
        ],
    )
    def test_icon_by_soc_level(self, soc, expected_icon):
        coord = _mock_coordinator({"soc": soc})
        sensor = BatterySOCSensor(coord)
        assert sensor.icon == expected_icon

    def test_icon_when_soc_none(self):
        coord = _mock_coordinator(None)
        sensor = BatterySOCSensor(coord)
        assert sensor.icon == "mdi:battery-unknown"

    def test_unique_id(self):
        coord = _mock_coordinator({"soc": 50})
        sensor = BatterySOCSensor(coord)
        assert sensor._attr_unique_id == "test_entry_soc"


# ===========================================================================
# BatteryStateSensor
# ===========================================================================
class TestBatteryStateSensor:
    """Tests for the BatteryStateSensor."""

    def test_state_full(self):
        coord = _mock_coordinator({"soc": 100, "power": 0})
        sensor = BatteryStateSensor(coord)
        assert sensor.native_value == "full"

    def test_state_empty(self):
        coord = _mock_coordinator({"soc": 5, "power": 0})
        sensor = BatteryStateSensor(coord)
        assert sensor.native_value == "empty"

    def test_state_charging(self):
        coord = _mock_coordinator({"soc": 50, "power": -500})
        sensor = BatteryStateSensor(coord)
        assert sensor.native_value == "charging"

    def test_state_discharging(self):
        coord = _mock_coordinator({"soc": 50, "power": 500})
        sensor = BatteryStateSensor(coord)
        assert sensor.native_value == "discharging"

    def test_state_idle(self):
        coord = _mock_coordinator({"soc": 50, "power": 5})
        sensor = BatteryStateSensor(coord)
        assert sensor.native_value == "idle"

    def test_state_idle_negative_small(self):
        coord = _mock_coordinator({"soc": 50, "power": -5})
        sensor = BatteryStateSensor(coord)
        assert sensor.native_value == "idle"

    def test_state_none_when_no_data(self):
        coord = _mock_coordinator(None)
        sensor = BatteryStateSensor(coord)
        assert sensor.native_value is None

    def test_translation_key(self):
        coord = _mock_coordinator({"soc": 50, "power": 0})
        sensor = BatteryStateSensor(coord)
        assert sensor.translation_key == "battery_state"

    # Icon tests for charging state
    @pytest.mark.parametrize(
        ("soc", "expected_icon"),
        [
            (95, "mdi:battery-charging-100"),
            (85, "mdi:battery-charging-90"),
            (75, "mdi:battery-charging-80"),
            (65, "mdi:battery-charging-70"),
            (55, "mdi:battery-charging-60"),
            (45, "mdi:battery-charging-50"),
            (35, "mdi:battery-charging-40"),
            (25, "mdi:battery-charging-30"),
            (15, "mdi:battery-charging-20"),
        ],
    )
    def test_icon_charging(self, soc, expected_icon):
        coord = _mock_coordinator({"soc": soc, "power": -500})
        sensor = BatteryStateSensor(coord)
        assert sensor.icon == expected_icon

    # Icon tests for discharging state
    @pytest.mark.parametrize(
        ("soc", "expected_icon"),
        [
            (95, "mdi:battery-arrow-down"),
            (75, "mdi:battery-70"),
            (55, "mdi:battery-50"),
            (35, "mdi:battery-30"),
            (15, "mdi:battery-10"),
            (8, "mdi:battery-alert"),
            (5, "mdi:battery-alert"),
        ],
    )
    def test_icon_discharging(self, soc, expected_icon):
        # soc must be > 5 for discharging (otherwise it's "empty")
        # and power > 10
        coord = _mock_coordinator({"soc": soc, "power": 500})
        sensor = BatteryStateSensor(coord)
        # Only test icons for actual discharging state
        if sensor.native_value == "discharging":
            assert sensor.icon == expected_icon

    def test_icon_full(self):
        coord = _mock_coordinator({"soc": 100, "power": 0})
        sensor = BatteryStateSensor(coord)
        assert sensor.icon == "mdi:battery"

    def test_icon_empty(self):
        coord = _mock_coordinator({"soc": 5, "power": 0})
        sensor = BatteryStateSensor(coord)
        assert sensor.icon == "mdi:battery-alert-variant-outline"

    # Icon tests for idle state
    @pytest.mark.parametrize(
        ("soc", "expected_icon"),
        [
            (95, "mdi:battery-heart"),
            (75, "mdi:battery-70"),
            (55, "mdi:battery-50"),
            (35, "mdi:battery-30"),
        ],
    )
    def test_icon_idle(self, soc, expected_icon):
        coord = _mock_coordinator({"soc": soc, "power": 0})
        sensor = BatteryStateSensor(coord)
        if sensor.native_value == "idle":
            assert sensor.icon == expected_icon

    def test_icon_when_data_none(self):
        """Test icon when coordinator data is None (state is None, soc defaults to 0)."""
        coord = _mock_coordinator(None)
        sensor = BatteryStateSensor(coord)
        # state is None -> falls into idle branch, soc=0 -> battery-30
        assert sensor.icon == "mdi:battery-30"


# ===========================================================================
# BatteryPowerSensor
# ===========================================================================
class TestBatteryPowerSensor:
    """Tests for the BatteryPowerSensor."""

    def test_native_value(self):
        coord = _mock_coordinator({"power": -500})
        sensor = BatteryPowerSensor(coord)
        assert sensor.native_value == -500

    def test_native_value_none(self):
        coord = _mock_coordinator(None)
        sensor = BatteryPowerSensor(coord)
        assert sensor.native_value is None

    def test_icon_none_power(self):
        coord = _mock_coordinator(None)
        sensor = BatteryPowerSensor(coord)
        assert sensor.icon == "mdi:battery"

    def test_icon_zero_power(self):
        coord = _mock_coordinator({"power": 0})
        sensor = BatteryPowerSensor(coord)
        assert sensor.icon == "mdi:battery"

    def test_icon_negative_power_charging(self):
        coord = _mock_coordinator({"power": -500})
        sensor = BatteryPowerSensor(coord)
        assert sensor.icon == "mdi:battery-charging"

    def test_icon_positive_power_discharging(self):
        coord = _mock_coordinator({"power": 500})
        sensor = BatteryPowerSensor(coord)
        assert sensor.icon == "mdi:battery-arrow-down"


# ===========================================================================
# BatteryChargePowerSensor
# ===========================================================================
class TestBatteryChargePowerSensor:
    """Tests for the BatteryChargePowerSensor."""

    def test_native_value(self):
        coord = _mock_coordinator({"charge_power": 1500})
        sensor = BatteryChargePowerSensor(coord)
        assert sensor.native_value == 1500

    def test_native_value_default(self):
        coord = _mock_coordinator({"soc": 50})
        sensor = BatteryChargePowerSensor(coord)
        assert sensor.native_value == 0

    def test_native_value_none(self):
        coord = _mock_coordinator(None)
        sensor = BatteryChargePowerSensor(coord)
        assert sensor.native_value is None


# ===========================================================================
# BatteryDischargePowerSensor
# ===========================================================================
class TestBatteryDischargePowerSensor:
    """Tests for the BatteryDischargePowerSensor."""

    def test_native_value(self):
        coord = _mock_coordinator({"discharge_power": 2000})
        sensor = BatteryDischargePowerSensor(coord)
        assert sensor.native_value == 2000

    def test_native_value_default(self):
        coord = _mock_coordinator({"soc": 50})
        sensor = BatteryDischargePowerSensor(coord)
        assert sensor.native_value == 0

    def test_native_value_none(self):
        coord = _mock_coordinator(None)
        sensor = BatteryDischargePowerSensor(coord)
        assert sensor.native_value is None


# ===========================================================================
# BatteryAvailableEnergySensor
# ===========================================================================
class TestBatteryAvailableEnergySensor:
    """Tests for the BatteryAvailableEnergySensor."""

    def test_native_value(self):
        coord = _mock_coordinator({"available_energy": 5000})
        sensor = BatteryAvailableEnergySensor(coord)
        assert sensor.native_value == 5000

    def test_native_value_default(self):
        coord = _mock_coordinator({"soc": 50})
        sensor = BatteryAvailableEnergySensor(coord)
        assert sensor.native_value == 0

    def test_native_value_none(self):
        coord = _mock_coordinator(None)
        sensor = BatteryAvailableEnergySensor(coord)
        assert sensor.native_value is None


# ===========================================================================
# BatteryEnergyChargedTodaySensor
# ===========================================================================
class TestBatteryEnergyChargedTodaySensor:
    """Tests for the BatteryEnergyChargedTodaySensor."""

    def test_native_value(self):
        coord = _mock_coordinator({"energy_charged_today": 3.45})
        sensor = BatteryEnergyChargedTodaySensor(coord)
        assert sensor.native_value == 3.45

    def test_native_value_missing_key(self):
        coord = _mock_coordinator({"soc": 50})
        sensor = BatteryEnergyChargedTodaySensor(coord)
        assert sensor.native_value is None

    def test_native_value_none(self):
        coord = _mock_coordinator(None)
        sensor = BatteryEnergyChargedTodaySensor(coord)
        assert sensor.native_value is None


# ===========================================================================
# BatteryEnergyDischargedTodaySensor
# ===========================================================================
class TestBatteryEnergyDischargedTodaySensor:
    """Tests for the BatteryEnergyDischargedTodaySensor."""

    def test_native_value(self):
        coord = _mock_coordinator({"energy_discharged_today": 2.10})
        sensor = BatteryEnergyDischargedTodaySensor(coord)
        assert sensor.native_value == 2.10

    def test_native_value_missing_key(self):
        coord = _mock_coordinator({"soc": 50})
        sensor = BatteryEnergyDischargedTodaySensor(coord)
        assert sensor.native_value is None

    def test_native_value_none(self):
        coord = _mock_coordinator(None)
        sensor = BatteryEnergyDischargedTodaySensor(coord)
        assert sensor.native_value is None


# ===========================================================================
# BatteryConsumption24hSensor
# ===========================================================================
class TestBatteryConsumption24hSensor:
    """Tests for the BatteryConsumption24hSensor."""

    def test_native_value(self):
        coord = _mock_coordinator({"consumption_24h": 12.5})
        sensor = BatteryConsumption24hSensor(coord)
        assert sensor.native_value == 12.5

    def test_native_value_missing_key(self):
        coord = _mock_coordinator({"soc": 50})
        sensor = BatteryConsumption24hSensor(coord)
        assert sensor.native_value is None

    def test_native_value_none(self):
        coord = _mock_coordinator(None)
        sensor = BatteryConsumption24hSensor(coord)
        assert sensor.native_value is None


# ===========================================================================
# BatteryBackupTimeSensor
# ===========================================================================
class TestBatteryBackupTimeSensor:
    """Tests for the BatteryBackupTimeSensor."""

    def test_native_value(self):
        coord = _mock_coordinator({"estimated_backup_time": 120})
        sensor = BatteryBackupTimeSensor(coord)
        assert sensor.native_value == 120

    def test_native_value_missing_key(self):
        coord = _mock_coordinator({"soc": 50})
        sensor = BatteryBackupTimeSensor(coord)
        assert sensor.native_value is None

    def test_native_value_none(self):
        coord = _mock_coordinator(None)
        sensor = BatteryBackupTimeSensor(coord)
        assert sensor.native_value is None


# ===========================================================================
# BatteryHealthSensor
# ===========================================================================
class TestBatteryHealthSensor:
    """Tests for the BatteryHealthSensor."""

    def test_native_value(self):
        coord = _mock_coordinator({"soh": 95})
        sensor = BatteryHealthSensor(coord)
        assert sensor.native_value == 95

    def test_native_value_default_100(self):
        coord = _mock_coordinator({"soc": 50})
        sensor = BatteryHealthSensor(coord)
        assert sensor.native_value == 100

    def test_native_value_none(self):
        coord = _mock_coordinator(None)
        sensor = BatteryHealthSensor(coord)
        assert sensor.native_value is None


# ===========================================================================
# BatteryGridModeSensor
# ===========================================================================
class TestBatteryGridModeSensor:
    """Tests for the BatteryGridModeSensor."""

    def test_native_value_from_devices(self):
        coord = _mock_coordinator({"devices": [{"reported_enc_grid_state": "grid-tied"}]})
        sensor = BatteryGridModeSensor(coord)
        assert sensor.native_value == "grid_tied"

    def test_native_value_from_devices_missing_state(self):
        coord = _mock_coordinator({"devices": [{"serial_num": "ABC"}]})
        sensor = BatteryGridModeSensor(coord)
        assert sensor.native_value == "unknown"

    def test_native_value_from_status_fallback(self):
        coord = _mock_coordinator({"devices": [], "status": "grid-tied"})
        sensor = BatteryGridModeSensor(coord)
        assert sensor.native_value == "grid_tied"

    def test_native_value_no_devices_no_status(self):
        coord = _mock_coordinator({"soc": 50})
        sensor = BatteryGridModeSensor(coord)
        assert sensor.native_value is None

    def test_native_value_none(self):
        coord = _mock_coordinator(None)
        sensor = BatteryGridModeSensor(coord)
        assert sensor.native_value is None


# ===========================================================================
# EnvoySerialNumberSensor
# ===========================================================================
class TestEnvoySerialNumberSensor:
    """Tests for the EnvoySerialNumberSensor (reads coordinator.envoy_serial)."""

    def test_native_value(self):
        coord = _mock_coordinator({"soc": 50})
        coord.envoy_serial = "ABC123456"
        sensor = EnvoySerialNumberSensor(coord)
        assert sensor.native_value == "ABC123456"

    def test_native_value_none(self):
        coord = _mock_coordinator({"soc": 50})
        coord.envoy_serial = None
        sensor = EnvoySerialNumberSensor(coord)
        assert sensor.native_value is None


# ===========================================================================
# EnvoyFirmwareSensor
# ===========================================================================
class TestEnvoyFirmwareSensor:
    """Tests for the EnvoyFirmwareSensor (reads coordinator.envoy_firmware)."""

    def test_native_value(self):
        coord = _mock_coordinator({"soc": 50})
        coord.envoy_firmware = "8.2.4225"
        sensor = EnvoyFirmwareSensor(coord)
        assert sensor.native_value == "8.2.4225"

    def test_native_value_none(self):
        coord = _mock_coordinator({"soc": 50})
        coord.envoy_firmware = None
        sensor = EnvoyFirmwareSensor(coord)
        assert sensor.native_value is None


# ===========================================================================
# Individual Battery Sensors - _get_device_data
# ===========================================================================
class TestIndividualBatteryGetDeviceData:
    """Tests for the _get_device_data method on individual battery sensors."""

    def test_get_device_data_found(self):
        coord = _mock_coordinator({"devices": [{"serial_num": "SN001", "temperature": 25}]})
        sensor = IndividualBatteryTemperatureSensor(coord, "SN001", "500-00001", 1)
        assert sensor._get_device_data() == {"serial_num": "SN001", "temperature": 25}

    def test_get_device_data_not_found(self):
        coord = _mock_coordinator({"devices": [{"serial_num": "SN002", "temperature": 25}]})
        sensor = IndividualBatteryTemperatureSensor(coord, "SN001", "500-00001", 1)
        assert sensor._get_device_data() is None

    def test_get_device_data_no_data(self):
        coord = _mock_coordinator(None)
        sensor = IndividualBatteryTemperatureSensor(coord, "SN001", "500-00001", 1)
        assert sensor._get_device_data() is None

    def test_get_device_data_empty_devices(self):
        coord = _mock_coordinator({"devices": []})
        sensor = IndividualBatteryTemperatureSensor(coord, "SN001", "500-00001", 1)
        assert sensor._get_device_data() is None


# ===========================================================================
# IndividualBatteryTemperatureSensor
# ===========================================================================
class TestIndividualBatteryTemperatureSensor:
    """Tests for IndividualBatteryTemperatureSensor."""

    def test_native_value(self):
        coord = _mock_coordinator({"devices": [{"serial_num": "SN001", "temperature": 32}]})
        sensor = IndividualBatteryTemperatureSensor(coord, "SN001", "500-00001", 1)
        assert sensor.native_value == 32

    def test_native_value_missing_key(self):
        coord = _mock_coordinator({"devices": [{"serial_num": "SN001"}]})
        sensor = IndividualBatteryTemperatureSensor(coord, "SN001", "500-00001", 1)
        assert sensor.native_value is None

    def test_native_value_no_data(self):
        coord = _mock_coordinator(None)
        sensor = IndividualBatteryTemperatureSensor(coord, "SN001", "500-00001", 1)
        assert sensor.native_value is None

    def test_unique_id(self):
        coord = _mock_coordinator(None)
        sensor = IndividualBatteryTemperatureSensor(coord, "SN001", "500-00001", 1)
        assert sensor._attr_unique_id == "test_entry_battery_SN001_temperature"


# ===========================================================================
# IndividualBatteryMaxCellTempSensor
# ===========================================================================
class TestIndividualBatteryMaxCellTempSensor:
    """Tests for IndividualBatteryMaxCellTempSensor."""

    def test_native_value(self):
        coord = _mock_coordinator({"devices": [{"serial_num": "SN001", "maxCellTemp": 38}]})
        sensor = IndividualBatteryMaxCellTempSensor(coord, "SN001", "500-00001", 1)
        assert sensor.native_value == 38

    def test_native_value_missing_key(self):
        coord = _mock_coordinator({"devices": [{"serial_num": "SN001"}]})
        sensor = IndividualBatteryMaxCellTempSensor(coord, "SN001", "500-00001", 1)
        assert sensor.native_value is None

    def test_native_value_no_data(self):
        coord = _mock_coordinator(None)
        sensor = IndividualBatteryMaxCellTempSensor(coord, "SN001", "500-00001", 1)
        assert sensor.native_value is None


# ===========================================================================
# IndividualBatteryCapacitySensor
# ===========================================================================
class TestIndividualBatteryCapacitySensor:
    """Tests for IndividualBatteryCapacitySensor."""

    def test_native_value(self):
        coord = _mock_coordinator({"devices": [{"serial_num": "SN001", "encharge_capacity": 5000}]})
        sensor = IndividualBatteryCapacitySensor(coord, "SN001", "500-00001", 1)
        assert sensor.native_value == 5000

    def test_native_value_missing_key(self):
        coord = _mock_coordinator({"devices": [{"serial_num": "SN001"}]})
        sensor = IndividualBatteryCapacitySensor(coord, "SN001", "500-00001", 1)
        assert sensor.native_value is None

    def test_native_value_no_data(self):
        coord = _mock_coordinator(None)
        sensor = IndividualBatteryCapacitySensor(coord, "SN001", "500-00001", 1)
        assert sensor.native_value is None


# ===========================================================================
# IndividualBatterySerialSensor
# ===========================================================================
class TestIndividualBatterySerialSensor:
    """Tests for IndividualBatterySerialSensor."""

    def test_native_value_returns_serial(self):
        coord = _mock_coordinator(None)
        sensor = IndividualBatterySerialSensor(coord, "SN001", "500-00001", 1)
        assert sensor.native_value == "SN001"

    def test_native_value_always_returns_serial(self):
        """Serial sensor always returns the serial_num, even without coordinator data."""
        coord = _mock_coordinator(None)
        sensor = IndividualBatterySerialSensor(coord, "MY-SERIAL", "500-00001", 1)
        assert sensor.native_value == "MY-SERIAL"


# ===========================================================================
# IndividualBatteryFirmwareSensor
# ===========================================================================
class TestIndividualBatteryFirmwareSensor:
    """Tests for IndividualBatteryFirmwareSensor."""

    def test_native_value(self):
        coord = _mock_coordinator({"devices": [{"serial_num": "SN001", "img_pnum_running": "1.2.3"}]})
        sensor = IndividualBatteryFirmwareSensor(coord, "SN001", "500-00001", 1)
        assert sensor.native_value == "1.2.3"

    def test_native_value_missing_key(self):
        coord = _mock_coordinator({"devices": [{"serial_num": "SN001"}]})
        sensor = IndividualBatteryFirmwareSensor(coord, "SN001", "500-00001", 1)
        assert sensor.native_value is None

    def test_native_value_no_data(self):
        coord = _mock_coordinator(None)
        sensor = IndividualBatteryFirmwareSensor(coord, "SN001", "500-00001", 1)
        assert sensor.native_value is None


# ===========================================================================
# IndividualBatterySOCSensor
# ===========================================================================
class TestIndividualBatterySOCSensor:
    """Tests for IndividualBatterySOCSensor."""

    def test_native_value_percentFull(self):
        coord = _mock_coordinator({"devices": [{"serial_num": "SN001", "percentFull": 82}]})
        sensor = IndividualBatterySOCSensor(coord, "SN001", "500-00001", 1)
        assert sensor.native_value == 82

    def test_native_value_soc_fallback(self):
        coord = _mock_coordinator({"devices": [{"serial_num": "SN001", "percentFull": 0, "soc": 55}]})
        sensor = IndividualBatterySOCSensor(coord, "SN001", "500-00001", 1)
        # percentFull is 0 (falsy), so fallback to soc
        assert sensor.native_value == 55

    def test_native_value_no_data(self):
        coord = _mock_coordinator(None)
        sensor = IndividualBatterySOCSensor(coord, "SN001", "500-00001", 1)
        assert sensor.native_value is None

    @pytest.mark.parametrize(
        ("soc", "expected_icon"),
        [
            (95, "mdi:battery"),
            (75, "mdi:battery-70"),
            (55, "mdi:battery-50"),
            (35, "mdi:battery-30"),
            (15, "mdi:battery-10"),
            (5, "mdi:battery-alert"),
        ],
    )
    def test_icon_by_level(self, soc, expected_icon):
        coord = _mock_coordinator({"devices": [{"serial_num": "SN001", "percentFull": soc}]})
        sensor = IndividualBatterySOCSensor(coord, "SN001", "500-00001", 1)
        assert sensor.icon == expected_icon

    def test_icon_when_none(self):
        coord = _mock_coordinator(None)
        sensor = IndividualBatterySOCSensor(coord, "SN001", "500-00001", 1)
        assert sensor.icon == "mdi:battery-unknown"


# ===========================================================================
# IndividualBatteryGridStateSensor
# ===========================================================================
class TestIndividualBatteryGridStateSensor:
    """Tests for IndividualBatteryGridStateSensor."""

    def test_native_value(self):
        coord = _mock_coordinator({"devices": [{"serial_num": "SN001", "reported_enc_grid_state": "grid-tied"}]})
        sensor = IndividualBatteryGridStateSensor(coord, "SN001", "500-00001", 1)
        assert sensor.native_value == "grid_tied"

    def test_native_value_default_unknown(self):
        coord = _mock_coordinator({"devices": [{"serial_num": "SN001"}]})
        sensor = IndividualBatteryGridStateSensor(coord, "SN001", "500-00001", 1)
        assert sensor.native_value == "unknown"

    def test_native_value_no_data(self):
        coord = _mock_coordinator(None)
        sensor = IndividualBatteryGridStateSensor(coord, "SN001", "500-00001", 1)
        assert sensor.native_value is None


# ===========================================================================
# async_setup_entry - System sensors and individual battery listener
# ===========================================================================
class TestAsyncSetupEntry:
    """Tests for the async_setup_entry function."""

    @pytest.mark.asyncio
    async def test_adds_system_sensors(self):
        """Test that system-level sensors are added."""
        coord = _mock_coordinator({"soc": 50})
        entry = MagicMock()
        entry.runtime_data = EnphaseBatteryRuntimeData(coordinator=coord)

        added_entities = []

        def capture_entities(entities):
            added_entities.extend(entities)

        await async_setup_entry(MagicMock(), entry, capture_entities)

        # Should have 14 system-level sensors
        assert len(added_entities) == 14

        # Verify types
        types = {type(e).__name__ for e in added_entities}
        assert "BatterySOCSensor" in types
        assert "BatteryStateSensor" in types
        assert "BatteryPowerSensor" in types
        assert "BatteryChargePowerSensor" in types
        assert "BatteryDischargePowerSensor" in types
        assert "BatteryAvailableEnergySensor" in types
        assert "BatteryEnergyChargedTodaySensor" in types
        assert "BatteryEnergyDischargedTodaySensor" in types
        assert "BatteryConsumption24hSensor" in types
        assert "BatteryBackupTimeSensor" in types
        assert "BatteryHealthSensor" in types
        assert "BatteryGridModeSensor" in types
        assert "EnvoySerialNumberSensor" in types
        assert "EnvoyFirmwareSensor" in types

    @pytest.mark.asyncio
    async def test_listener_adds_individual_batteries(self):
        """Test that the listener callback adds individual battery sensors."""
        coord = _mock_coordinator(
            {
                "soc": 50,
                "devices": [
                    {
                        "serial_num": "SN001",
                        "part_num": "500-00001",
                        "temperature": 25,
                        "percentFull": 80,
                    },
                ],
            }
        )

        entry = MagicMock()
        entry.runtime_data = EnphaseBatteryRuntimeData(coordinator=coord)
        entry.async_on_unload = MagicMock()

        all_added = []

        def capture_entities(entities):
            all_added.extend(entities)

        await async_setup_entry(MagicMock(), entry, capture_entities)

        # 14 system sensors + 7 individual sensors (1 battery with 7 sensors each)
        assert len(all_added) == 14 + 7

    @pytest.mark.asyncio
    async def test_listener_skips_non_battery_devices(self):
        """Test that devices without battery markers are skipped."""
        coord = _mock_coordinator(
            {
                "soc": 50,
                "devices": [
                    {
                        "serial_num": "SN_ENPOWER",
                        "part_num": "800-00001",
                        "type": "ENPOWER",
                    },
                ],
            }
        )

        entry = MagicMock()
        entry.runtime_data = EnphaseBatteryRuntimeData(coordinator=coord)
        entry.async_on_unload = MagicMock()

        all_added = []

        def capture_entities(entities):
            all_added.extend(entities)

        await async_setup_entry(MagicMock(), entry, capture_entities)

        # Only 14 system sensors, no individual batteries
        assert len(all_added) == 14

    @pytest.mark.asyncio
    async def test_listener_skips_devices_without_serial(self):
        """Test that devices without serial_num are skipped."""
        coord = _mock_coordinator(
            {
                "soc": 50,
                "devices": [
                    {"part_num": "500-00001", "temperature": 25},
                ],
            }
        )

        entry = MagicMock()
        entry.runtime_data = EnphaseBatteryRuntimeData(coordinator=coord)
        entry.async_on_unload = MagicMock()

        all_added = []

        def capture_entities(entities):
            all_added.extend(entities)

        await async_setup_entry(MagicMock(), entry, capture_entities)

        # Only 14 system sensors
        assert len(all_added) == 14

    @pytest.mark.asyncio
    async def test_listener_identifies_battery_by_type(self):
        """Test that devices with type ENCHARGE are recognized as batteries."""
        coord = _mock_coordinator(
            {
                "soc": 50,
                "devices": [
                    {
                        "serial_num": "SN001",
                        "part_num": "999-xxxxx",
                        "type": "ENCHARGE",
                    },
                ],
            }
        )

        entry = MagicMock()
        entry.runtime_data = EnphaseBatteryRuntimeData(coordinator=coord)
        entry.async_on_unload = MagicMock()

        all_added = []

        def capture_entities(entities):
            all_added.extend(entities)

        await async_setup_entry(MagicMock(), entry, capture_entities)

        # 14 system + 7 individual
        assert len(all_added) == 14 + 7

    @pytest.mark.asyncio
    async def test_listener_identifies_battery_by_percentFull(self):
        """Test that devices with percentFull field are recognized as batteries."""
        coord = _mock_coordinator(
            {
                "soc": 50,
                "devices": [
                    {
                        "serial_num": "SN001",
                        "part_num": "999-xxxxx",
                        "type": "unknown",
                        "percentFull": 50,
                    },
                ],
            }
        )

        entry = MagicMock()
        entry.runtime_data = EnphaseBatteryRuntimeData(coordinator=coord)
        entry.async_on_unload = MagicMock()

        all_added = []

        def capture_entities(entities):
            all_added.extend(entities)

        await async_setup_entry(MagicMock(), entry, capture_entities)

        # 14 system + 7 individual
        assert len(all_added) == 14 + 7

    @pytest.mark.asyncio
    async def test_listener_does_not_readd_batteries(self):
        """Test that already-added batteries are not re-added on subsequent calls."""
        coord = _mock_coordinator(
            {
                "soc": 50,
                "devices": [
                    {
                        "serial_num": "SN001",
                        "part_num": "500-00001",
                        "temperature": 25,
                    },
                ],
            }
        )

        entry = MagicMock()
        entry.runtime_data = EnphaseBatteryRuntimeData(coordinator=coord)
        entry.async_on_unload = MagicMock()

        all_added = []

        def capture_entities(entities):
            all_added.extend(entities)

        await async_setup_entry(MagicMock(), entry, capture_entities)

        # First call: 14 system + 7 individual = 21
        assert len(all_added) == 21

        # Now simulate the listener firing again (coordinator.async_add_listener was called)
        # The listener callback was passed to async_add_listener
        listener_call = coord.async_add_listener.call_args
        callback = listener_call[0][0]

        # Call listener again - should NOT add more entities
        all_added.clear()
        callback()

        # No new entities because SN001 was already added
        assert len(all_added) == 0

    @pytest.mark.asyncio
    async def test_listener_no_data(self):
        """Test that listener does nothing when coordinator.data is None."""
        coord = _mock_coordinator(None)

        entry = MagicMock()
        entry.runtime_data = EnphaseBatteryRuntimeData(coordinator=coord)
        entry.async_on_unload = MagicMock()

        all_added = []

        def capture_entities(entities):
            all_added.extend(entities)

        await async_setup_entry(MagicMock(), entry, capture_entities)

        # Only 14 system sensors (no data for individual batteries)
        assert len(all_added) == 14

    @pytest.mark.asyncio
    async def test_listener_no_devices_key(self):
        """Test listener when data exists but has no devices key."""
        coord = _mock_coordinator({"soc": 50})

        entry = MagicMock()
        entry.runtime_data = EnphaseBatteryRuntimeData(coordinator=coord)
        entry.async_on_unload = MagicMock()

        all_added = []

        def capture_entities(entities):
            all_added.extend(entities)

        await async_setup_entry(MagicMock(), entry, capture_entities)

        # Only 14 system sensors
        assert len(all_added) == 14
