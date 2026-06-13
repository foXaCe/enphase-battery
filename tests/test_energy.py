"""Unit tests for the EnergyTracker (no Home Assistant required)."""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.enphase_battery.energy import EnergyTracker


@pytest.fixture
def mock_store() -> MagicMock:
    """Return a mock persistent store."""
    store = MagicMock()
    store.async_load = AsyncMock(return_value=None)
    store.async_save = AsyncMock()
    return store


@pytest.fixture
def tracker(mock_store: MagicMock) -> EnergyTracker:
    """Return an EnergyTracker backed by the mock store."""
    return EnergyTracker(mock_store)


# ---------------------------------------------------------------------------
# Initialization
# ---------------------------------------------------------------------------


class TestInit:
    """Initial state."""

    def test_defaults(self, tracker: EnergyTracker) -> None:
        assert tracker._daily_reset_date is None
        assert tracker._daily_charged_start == 0
        assert tracker._daily_discharged_start == 0
        assert tracker._consumption_24h_history == []
        assert tracker._last_soc is None
        assert tracker._last_power is None
        assert tracker._last_update_time is None
        assert tracker._last_storage_save is None


# ---------------------------------------------------------------------------
# async_load
# ---------------------------------------------------------------------------


class TestAsyncLoad:
    """Loading persisted state."""

    async def test_success_with_data(self, tracker: EnergyTracker, mock_store: MagicMock) -> None:
        mock_store.async_load.return_value = {
            "reset_date": "2024-01-15",
            "charged_start": 50.0,
            "discharged_start": 30.0,
            "consumption_history": [("2024-01-15T10:00:00", 100.0)],
            "last_soc": 65,
            "soc_charged": 1.5,
            "soc_discharged": 0.8,
            "last_power": -200,
            "last_update_time": "2024-01-15T10:00:00",
            "power_charged": 2.0,
            "power_discharged": 1.0,
        }

        await tracker.async_load()

        assert tracker._daily_reset_date == "2024-01-15"
        assert tracker._daily_charged_start == 50.0
        assert tracker._daily_discharged_start == 30.0
        assert len(tracker._consumption_24h_history) == 1
        assert tracker._last_soc == 65
        assert tracker._daily_soc_charged == 1.5
        assert tracker._daily_soc_discharged == 0.8
        assert tracker._last_power == -200
        assert tracker._last_update_time == "2024-01-15T10:00:00"
        assert tracker._daily_power_charged == 2.0
        assert tracker._daily_power_discharged == 1.0

    async def test_empty_store(self, tracker: EnergyTracker, mock_store: MagicMock) -> None:
        mock_store.async_load.return_value = None

        await tracker.async_load()

        assert tracker._daily_reset_date is None
        assert tracker._daily_charged_start == 0
        assert tracker._daily_discharged_start == 0
        assert tracker._consumption_24h_history == []
        assert tracker._last_soc is None

    async def test_store_error(self, tracker: EnergyTracker, mock_store: MagicMock) -> None:
        mock_store.async_load = AsyncMock(side_effect=Exception("Storage error"))

        # Should not raise
        await tracker.async_load()


# ---------------------------------------------------------------------------
# async_save / async_save_safe
# ---------------------------------------------------------------------------


class TestAsyncSave:
    """Saving persisted state."""

    async def test_success(self, tracker: EnergyTracker, mock_store: MagicMock) -> None:
        tracker._daily_reset_date = "2024-01-15"
        tracker._daily_charged_start = 50.0
        tracker._daily_discharged_start = 30.0
        tracker._consumption_24h_history = [("2024-01-15T10:00:00", 100.0)]
        tracker._last_soc = 65
        tracker._daily_soc_charged = 1.5
        tracker._daily_soc_discharged = 0.8
        tracker._last_power = -200
        tracker._last_update_time = "2024-01-15T10:00:00"
        tracker._daily_power_charged = 2.0
        tracker._daily_power_discharged = 1.0

        await tracker.async_save()

        mock_store.async_save.assert_awaited_once()
        saved = mock_store.async_save.call_args[0][0]
        assert saved["reset_date"] == "2024-01-15"
        assert saved["charged_start"] == 50.0
        assert saved["discharged_start"] == 30.0
        assert saved["last_soc"] == 65
        assert saved["soc_charged"] == 1.5
        assert saved["soc_discharged"] == 0.8
        assert saved["last_power"] == -200
        assert saved["last_update_time"] == "2024-01-15T10:00:00"
        assert saved["power_charged"] == 2.0
        assert saved["power_discharged"] == 1.0

    async def test_truncates_consumption_history(self, tracker: EnergyTracker, mock_store: MagicMock) -> None:
        tracker._consumption_24h_history = [(f"2024-01-15T{i:02d}:00:00", float(i)) for i in range(150)]

        await tracker.async_save()

        saved = mock_store.async_save.call_args[0][0]
        assert len(saved["consumption_history"]) == 100

    async def test_error(self, tracker: EnergyTracker, mock_store: MagicMock) -> None:
        mock_store.async_save = AsyncMock(side_effect=Exception("Write error"))

        # Should not raise (errors are logged and swallowed)
        await tracker.async_save()


