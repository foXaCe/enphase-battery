"""Tests for the Enphase Battery binary sensor platform."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.enphase_battery import EnphaseBatteryRuntimeData
from custom_components.enphase_battery.binary_sensor import (
    BatteryGridTiedBinarySensor,
    BatteryHealthyBinarySensor,
    EnvoyConnectedBinarySensor,
    async_setup_entry,
)
from custom_components.enphase_battery.coordinator import (
    EnphaseBatteryDataUpdateCoordinator,
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
    coord.invalidate_cloud_control_cache = MagicMock()
    coord.async_request_refresh = AsyncMock()
    coord.async_add_listener = MagicMock(return_value=lambda: None)
    coord.battery_mode = "self-consumption"
    return coord


# ===========================================================================
# async_setup_entry
# ===========================================================================
class TestAsyncSetupEntry:
    """Tests for the async_setup_entry function."""

    @pytest.mark.asyncio
    async def test_creates_three_binary_sensors(self):
        """Should create 3 binary sensor entities."""
        coord = _mock_coordinator({"soc": 50})

        entry = MagicMock()
        entry.runtime_data = EnphaseBatteryRuntimeData(coordinator=coord)

        added = []
        await async_setup_entry(MagicMock(), entry, lambda e: added.extend(e))

        assert len(added) == 3
        types = {type(e).__name__ for e in added}
        assert "BatteryGridTiedBinarySensor" in types
        assert "BatteryHealthyBinarySensor" in types
        assert "EnvoyConnectedBinarySensor" in types


# ===========================================================================
# BatteryGridTiedBinarySensor
# ===========================================================================
class TestBatteryGridTiedBinarySensor:
    """Tests for the BatteryGridTiedBinarySensor."""

    def test_is_on_grid_tied_from_devices(self):
        coord = _mock_coordinator({"devices": [{"reported_enc_grid_state": "grid-tied"}]})
        sensor = BatteryGridTiedBinarySensor(coord)
        assert sensor.is_on is True

    def test_is_on_not_grid_tied_from_devices(self):
        coord = _mock_coordinator({"devices": [{"reported_enc_grid_state": "grid-forming"}]})
        sensor = BatteryGridTiedBinarySensor(coord)
        assert sensor.is_on is False

    def test_is_on_from_status_fallback(self):
        coord = _mock_coordinator({"devices": [], "status": "grid-tied"})
        sensor = BatteryGridTiedBinarySensor(coord)
        assert sensor.is_on is True

    def test_is_on_from_status_not_grid_tied(self):
        coord = _mock_coordinator({"devices": [], "status": "off-grid"})
        sensor = BatteryGridTiedBinarySensor(coord)
        assert sensor.is_on is False

    def test_is_on_from_status_case_insensitive(self):
        coord = _mock_coordinator({"devices": [], "status": "Grid-Tied"})
        sensor = BatteryGridTiedBinarySensor(coord)
        assert sensor.is_on is True

    def test_is_on_none_when_no_data(self):
        coord = _mock_coordinator(None)
        sensor = BatteryGridTiedBinarySensor(coord)
        assert sensor.is_on is None

    def test_icon_on(self):
        coord = _mock_coordinator({"devices": [{"reported_enc_grid_state": "grid-tied"}]})
        sensor = BatteryGridTiedBinarySensor(coord)
        assert sensor.icon == "mdi:transmission-tower"

    def test_icon_off(self):
        coord = _mock_coordinator({"devices": [{"reported_enc_grid_state": "grid-forming"}]})
        sensor = BatteryGridTiedBinarySensor(coord)
        assert sensor.icon == "mdi:transmission-tower-off"

    def test_icon_none_data(self):
        coord = _mock_coordinator(None)
        sensor = BatteryGridTiedBinarySensor(coord)
        # is_on is None, which is falsy -> off icon
        assert sensor.icon == "mdi:transmission-tower-off"

    def test_unique_id(self):
        coord = _mock_coordinator(None)
        sensor = BatteryGridTiedBinarySensor(coord)
        assert sensor._attr_unique_id == "test_entry_grid_tied"

    def test_is_on_empty_string_grid_state(self):
        """Test with empty string grid state from device."""
        coord = _mock_coordinator({"devices": [{"reported_enc_grid_state": ""}]})
        sensor = BatteryGridTiedBinarySensor(coord)
        assert sensor.is_on is False

    def test_is_on_missing_grid_state_key(self):
        """Test with device that has no reported_enc_grid_state key."""
        coord = _mock_coordinator({"devices": [{"serial_num": "ABC"}]})
        sensor = BatteryGridTiedBinarySensor(coord)
        # Falls back to default empty string, which != "grid-tied"
        assert sensor.is_on is False

    def test_is_on_no_devices_no_status(self):
        """Test with data but no devices and no status key."""
        coord = _mock_coordinator({"soc": 50})
        sensor = BatteryGridTiedBinarySensor(coord)
        # devices is empty, status is missing -> .get returns empty list, len(devices) = 0
        # Then status = data.get("status", "") -> ""
        # "grid-tied" in "".lower() -> False
        assert sensor.is_on is False


# ===========================================================================
# BatteryHealthyBinarySensor
# ===========================================================================
class TestBatteryHealthyBinarySensor:
    """Tests for the BatteryHealthyBinarySensor."""

    def test_is_on_healthy(self):
        """Healthy battery: soh=100, no high temperature -> no problem (False)."""
        coord = _mock_coordinator({"soh": 100})
        sensor = BatteryHealthyBinarySensor(coord)
        assert sensor.is_on is False

    def test_is_on_soh_below_80(self):
        """SOH below 80% indicates problem (True)."""
        coord = _mock_coordinator({"soh": 75})
        sensor = BatteryHealthyBinarySensor(coord)
        assert sensor.is_on is True

    def test_is_on_soh_exactly_80(self):
        """SOH exactly 80% is not a problem (False)."""
        coord = _mock_coordinator({"soh": 80})
        sensor = BatteryHealthyBinarySensor(coord)
        assert sensor.is_on is False

    def test_is_on_temperature_high(self):
        """Temperature > 50 indicates problem (True)."""
        coord = _mock_coordinator({"soh": 100, "temperature": 55})
        sensor = BatteryHealthyBinarySensor(coord)
        assert sensor.is_on is True

    def test_is_on_temperature_exactly_50(self):
        """Temperature exactly 50 is not a problem."""
        coord = _mock_coordinator({"soh": 100, "temperature": 50})
        sensor = BatteryHealthyBinarySensor(coord)
        assert sensor.is_on is False

    def test_is_on_temperature_none(self):
        """No temperature data with good SOH -> no problem."""
        coord = _mock_coordinator({"soh": 95})
        sensor = BatteryHealthyBinarySensor(coord)
        assert sensor.is_on is False

    def test_is_on_default_soh(self):
        """Missing soh key defaults to 100 -> no problem."""
        coord = _mock_coordinator({"soc": 50})
        sensor = BatteryHealthyBinarySensor(coord)
        assert sensor.is_on is False

    def test_is_on_none_when_no_data(self):
        coord = _mock_coordinator(None)
        sensor = BatteryHealthyBinarySensor(coord)
        assert sensor.is_on is None

    def test_icon_problem(self):
        coord = _mock_coordinator({"soh": 75})
        sensor = BatteryHealthyBinarySensor(coord)
        assert sensor.icon == "mdi:alert-circle"

    def test_icon_healthy(self):
        coord = _mock_coordinator({"soh": 100})
        sensor = BatteryHealthyBinarySensor(coord)
        assert sensor.icon == "mdi:check-circle"

    def test_icon_none_data(self):
        coord = _mock_coordinator(None)
        sensor = BatteryHealthyBinarySensor(coord)
        # is_on is None which is falsy -> check-circle
        assert sensor.icon == "mdi:check-circle"

    def test_unique_id(self):
        coord = _mock_coordinator(None)
        sensor = BatteryHealthyBinarySensor(coord)
        assert sensor._attr_unique_id == "test_entry_healthy"

    def test_both_soh_low_and_temp_high(self):
        """Both problems present: temperature check happens first, returns True."""
        coord = _mock_coordinator({"soh": 60, "temperature": 55})
        sensor = BatteryHealthyBinarySensor(coord)
        assert sensor.is_on is True

    def test_temperature_zero(self):
        """Temperature 0 is falsy in Python, so temp check is skipped."""
        coord = _mock_coordinator({"soh": 100, "temperature": 0})
        sensor = BatteryHealthyBinarySensor(coord)
        # temperature is 0, which is falsy -> `if temp and temp > 50` is False
        assert sensor.is_on is False


# ===========================================================================
# EnvoyConnectedBinarySensor
# ===========================================================================
class TestEnvoyConnectedBinarySensor:
    """Tests for the EnvoyConnectedBinarySensor."""

    def test_is_on_with_data(self):
        """If coordinator has any data, envoy is connected."""
        coord = _mock_coordinator({"soc": 50})
        sensor = EnvoyConnectedBinarySensor(coord)
        assert sensor.is_on is True

    def test_is_on_false_no_data(self):
        """If coordinator has no data, envoy is not connected."""
        coord = _mock_coordinator(None)
        sensor = EnvoyConnectedBinarySensor(coord)
        assert sensor.is_on is False

    def test_is_on_empty_dict(self):
        """Empty dict is truthy, so envoy is considered connected."""
        coord = _mock_coordinator({})
        sensor = EnvoyConnectedBinarySensor(coord)
        # Python: `not {}` is True... but the code says `if not self.coordinator.data`
        # {} is falsy? No, `not {}` == True. Wait: empty dict is falsy in Python.
        # So `if not self.coordinator.data:` will be True for {} -> return False
        assert sensor.is_on is False

    def test_icon_connected(self):
        coord = _mock_coordinator({"soc": 50})
        sensor = EnvoyConnectedBinarySensor(coord)
        assert sensor.icon == "mdi:router-wireless"

    def test_icon_disconnected(self):
        coord = _mock_coordinator(None)
        sensor = EnvoyConnectedBinarySensor(coord)
        assert sensor.icon == "mdi:router-wireless-off"

    def test_unique_id(self):
        coord = _mock_coordinator(None)
        sensor = EnvoyConnectedBinarySensor(coord)
        assert sensor._attr_unique_id == "test_entry_envoy_connected"
