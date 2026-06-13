"""Energy tracking for the Enphase Battery integration.

Encapsulates the daily charge/discharge counters, the 24h rolling consumption
window and the estimated backup time. The pure computation (:meth:`update`)
is kept separate from persistence (:meth:`async_load` / :meth:`async_save`) so
the logic can be unit-tested without Home Assistant.
"""

from __future__ import annotations

from datetime import datetime, timedelta
import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from homeassistant.helpers.storage import Store

    from .api import BatteryData

_LOGGER = logging.getLogger(__name__)

# Persistent storage identifiers (kept stable for backward compatibility).
STORAGE_VERSION = 1
STORAGE_KEY = "enphase_battery_energy_tracking"

# Save persisted state at most once per this interval.
STORAGE_SAVE_INTERVAL = timedelta(minutes=5)


class EnergyTracker:
    """Track daily energy, 24h consumption and estimated backup time."""

    def __init__(self, store: Store[dict[str, Any]]) -> None:
        """Initialize the tracker with a persistent store."""
        self._store = store
        self._stored_data: dict[str, Any] = {}

        # Daily energy counters (meter-based)
        self._daily_reset_date: str | None = None
        self._daily_charged_start: float = 0
        self._daily_discharged_start: float = 0
        self._consumption_24h_history: list[tuple[str, float]] = []

        # SOC-based tracking (fallback reference)
        self._last_soc: int | None = None
        self._daily_soc_charged: float = 0
        self._daily_soc_discharged: float = 0

        # Power-integration tracking (most accurate fallback)
        self._last_power: float | None = None
        self._last_update_time: str | None = None
        self._daily_power_charged: float = 0
        self._daily_power_discharged: float = 0

        # Batched persistence
        self._last_storage_save: datetime | None = None
        self._storage_save_interval = STORAGE_SAVE_INTERVAL

    async def async_load(self) -> None:
        """Load energy tracking data from persistent storage."""
        try:
            self._stored_data = await self._store.async_load() or {}

            self._daily_reset_date = self._stored_data.get("reset_date")
            self._daily_charged_start = self._stored_data.get("charged_start", 0)
            self._daily_discharged_start = self._stored_data.get("discharged_start", 0)
            self._consumption_24h_history = self._stored_data.get("consumption_history", [])
            self._last_soc = self._stored_data.get("last_soc")
            self._daily_soc_charged = self._stored_data.get("soc_charged", 0)
            self._daily_soc_discharged = self._stored_data.get("soc_discharged", 0)
            self._last_power = self._stored_data.get("last_power")
            self._last_update_time = self._stored_data.get("last_update_time")
            self._daily_power_charged = self._stored_data.get("power_charged", 0)
            self._daily_power_discharged = self._stored_data.get("power_discharged", 0)

            if self._daily_reset_date:
                _LOGGER.debug("Restored energy tracking from %s", self._daily_reset_date)
        except Exception as err:
            _LOGGER.error("Failed to load energy tracking data: %s", err)

    async def async_save(self) -> None:
        """Save energy tracking data to persistent storage."""
        try:
            data = {
                "reset_date": self._daily_reset_date,
                "charged_start": self._daily_charged_start,
                "discharged_start": self._daily_discharged_start,
                "consumption_history": self._consumption_24h_history[-100:],
                "last_soc": self._last_soc,
                "soc_charged": self._daily_soc_charged,
                "soc_discharged": self._daily_soc_discharged,
                "last_power": self._last_power,
                "last_update_time": self._last_update_time,
                "power_charged": self._daily_power_charged,
                "power_discharged": self._daily_power_discharged,
            }
            await self._store.async_save(data)
        except Exception as err:
            _LOGGER.error("Failed to save energy tracking data: %s", err)

    def update(self, data: BatteryData) -> bool:
        """Compute derived energy values and update ``data`` in place.

        Returns ``True`` when persisted state should be saved (batched so the
        caller schedules :meth:`async_save_safe` at most every few minutes).
        """
        now = datetime.now()
        today_str = now.strftime("%Y-%m-%d")

        total_charged = data.get("total_energy_charged", 0)  # kWh
        total_discharged = data.get("total_energy_discharged", 0)  # kWh
        total_consumption = data.get("total_consumption", 0)  # kWh

        # Reset daily counters at midnight
        if self._daily_reset_date != today_str:
            self._daily_reset_date = today_str
            self._daily_charged_start = total_charged
            self._daily_discharged_start = total_discharged
            self._daily_soc_charged = 0
            self._daily_soc_discharged = 0
            self._daily_power_charged = 0
            self._daily_power_discharged = 0

        # Daily energy from meters (if available)
        energy_charged_today = max(0, total_charged - self._daily_charged_start)
        energy_discharged_today = max(0, total_discharged - self._daily_discharged_start)

        # Fallback: if meters don't track battery energy (= 0), use power integration
        if energy_charged_today == 0 and energy_discharged_today == 0:
            current_power = data.get("power", 0)  # W (negative=charging, positive=discharging)

            if self._last_power is not None and self._last_update_time is not None:
                try:
                    last_time = datetime.fromisoformat(self._last_update_time)
                    time_delta_hours = (now - last_time).total_seconds() / 3600

                    # Average power over the interval (trapezoidal integration)
                    avg_power = (current_power + self._last_power) / 2  # W
                    energy_delta_kwh = (avg_power * time_delta_hours) / 1000

                    if avg_power < 0:
                        self._daily_power_charged += abs(energy_delta_kwh)
                    elif avg_power > 0:
                        self._daily_power_discharged += energy_delta_kwh
                except (ValueError, TypeError) as e:
                    _LOGGER.warning("Error in power integration: %s", e)

            self._last_power = current_power
            self._last_update_time = now.isoformat()

            energy_charged_today = self._daily_power_charged
            energy_discharged_today = self._daily_power_discharged

            # SOC tracking for backup reference
            self._last_soc = data.get("soc", 0)

        data["energy_charged_today"] = round(energy_charged_today, 2)
        data["energy_discharged_today"] = round(energy_discharged_today, 2)

        # 24h rolling consumption
        self._consumption_24h_history.append((now.isoformat(), total_consumption))
        cutoff_time = now - timedelta(hours=24)
        self._consumption_24h_history = [
            (ts, cons) for ts, cons in self._consumption_24h_history if datetime.fromisoformat(ts) > cutoff_time
        ]

        if len(self._consumption_24h_history) >= 2:
            oldest_consumption = self._consumption_24h_history[0][1]
            consumption_24h = max(0, total_consumption - oldest_consumption)
        else:
            consumption_24h = 0

        data["consumption_24h"] = round(consumption_24h, 2)

        # Estimated backup time (minutes): available energy / current draw
        available_energy_wh = data.get("available_energy", 0)
        discharge_power = abs(data.get("power", 0))

        if discharge_power > 0:
            backup_time_minutes = int((available_energy_wh / discharge_power) * 60)
        elif consumption_24h > 0 and len(self._consumption_24h_history) >= 2:
            hours_tracked = (now - datetime.fromisoformat(self._consumption_24h_history[0][0])).total_seconds() / 3600
            avg_power = (consumption_24h * 1000) / hours_tracked  # kWh -> W
            backup_time_minutes = int((available_energy_wh / avg_power) * 60) if avg_power > 0 else 0
        else:
            backup_time_minutes = 0

        data["estimated_backup_time"] = backup_time_minutes

        # Tell the caller whether to persist (batched)
        if self._last_storage_save is None or (now - self._last_storage_save) >= self._storage_save_interval:
            self._last_storage_save = now
            return True
        return False