# ---------------------------------------------------------------------------
# update
# ---------------------------------------------------------------------------


class TestUpdate:
    """Derived value computation."""

    def test_midnight_reset(self, tracker: EnergyTracker) -> None:
        tracker._daily_reset_date = "2020-01-01"  # Old date
        tracker._daily_charged_start = 999
        tracker._daily_discharged_start = 888
        tracker._daily_soc_charged = 10
        tracker._daily_soc_discharged = 5
        tracker._daily_power_charged = 3.0
        tracker._daily_power_discharged = 2.0

        data = {
            "total_energy_charged": 200.0,
            "total_energy_discharged": 150.0,
            "total_consumption": 400.0,
            "available_energy": 5000,
            "power": 1000,
        }

        tracker.update(data)

        today_str = datetime.now().strftime("%Y-%m-%d")
        assert tracker._daily_reset_date == today_str
        assert tracker._daily_charged_start == 200.0
        assert tracker._daily_discharged_start == 150.0
        assert tracker._daily_soc_charged == 0
        assert tracker._daily_soc_discharged == 0
        assert tracker._daily_power_charged == 0
        assert tracker._daily_power_discharged == 0
        assert data["energy_charged_today"] == 0
        assert data["energy_discharged_today"] == 0

    def test_meter_based_energy(self, tracker: EnergyTracker) -> None:
        today_str = datetime.now().strftime("%Y-%m-%d")
        tracker._daily_reset_date = today_str
        tracker._daily_charged_start = 100.0
        tracker._daily_discharged_start = 80.0

        data = {
            "total_energy_charged": 105.5,
            "total_energy_discharged": 83.2,
            "total_consumption": 250.0,
            "available_energy": 5000,
            "power": 500,
        }

        tracker.update(data)

        assert data["energy_charged_today"] == 5.5
        assert data["energy_discharged_today"] == 3.2

    def test_power_integration_fallback_charging(self, tracker: EnergyTracker) -> None:
        today_str = datetime.now().strftime("%Y-%m-%d")
        tracker._daily_reset_date = today_str
        past_time = datetime.now() - timedelta(seconds=30)
        tracker._last_power = -1000.0
        tracker._last_update_time = past_time.isoformat()

        data = {
            "total_energy_charged": 0,
            "total_energy_discharged": 0,
            "total_consumption": 100.0,
            "available_energy": 5000,
            "power": -1000,
            "soc": 50,
        }

        tracker.update(data)

        assert data["energy_charged_today"] > 0
        assert data["energy_discharged_today"] == 0
        assert tracker._last_power == -1000
        assert tracker._last_update_time is not None
        assert tracker._last_soc == 50

    def test_power_integration_fallback_discharging(self, tracker: EnergyTracker) -> None:
        today_str = datetime.now().strftime("%Y-%m-%d")
        tracker._daily_reset_date = today_str
        past_time = datetime.now() - timedelta(seconds=60)
        tracker._last_power = 2000.0
        tracker._last_update_time = past_time.isoformat()

        data = {
            "total_energy_charged": 0,
            "total_energy_discharged": 0,
            "total_consumption": 100.0,
            "available_energy": 5000,
            "power": 2000,
            "soc": 40,
        }

        tracker.update(data)

        assert data["energy_charged_today"] == 0
        assert data["energy_discharged_today"] > 0

    def test_power_integration_zero_avg_power(self, tracker: EnergyTracker) -> None:
        today_str = datetime.now().strftime("%Y-%m-%d")
        tracker._daily_reset_date = today_str
        past_time = datetime.now() - timedelta(seconds=30)
        tracker._last_power = 500.0
        tracker._last_update_time = past_time.isoformat()

        data = {
            "total_energy_charged": 0,
            "total_energy_discharged": 0,
            "total_consumption": 100.0,
            "available_energy": 5000,
            "power": -500,  # avg = (500 + -500) / 2 = 0
            "soc": 50,
        }

        tracker.update(data)

        assert data["energy_charged_today"] == 0
        assert data["energy_discharged_today"] == 0

    def test_power_integration_no_previous_data(self, tracker: EnergyTracker) -> None:
        today_str = datetime.now().strftime("%Y-%m-%d")
        tracker._daily_reset_date = today_str
        tracker._last_power = None
        tracker._last_update_time = None

        data = {
            "total_energy_charged": 0,
            "total_energy_discharged": 0,
            "total_consumption": 100.0,
            "available_energy": 5000,
            "power": -500,
            "soc": 60,
        }

        tracker.update(data)

        assert data["energy_charged_today"] == 0
        assert data["energy_discharged_today"] == 0
        assert tracker._last_power == -500
        assert tracker._last_update_time is not None

    def test_power_integration_invalid_time(self, tracker: EnergyTracker) -> None:
        today_str = datetime.now().strftime("%Y-%m-%d")
        tracker._daily_reset_date = today_str
        tracker._last_power = -500.0
        tracker._last_update_time = "not-a-valid-time"

        data = {
            "total_energy_charged": 0,
            "total_energy_discharged": 0,
            "total_consumption": 100.0,
            "available_energy": 5000,
            "power": -500,
            "soc": 60,
        }

        # Should not raise (handles ValueError gracefully)
        tracker.update(data)

        assert tracker._last_power == -500

    def test_24h_consumption_calculation(self, tracker: EnergyTracker) -> None:
        today_str = datetime.now().strftime("%Y-%m-%d")
        tracker._daily_reset_date = today_str
        tracker._daily_charged_start = 100.0
        tracker._daily_discharged_start = 80.0
        old_time = (datetime.now() - timedelta(hours=12)).isoformat()
        tracker._consumption_24h_history = [(old_time, 200.0)]

        data = {
            "total_energy_charged": 105.0,
            "total_energy_discharged": 83.0,
            "total_consumption": 230.0,
            "available_energy": 5000,
            "power": 500,
        }

        tracker.update(data)

        assert data["consumption_24h"] == 30.0

    def test_24h_consumption_removes_old_entries(self, tracker: EnergyTracker) -> None:
        today_str = datetime.now().strftime("%Y-%m-%d")
        tracker._daily_reset_date = today_str
        tracker._daily_charged_start = 100.0
        tracker._daily_discharged_start = 80.0
        now = datetime.now()
        tracker._consumption_24h_history = [
            ((now - timedelta(hours=25)).isoformat(), 100.0),
            ((now - timedelta(hours=1)).isoformat(), 200.0),
        ]

        data = {
            "total_energy_charged": 105.0,
            "total_energy_discharged": 83.0,
            "total_consumption": 250.0,
            "available_energy": 5000,
            "power": 500,
        }

        tracker.update(data)

        assert len(tracker._consumption_24h_history) == 2  # old removed, new appended
        assert data["consumption_24h"] == 50.0

    def test_24h_consumption_single_entry(self, tracker: EnergyTracker) -> None:
        today_str = datetime.now().strftime("%Y-%m-%d")
        tracker._daily_reset_date = today_str
        tracker._daily_charged_start = 100.0
        tracker._daily_discharged_start = 80.0
        tracker._consumption_24h_history = []

        data = {
            "total_energy_charged": 105.0,
            "total_energy_discharged": 83.0,
            "total_consumption": 250.0,
            "available_energy": 5000,
            "power": 500,
        }

        tracker.update(data)

        assert data["consumption_24h"] == 0

    def test_backup_time_from_discharge_power(self, tracker: EnergyTracker) -> None:
        today_str = datetime.now().strftime("%Y-%m-%d")
        tracker._daily_reset_date = today_str
        tracker._daily_charged_start = 100.0
        tracker._daily_discharged_start = 80.0

        data = {
            "total_energy_charged": 105.0,
            "total_energy_discharged": 83.0,
            "total_consumption": 250.0,
            "available_energy": 5000,  # Wh
            "power": 1000,  # discharging
        }

        tracker.update(data)

        assert data["estimated_backup_time"] == 300  # 5000/1000*60

    def test_backup_time_from_avg_consumption(self, tracker: EnergyTracker) -> None:
        today_str = datetime.now().strftime("%Y-%m-%d")
        tracker._daily_reset_date = today_str
        tracker._daily_charged_start = 100.0
        tracker._daily_discharged_start = 80.0
        old_time = (datetime.now() - timedelta(hours=12)).isoformat()
        tracker._consumption_24h_history = [(old_time, 176.0)]

        data = {
            "total_energy_charged": 105.0,
            "total_energy_discharged": 83.0,
            "total_consumption": 200.0,  # 24 kWh over 12h = 2000W avg
            "available_energy": 4000,
            "power": 0,
        }

        tracker.update(data)

        assert data["estimated_backup_time"] == 120  # 4000/2000*60

    def test_backup_time_zero_when_no_consumption(self, tracker: EnergyTracker) -> None:
        today_str = datetime.now().strftime("%Y-%m-%d")
        tracker._daily_reset_date = today_str
        tracker._daily_charged_start = 100.0
        tracker._daily_discharged_start = 80.0

        data = {
            "total_energy_charged": 105.0,
            "total_energy_discharged": 83.0,
            "total_consumption": 250.0,
            "available_energy": 5000,
            "power": 0,
        }

        tracker.update(data)

        assert data["estimated_backup_time"] == 0

    def test_backup_time_charging_battery(self, tracker: EnergyTracker) -> None:
        today_str = datetime.now().strftime("%Y-%m-%d")
        tracker._daily_reset_date = today_str
        tracker._daily_charged_start = 100.0
        tracker._daily_discharged_start = 80.0

        data = {
            "total_energy_charged": 105.0,
            "total_energy_discharged": 83.0,
            "total_consumption": 250.0,
            "available_energy": 3000,
            "power": -500,  # charging; abs used
        }

        tracker.update(data)

        assert data["estimated_backup_time"] == 360  # 3000/500*60

    def test_meter_energy_negative_clamped_to_zero(self, tracker: EnergyTracker) -> None:
        today_str = datetime.now().strftime("%Y-%m-%d")
        tracker._daily_reset_date = today_str
        tracker._daily_charged_start = 200.0
        tracker._daily_discharged_start = 150.0

        data = {
            "total_energy_charged": 100.0,  # less than start (meter reset)
            "total_energy_discharged": 80.0,
            "total_consumption": 250.0,
            "available_energy": 5000,
            "power": 500,
        }

        tracker.update(data)

        # Clamped to 0 then power-integration fallback kicks in (no prev data → 0)
        assert data["energy_charged_today"] == 0
        assert data["energy_discharged_today"] == 0


