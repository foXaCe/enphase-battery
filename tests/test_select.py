"""Tests for the Enphase Battery select platform."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.enphase_battery import EnphaseBatteryRuntimeData
from custom_components.enphase_battery.const import (
    BATTERY_MODE_BACKUP_ONLY,
    BATTERY_MODE_COST_SAVINGS,
    BATTERY_MODE_EXPERT,
    BATTERY_MODE_SELF_CONSUMPTION,
    CONF_CONNECTION_MODE,
    CONNECTION_MODE_CLOUD,
    CONNECTION_MODE_LOCAL,
    DOMAIN,
)
from custom_components.enphase_battery.coordinator import (
    EnphaseBatteryDataUpdateCoordinator,
)
from custom_components.enphase_battery.select import (
    BatteryModeSelect,
    async_setup_entry,
)


# ---------------------------------------------------------------------------
# Helper: create a mock coordinator
# ---------------------------------------------------------------------------
def _mock_coordinator(data=None, battery_mode=None):
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
    coord.battery_mode = battery_mode
    return coord


def _mock_entry(is_local=False, enable_cloud_control=False):
    """Create a mock config entry."""
    entry = MagicMock()
    entry.data = {
        CONF_CONNECTION_MODE: CONNECTION_MODE_LOCAL if is_local else CONNECTION_MODE_CLOUD,
        "enable_cloud_control": enable_cloud_control,
    }
    return entry


# ===========================================================================
# async_setup_entry
# ===========================================================================
class TestAsyncSetupEntry:
    """Tests for the async_setup_entry function."""

    @pytest.mark.asyncio
    async def test_cloud_mode_creates_select(self):
        """Cloud mode should create BatteryModeSelect."""
        coord = _mock_coordinator({"soc": 50}, battery_mode="self-consumption")
        coord.is_local_mode = False

        entry = _mock_entry(is_local=False)
        entry.runtime_data = EnphaseBatteryRuntimeData(coordinator=coord)

        added = []
        await async_setup_entry(MagicMock(), entry, lambda e: added.extend(e))

        assert len(added) == 1
        assert isinstance(added[0], BatteryModeSelect)

    @pytest.mark.asyncio
    async def test_local_mode_without_cloud_control_no_select(self):
        """Local mode without cloud control should create no select and log warning."""
        coord = _mock_coordinator({"soc": 50})
        coord.is_local_mode = True

        entry = _mock_entry(is_local=True, enable_cloud_control=False)
        entry.runtime_data = EnphaseBatteryRuntimeData(coordinator=coord)

        added = []
        with patch("custom_components.enphase_battery.select._LOGGER") as mock_logger:
            await async_setup_entry(MagicMock(), entry, lambda e: added.extend(e))
            mock_logger.warning.assert_called_once()

        assert len(added) == 0

    @pytest.mark.asyncio
    async def test_local_mode_with_cloud_control_creates_select(self):
        """Local mode with cloud control should create BatteryModeSelect."""
        coord = _mock_coordinator({"soc": 50}, battery_mode="self-consumption")
        coord.is_local_mode = True

        entry = _mock_entry(is_local=True, enable_cloud_control=True)
        entry.runtime_data = EnphaseBatteryRuntimeData(coordinator=coord)

        added = []
        await async_setup_entry(MagicMock(), entry, lambda e: added.extend(e))

        assert len(added) == 1
        assert isinstance(added[0], BatteryModeSelect)


# ===========================================================================
# BatteryModeSelect
# ===========================================================================
class TestBatteryModeSelect:
    """Tests for the BatteryModeSelect."""

    def test_current_option_self_consumption(self):
        coord = _mock_coordinator(
            {"soc": 50, "mode": "self-consumption"},
            battery_mode=BATTERY_MODE_SELF_CONSUMPTION,
        )
        select = BatteryModeSelect(coord)
        assert select.current_option == "self_consumption"

    def test_current_option_cost_savings(self):
        coord = _mock_coordinator(
            {"soc": 50, "mode": "cost_savings"},
            battery_mode=BATTERY_MODE_COST_SAVINGS,
        )
        select = BatteryModeSelect(coord)
        assert select.current_option == "savings"

    def test_current_option_backup_only(self):
        coord = _mock_coordinator(
            {"soc": 50, "mode": "backup_only"},
            battery_mode=BATTERY_MODE_BACKUP_ONLY,
        )
        select = BatteryModeSelect(coord)
        assert select.current_option == "backup"

    def test_current_option_expert(self):
        coord = _mock_coordinator(
            {"soc": 50, "mode": "expert"},
            battery_mode=BATTERY_MODE_EXPERT,
        )
        select = BatteryModeSelect(coord)
        assert select.current_option == "expert"

    def test_current_option_none_no_data(self):
        coord = _mock_coordinator(None, battery_mode=None)
        select = BatteryModeSelect(coord)
        assert select.current_option is None

    def test_current_option_none_no_battery_mode(self):
        coord = _mock_coordinator({"soc": 50}, battery_mode=None)
        select = BatteryModeSelect(coord)
        assert select.current_option is None

    def test_current_option_unknown_mode(self):
        coord = _mock_coordinator({"soc": 50}, battery_mode="unknown_mode")
        select = BatteryModeSelect(coord)
        assert select.current_option is None

    @pytest.mark.asyncio
    async def test_select_option_self_consumption(self):
        coord = _mock_coordinator({"soc": 50}, battery_mode="self-consumption")
        select = BatteryModeSelect(coord)

        await select.async_select_option("self_consumption")

        coord.api.set_battery_mode.assert_awaited_once_with(BATTERY_MODE_SELF_CONSUMPTION)
        coord.invalidate_cloud_control_cache.assert_called_once()
        coord.async_request_refresh.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_select_option_cost_savings(self):
        coord = _mock_coordinator({"soc": 50}, battery_mode="self-consumption")
        select = BatteryModeSelect(coord)

        await select.async_select_option("savings")

        coord.api.set_battery_mode.assert_awaited_once_with(BATTERY_MODE_COST_SAVINGS)

    @pytest.mark.asyncio
    async def test_select_option_backup_only(self):
        coord = _mock_coordinator({"soc": 50}, battery_mode="self-consumption")
        select = BatteryModeSelect(coord)

        await select.async_select_option("backup")

        coord.api.set_battery_mode.assert_awaited_once_with(BATTERY_MODE_BACKUP_ONLY)

    @pytest.mark.asyncio
    async def test_select_option_expert(self):
        coord = _mock_coordinator({"soc": 50}, battery_mode="self-consumption")
        select = BatteryModeSelect(coord)

        await select.async_select_option("expert")

        coord.api.set_battery_mode.assert_awaited_once_with(BATTERY_MODE_EXPERT)

    @pytest.mark.asyncio
    async def test_select_option_invalid(self):
        """Invalid option should log error and not call API."""
        coord = _mock_coordinator({"soc": 50}, battery_mode="self-consumption")
        select = BatteryModeSelect(coord)

        with patch("custom_components.enphase_battery.select._LOGGER") as mock_logger:
            await select.async_select_option("Invalid Mode")
            mock_logger.error.assert_called_once()

        coord.api.set_battery_mode.assert_not_called()

    @pytest.mark.asyncio
    async def test_select_option_error(self):
        coord = _mock_coordinator({"soc": 50}, battery_mode="self-consumption")
        coord.api.set_battery_mode = AsyncMock(side_effect=Exception("API error"))
        select = BatteryModeSelect(coord)

        with pytest.raises(Exception, match="API error"):
            await select.async_select_option("self_consumption")

    @pytest.mark.asyncio
    async def test_select_option_no_api(self):
        coord = _mock_coordinator({"soc": 50}, battery_mode="self-consumption")
        coord.api = None
        select = BatteryModeSelect(coord)

        with pytest.raises(HomeAssistantError):
            await select.async_select_option("self_consumption")

    def test_unique_id(self):
        coord = _mock_coordinator(None)
        select = BatteryModeSelect(coord)
        assert select._attr_unique_id == "test_entry_battery_mode"

    def test_options_list(self):
        coord = _mock_coordinator(None)
        select = BatteryModeSelect(coord)
        assert "self_consumption" in select._attr_options
        assert "savings" in select._attr_options

    def test_mode_mapping_roundtrip(self):
        """Verify all API modes can be mapped to keys and back."""
        coord = _mock_coordinator(None)
        select = BatteryModeSelect(coord)

        api_modes = [
            BATTERY_MODE_SELF_CONSUMPTION,
            BATTERY_MODE_COST_SAVINGS,
            BATTERY_MODE_BACKUP_ONLY,
            BATTERY_MODE_EXPERT,
        ]

        for api_mode in api_modes:
            key = select._mode_api_to_key.get(api_mode)
            assert key is not None, f"No translation key for {api_mode}"
            back_to_api = select._mode_key_to_api.get(key)
            assert back_to_api == api_mode, f"Roundtrip failed for {api_mode}"
