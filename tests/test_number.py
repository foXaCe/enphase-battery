"""Tests for the Enphase Battery number platform."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.exceptions import HomeAssistantError
import pytest

from custom_components.enphase_battery import EnphaseBatteryRuntimeData
from custom_components.enphase_battery.coordinator import (
    EnphaseBatteryDataUpdateCoordinator,
)
from custom_components.enphase_battery.number import (
    BatteryBackupReserveNumber,
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
    # For the available property to work with super().available
    coord.last_update_success = True
    return coord


# ===========================================================================
# async_setup_entry
# ===========================================================================
class TestAsyncSetupEntry:
    """Tests for the async_setup_entry function."""

    @pytest.mark.asyncio
    async def test_creates_number_entity(self):
        """Should create the BatteryBackupReserveNumber entity."""
        coord = _mock_coordinator({"soc": 50, "very_low_soc": 10})

        entry = MagicMock()
        entry.runtime_data = EnphaseBatteryRuntimeData(coordinator=coord)

        added = []
        await async_setup_entry(MagicMock(), entry, lambda e: added.extend(e))

        assert len(added) == 1
        assert isinstance(added[0], BatteryBackupReserveNumber)


# ===========================================================================
# BatteryBackupReserveNumber
# ===========================================================================
class TestBatteryBackupReserveNumber:
    """Tests for the BatteryBackupReserveNumber."""

    def test_native_value(self):
        coord = _mock_coordinator({"very_low_soc": 15})
        number = BatteryBackupReserveNumber(coord)
        assert number.native_value == 15

    def test_native_value_default(self):
        """When very_low_soc is not in data, default to 5."""
        coord = _mock_coordinator({"soc": 50})
        number = BatteryBackupReserveNumber(coord)
        assert number.native_value == 5

    def test_native_value_none_no_data(self):
        coord = _mock_coordinator(None)
        number = BatteryBackupReserveNumber(coord)
        assert number.native_value is None

    def test_available_with_api(self):
        """available should be True when parent is available AND api is not None."""
        coord = _mock_coordinator({"very_low_soc": 10})
        number = BatteryBackupReserveNumber(coord)
        # We need to mock super().available; CoordinatorEntity.available
        # checks coordinator.last_update_success. We mock it through the property.
        with patch(
            "custom_components.enphase_battery.number.CoordinatorEntity.available",
            new_callable=lambda: property(lambda self: True),
        ):
            assert number.available is True

    def test_available_without_api(self):
        """available should be False when api is None."""
        coord = _mock_coordinator({"very_low_soc": 10})
        coord.api = None
        number = BatteryBackupReserveNumber(coord)
        with patch(
            "custom_components.enphase_battery.number.CoordinatorEntity.available",
            new_callable=lambda: property(lambda self: True),
        ):
            assert number.available is False

    def test_available_coordinator_unavailable(self):
        """available should be False when coordinator is unavailable."""
        coord = _mock_coordinator({"very_low_soc": 10})
        number = BatteryBackupReserveNumber(coord)
        with patch(
            "custom_components.enphase_battery.number.CoordinatorEntity.available",
            new_callable=lambda: property(lambda self: False),
        ):
            assert number.available is False

    @pytest.mark.asyncio
    async def test_set_native_value(self):
        coord = _mock_coordinator({"very_low_soc": 10})
        number = BatteryBackupReserveNumber(coord)

        await number.async_set_native_value(15.0)

        coord.api.set_very_low_soc.assert_awaited_once_with(15)
        coord.async_request_refresh.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_set_native_value_converts_to_int(self):
        """Value should be converted to int before calling API."""
        coord = _mock_coordinator({"very_low_soc": 10})
        number = BatteryBackupReserveNumber(coord)

        await number.async_set_native_value(20.7)

        coord.api.set_very_low_soc.assert_awaited_once_with(20)

    @pytest.mark.asyncio
    async def test_set_native_value_no_api(self):
        """Should raise HomeAssistantError when API is not initialized."""
        coord = _mock_coordinator({"very_low_soc": 10})
        coord.api = None
        number = BatteryBackupReserveNumber(coord)

        with pytest.raises(HomeAssistantError):
            await number.async_set_native_value(15.0)

    @pytest.mark.asyncio
    async def test_set_native_value_api_error(self):
        """Should propagate API errors."""
        coord = _mock_coordinator({"very_low_soc": 10})
        coord.api.set_very_low_soc = AsyncMock(side_effect=Exception("API error"))
        number = BatteryBackupReserveNumber(coord)

        with pytest.raises(Exception, match="API error"):
            await number.async_set_native_value(15.0)

    def test_unique_id(self):
        coord = _mock_coordinator(None)
        number = BatteryBackupReserveNumber(coord)
        assert number._attr_unique_id == "test_entry_very_low_soc"

    def test_min_max_step(self):
        coord = _mock_coordinator(None)
        number = BatteryBackupReserveNumber(coord)
        assert number._attr_native_min_value == 5
        assert number._attr_native_max_value == 25
        assert number._attr_native_step == 1
