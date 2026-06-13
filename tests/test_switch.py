"""Tests for the Enphase Battery switch platform."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.enphase_battery import EnphaseBatteryRuntimeData
from custom_components.enphase_battery.const import (
    CONF_CONNECTION_MODE,
    CONNECTION_MODE_CLOUD,
    CONNECTION_MODE_LOCAL,
    DOMAIN,
)
from custom_components.enphase_battery.coordinator import (
    EnphaseBatteryDataUpdateCoordinator,
)
from custom_components.enphase_battery.switch import (
    SWITCHES,
    EnphaseBatterySwitch,
    async_setup_entry,
)


def _make_switch(coord, key: str) -> EnphaseBatterySwitch:
    """Build an EnphaseBatterySwitch for the description with the given key."""
    description = next(d for d in SWITCHES if d.key == key)
    return EnphaseBatterySwitch(coord, description)


# ---------------------------------------------------------------------------
# Helper: create a mock coordinator
# ---------------------------------------------------------------------------
def _mock_coordinator(data=None):
    """Create a mock coordinator with data."""
    coord = MagicMock(spec=EnphaseBatteryDataUpdateCoordinator)
    coord.data = data
    coord.unique_id_prefix = "test_entry"
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
    async def test_cloud_mode_creates_all_switches(self):
        """Cloud mode should create all 4 switches."""
        coord = _mock_coordinator({"soc": 50})
        coord.is_local_mode = False

        entry = _mock_entry(is_local=False)
        entry.runtime_data = EnphaseBatteryRuntimeData(coordinator=coord)

        added = []
        await async_setup_entry(MagicMock(), entry, lambda e: added.extend(e))

        assert len(added) == 4
        keys = {e.entity_description.key for e in added}
        assert keys == {
            "charge_from_grid",
            "discharge_to_grid",
            "reserve_battery_discharge",
            "power_match",
        }

    @pytest.mark.asyncio
    async def test_local_mode_without_cloud_control_no_switches(self):
        """Local mode without cloud control should create no switches and log warning."""
        coord = _mock_coordinator({"soc": 50})
        coord.is_local_mode = True

        entry = _mock_entry(is_local=True, enable_cloud_control=False)
        entry.runtime_data = EnphaseBatteryRuntimeData(coordinator=coord)

        added = []
        with patch("custom_components.enphase_battery.switch._LOGGER") as mock_logger:
            await async_setup_entry(MagicMock(), entry, lambda e: added.extend(e))
            mock_logger.warning.assert_called_once()

        assert len(added) == 0

    @pytest.mark.asyncio
    async def test_local_mode_with_cloud_control_creates_switches(self):
        """Local mode with cloud control enabled should create all 4 switches."""
        coord = _mock_coordinator({"soc": 50})
        coord.is_local_mode = True

        entry = _mock_entry(is_local=True, enable_cloud_control=True)
        entry.runtime_data = EnphaseBatteryRuntimeData(coordinator=coord)

        added = []
        await async_setup_entry(MagicMock(), entry, lambda e: added.extend(e))

        assert len(added) == 4


# ===========================================================================
# ChargeFromGridSwitch
# ===========================================================================
class TestChargeFromGridSwitch:
    """Tests for the ChargeFromGridSwitch."""

    def test_is_on_from_data(self):
        coord = _mock_coordinator({"charge_from_grid": True})
        switch = _make_switch(coord, "charge_from_grid")
        assert switch.is_on is True

    def test_is_on_false_from_data(self):
        coord = _mock_coordinator({"charge_from_grid": False})
        switch = _make_switch(coord, "charge_from_grid")
        assert switch.is_on is False

    def test_is_on_default_false(self):
        coord = _mock_coordinator({"soc": 50})
        switch = _make_switch(coord, "charge_from_grid")
        assert switch.is_on is False

    def test_is_on_none_when_no_data(self):
        coord = _mock_coordinator(None)
        switch = _make_switch(coord, "charge_from_grid")
        assert switch.is_on is None

    def test_is_on_optimistic_state(self):
        coord = _mock_coordinator({"charge_from_grid": False})
        switch = _make_switch(coord, "charge_from_grid")
        switch._optimistic_state = True
        assert switch.is_on is True

    @pytest.mark.asyncio
    async def test_turn_on(self):
        coord = _mock_coordinator({"charge_from_grid": False})
        switch = _make_switch(coord, "charge_from_grid")
        switch.async_write_ha_state = MagicMock()

        await switch.async_turn_on()

        coord.api.set_charge_from_grid.assert_awaited_once_with(True)
        coord.invalidate_cloud_control_cache.assert_called_once()
        coord.async_request_refresh.assert_awaited_once()
        assert switch._optimistic_state is None

    @pytest.mark.asyncio
    async def test_turn_off(self):
        coord = _mock_coordinator({"charge_from_grid": True})
        switch = _make_switch(coord, "charge_from_grid")
        switch.async_write_ha_state = MagicMock()

        await switch.async_turn_off()

        coord.api.set_charge_from_grid.assert_awaited_once_with(False)
        coord.invalidate_cloud_control_cache.assert_called_once()
        coord.async_request_refresh.assert_awaited_once()
        assert switch._optimistic_state is None

    @pytest.mark.asyncio
    async def test_turn_on_error(self):
        coord = _mock_coordinator({"charge_from_grid": False})
        coord.api.set_charge_from_grid = AsyncMock(side_effect=Exception("API error"))
        switch = _make_switch(coord, "charge_from_grid")
        switch.async_write_ha_state = MagicMock()

        with pytest.raises(Exception, match="API error"):
            await switch.async_turn_on()

        assert switch._optimistic_state is None

    @pytest.mark.asyncio
    async def test_turn_off_error(self):
        coord = _mock_coordinator({"charge_from_grid": True})
        coord.api.set_charge_from_grid = AsyncMock(side_effect=Exception("API error"))
        switch = _make_switch(coord, "charge_from_grid")
        switch.async_write_ha_state = MagicMock()

        with pytest.raises(Exception, match="API error"):
            await switch.async_turn_off()

        assert switch._optimistic_state is None

    @pytest.mark.asyncio
    async def test_turn_on_no_api(self):
        coord = _mock_coordinator({"charge_from_grid": False})
        coord.api = None
        switch = _make_switch(coord, "charge_from_grid")
        switch.async_write_ha_state = MagicMock()

        with pytest.raises(HomeAssistantError):
            await switch.async_turn_on()

        assert switch._optimistic_state is None

    @pytest.mark.asyncio
    async def test_turn_off_no_api(self):
        coord = _mock_coordinator({"charge_from_grid": True})
        coord.api = None
        switch = _make_switch(coord, "charge_from_grid")
        switch.async_write_ha_state = MagicMock()

        with pytest.raises(HomeAssistantError):
            await switch.async_turn_off()

        assert switch._optimistic_state is None

    def test_unique_id(self):
        coord = _mock_coordinator(None)
        switch = _make_switch(coord, "charge_from_grid")
        assert switch._attr_unique_id == f"{coord.unique_id_prefix}_charge_from_grid"


# ===========================================================================
# LimitDischargeSwitch
# ===========================================================================
class TestLimitDischargeSwitch:
    """Tests for the LimitDischargeSwitch."""

    def test_is_on_from_data(self):
        coord = _mock_coordinator({"discharge_to_grid": True})
        switch = _make_switch(coord, "discharge_to_grid")
        assert switch.is_on is True

    def test_is_on_false_from_data(self):
        coord = _mock_coordinator({"discharge_to_grid": False})
        switch = _make_switch(coord, "discharge_to_grid")
        assert switch.is_on is False

    def test_is_on_default_false(self):
        coord = _mock_coordinator({"soc": 50})
        switch = _make_switch(coord, "discharge_to_grid")
        assert switch.is_on is False

    def test_is_on_none_when_no_data(self):
        coord = _mock_coordinator(None)
        switch = _make_switch(coord, "discharge_to_grid")
        assert switch.is_on is None

    def test_is_on_optimistic_state(self):
        coord = _mock_coordinator({"discharge_to_grid": False})
        switch = _make_switch(coord, "discharge_to_grid")
        switch._optimistic_state = True
        assert switch.is_on is True

    @pytest.mark.asyncio
    async def test_turn_on(self):
        coord = _mock_coordinator({"discharge_to_grid": False})
        switch = _make_switch(coord, "discharge_to_grid")
        switch.async_write_ha_state = MagicMock()

        await switch.async_turn_on()

        coord.api.set_limit_discharge.assert_awaited_once_with(True)
        coord.invalidate_cloud_control_cache.assert_called_once()
        coord.async_request_refresh.assert_awaited_once()
        assert switch._optimistic_state is None

    @pytest.mark.asyncio
    async def test_turn_off(self):
        coord = _mock_coordinator({"discharge_to_grid": True})
        switch = _make_switch(coord, "discharge_to_grid")
        switch.async_write_ha_state = MagicMock()

        await switch.async_turn_off()

        coord.api.set_limit_discharge.assert_awaited_once_with(False)
        coord.invalidate_cloud_control_cache.assert_called_once()
        coord.async_request_refresh.assert_awaited_once()
        assert switch._optimistic_state is None

    @pytest.mark.asyncio
    async def test_turn_on_error(self):
        coord = _mock_coordinator({"discharge_to_grid": False})
        coord.api.set_limit_discharge = AsyncMock(side_effect=Exception("API error"))
        switch = _make_switch(coord, "discharge_to_grid")
        switch.async_write_ha_state = MagicMock()

        with pytest.raises(Exception, match="API error"):
            await switch.async_turn_on()

        assert switch._optimistic_state is None

    @pytest.mark.asyncio
    async def test_turn_off_error(self):
        coord = _mock_coordinator({"discharge_to_grid": True})
        coord.api.set_limit_discharge = AsyncMock(side_effect=Exception("API error"))
        switch = _make_switch(coord, "discharge_to_grid")
        switch.async_write_ha_state = MagicMock()

        with pytest.raises(Exception, match="API error"):
            await switch.async_turn_off()

        assert switch._optimistic_state is None

    @pytest.mark.asyncio
    async def test_turn_on_no_api(self):
        coord = _mock_coordinator({"discharge_to_grid": False})
        coord.api = None
        switch = _make_switch(coord, "discharge_to_grid")
        switch.async_write_ha_state = MagicMock()

        with pytest.raises(HomeAssistantError):
            await switch.async_turn_on()

    @pytest.mark.asyncio
    async def test_turn_off_no_api(self):
        coord = _mock_coordinator({"discharge_to_grid": True})
        coord.api = None
        switch = _make_switch(coord, "discharge_to_grid")
        switch.async_write_ha_state = MagicMock()

        with pytest.raises(HomeAssistantError):
            await switch.async_turn_off()

    def test_unique_id(self):
        coord = _mock_coordinator(None)
        switch = _make_switch(coord, "discharge_to_grid")
        assert switch._attr_unique_id == f"{coord.unique_id_prefix}_discharge_to_grid"


# ===========================================================================
# ReserveBatteryDischargeSwitch
# ===========================================================================
class TestReserveBatteryDischargeSwitch:
    """Tests for the ReserveBatteryDischargeSwitch."""

    def test_is_on_from_data(self):
        coord = _mock_coordinator({"reserve_battery_discharge": True})
        switch = _make_switch(coord, "reserve_battery_discharge")
        assert switch.is_on is True

    def test_is_on_false_from_data(self):
        coord = _mock_coordinator({"reserve_battery_discharge": False})
        switch = _make_switch(coord, "reserve_battery_discharge")
        assert switch.is_on is False

    def test_is_on_default_false(self):
        coord = _mock_coordinator({"soc": 50})
        switch = _make_switch(coord, "reserve_battery_discharge")
        assert switch.is_on is False

    def test_is_on_none_when_no_data(self):
        coord = _mock_coordinator(None)
        switch = _make_switch(coord, "reserve_battery_discharge")
        assert switch.is_on is None

    def test_is_on_optimistic_state(self):
        coord = _mock_coordinator({"reserve_battery_discharge": False})
        switch = _make_switch(coord, "reserve_battery_discharge")
        switch._optimistic_state = True
        assert switch.is_on is True

    @pytest.mark.asyncio
    async def test_turn_on(self):
        coord = _mock_coordinator({"reserve_battery_discharge": False})
        switch = _make_switch(coord, "reserve_battery_discharge")
        switch.async_write_ha_state = MagicMock()

        await switch.async_turn_on()

        coord.api.set_reserve_battery_discharge.assert_awaited_once_with(True)
        coord.invalidate_cloud_control_cache.assert_called_once()
        coord.async_request_refresh.assert_awaited_once()
        assert switch._optimistic_state is None

    @pytest.mark.asyncio
    async def test_turn_off(self):
        coord = _mock_coordinator({"reserve_battery_discharge": True})
        switch = _make_switch(coord, "reserve_battery_discharge")
        switch.async_write_ha_state = MagicMock()

        await switch.async_turn_off()

        coord.api.set_reserve_battery_discharge.assert_awaited_once_with(False)
        coord.invalidate_cloud_control_cache.assert_called_once()
        coord.async_request_refresh.assert_awaited_once()
        assert switch._optimistic_state is None

    @pytest.mark.asyncio
    async def test_turn_on_error(self):
        coord = _mock_coordinator({"reserve_battery_discharge": False})
        coord.api.set_reserve_battery_discharge = AsyncMock(side_effect=Exception("API error"))
        switch = _make_switch(coord, "reserve_battery_discharge")
        switch.async_write_ha_state = MagicMock()

        with pytest.raises(Exception, match="API error"):
            await switch.async_turn_on()

        assert switch._optimistic_state is None

    @pytest.mark.asyncio
    async def test_turn_off_error(self):
        coord = _mock_coordinator({"reserve_battery_discharge": True})
        coord.api.set_reserve_battery_discharge = AsyncMock(side_effect=Exception("API error"))
        switch = _make_switch(coord, "reserve_battery_discharge")
        switch.async_write_ha_state = MagicMock()

        with pytest.raises(Exception, match="API error"):
            await switch.async_turn_off()

        assert switch._optimistic_state is None

    @pytest.mark.asyncio
    async def test_turn_on_no_api(self):
        coord = _mock_coordinator({"reserve_battery_discharge": False})
        coord.api = None
        switch = _make_switch(coord, "reserve_battery_discharge")
        switch.async_write_ha_state = MagicMock()

        with pytest.raises(HomeAssistantError):
            await switch.async_turn_on()

    @pytest.mark.asyncio
    async def test_turn_off_no_api(self):
        coord = _mock_coordinator({"reserve_battery_discharge": True})
        coord.api = None
        switch = _make_switch(coord, "reserve_battery_discharge")
        switch.async_write_ha_state = MagicMock()

        with pytest.raises(HomeAssistantError):
            await switch.async_turn_off()

    def test_unique_id(self):
        coord = _mock_coordinator(None)
        switch = _make_switch(coord, "reserve_battery_discharge")
        assert switch._attr_unique_id == f"{coord.unique_id_prefix}_reserve_battery_discharge"


# ===========================================================================
# PowerMatchSwitch
# ===========================================================================
class TestPowerMatchSwitch:
    """Tests for the PowerMatchSwitch."""

    def test_is_on_from_data(self):
        coord = _mock_coordinator({"power_match": True})
        switch = _make_switch(coord, "power_match")
        assert switch.is_on is True

    def test_is_on_false_from_data(self):
        coord = _mock_coordinator({"power_match": False})
        switch = _make_switch(coord, "power_match")
        assert switch.is_on is False

    def test_is_on_default_false(self):
        coord = _mock_coordinator({"soc": 50})
        switch = _make_switch(coord, "power_match")
        assert switch.is_on is False

    def test_is_on_none_when_no_data(self):
        coord = _mock_coordinator(None)
        switch = _make_switch(coord, "power_match")
        assert switch.is_on is None

    def test_is_on_optimistic_state(self):
        coord = _mock_coordinator({"power_match": False})
        switch = _make_switch(coord, "power_match")
        switch._optimistic_state = True
        assert switch.is_on is True

    @pytest.mark.asyncio
    async def test_turn_on(self):
        coord = _mock_coordinator({"power_match": False})
        switch = _make_switch(coord, "power_match")
        switch.async_write_ha_state = MagicMock()

        await switch.async_turn_on()

        coord.api.set_power_match.assert_awaited_once_with(True)
        coord.invalidate_cloud_control_cache.assert_called_once()
        coord.async_request_refresh.assert_awaited_once()
        assert switch._optimistic_state is None

    @pytest.mark.asyncio
    async def test_turn_off(self):
        coord = _mock_coordinator({"power_match": True})
        switch = _make_switch(coord, "power_match")
        switch.async_write_ha_state = MagicMock()

        await switch.async_turn_off()

        coord.api.set_power_match.assert_awaited_once_with(False)
        coord.invalidate_cloud_control_cache.assert_called_once()
        coord.async_request_refresh.assert_awaited_once()
        assert switch._optimistic_state is None

    @pytest.mark.asyncio
    async def test_turn_on_error(self):
        coord = _mock_coordinator({"power_match": False})
        coord.api.set_power_match = AsyncMock(side_effect=Exception("API error"))
        switch = _make_switch(coord, "power_match")
        switch.async_write_ha_state = MagicMock()

        with pytest.raises(Exception, match="API error"):
            await switch.async_turn_on()

        assert switch._optimistic_state is None

    @pytest.mark.asyncio
    async def test_turn_off_error(self):
        coord = _mock_coordinator({"power_match": True})
        coord.api.set_power_match = AsyncMock(side_effect=Exception("API error"))
        switch = _make_switch(coord, "power_match")
        switch.async_write_ha_state = MagicMock()

        with pytest.raises(Exception, match="API error"):
            await switch.async_turn_off()

        assert switch._optimistic_state is None

    @pytest.mark.asyncio
    async def test_turn_on_no_api(self):
        coord = _mock_coordinator({"power_match": False})
        coord.api = None
        switch = _make_switch(coord, "power_match")
        switch.async_write_ha_state = MagicMock()

        with pytest.raises(HomeAssistantError):
            await switch.async_turn_on()

    @pytest.mark.asyncio
    async def test_turn_off_no_api(self):
        coord = _mock_coordinator({"power_match": True})
        coord.api = None
        switch = _make_switch(coord, "power_match")
        switch.async_write_ha_state = MagicMock()

        with pytest.raises(HomeAssistantError):
            await switch.async_turn_off()

    def test_unique_id(self):
        coord = _mock_coordinator(None)
        switch = _make_switch(coord, "power_match")
        assert switch._attr_unique_id == f"{coord.unique_id_prefix}_power_match"