# ---------------------------------------------------------------------------
# update: batched-save signalling
# ---------------------------------------------------------------------------


class TestUpdateSaveDue:
    """The save_due return value drives batched persistence."""

    def _data(self) -> dict:
        today_str = datetime.now().strftime("%Y-%m-%d")
        return {
            "total_energy_charged": 105.0,
            "total_energy_discharged": 83.0,
            "total_consumption": 250.0,
            "available_energy": 5000,
            "power": 500,
            "_reset": today_str,
        }

    def test_save_due_on_first_update(self, tracker: EnergyTracker) -> None:
        tracker._daily_reset_date = datetime.now().strftime("%Y-%m-%d")
        tracker._last_storage_save = None

        assert tracker.update(self._data()) is True
        assert tracker._last_storage_save is not None

    def test_save_skipped_when_recent(self, tracker: EnergyTracker) -> None:
        tracker._daily_reset_date = datetime.now().strftime("%Y-%m-%d")
        recent = datetime.now() - timedelta(seconds=30)
        tracker._last_storage_save = recent

        assert tracker.update(self._data()) is False
        assert tracker._last_storage_save == recent

    def test_save_due_after_interval(self, tracker: EnergyTracker) -> None:
        tracker._daily_reset_date = datetime.now().strftime("%Y-%m-%d")
        old = datetime.now() - timedelta(minutes=6)
        tracker._last_storage_save = old

        assert tracker.update(self._data()) is True
        assert tracker._last_storage_save != old
