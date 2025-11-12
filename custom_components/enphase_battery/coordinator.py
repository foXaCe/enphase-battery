"""DataUpdateCoordinator for Enphase Battery."""

from __future__ import annotations

from datetime import datetime, timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)

from .api import EnphaseBatteryAPI, EnphaseBatteryApiError
from .const import (
    CONF_CONNECTION_MODE,
    CONF_ENVOY_HOST,
    CONF_SITE_ID,
    CONF_USER_ID,
    CONNECTION_MODE_CLOUD,
    CONNECTION_MODE_LOCAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    LOCAL_SCAN_INTERVAL,
)
from .envoy_local_api import EnphaseEnvoyLocalAPI, EnvoyLocalApiError

_LOGGER = logging.getLogger(__name__)

# Storage version and key for persistent energy tracking
STORAGE_VERSION = 1
STORAGE_KEY = "enphase_battery_energy_tracking"


class EnphaseBatteryDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching Enphase Battery data.

    Supports dual connection modes:
    - Local mode: Direct connection to Envoy (10s polling, no API limits)
    - Cloud mode: Enphase Enlighten API (60s polling)
    """

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the coordinator."""
        self.entry = entry
        self.api: EnphaseBatteryAPI | None = None
        self.local_api: EnphaseEnvoyLocalAPI | None = None

        # Initialize persistent storage for energy tracking
        self._store = Store(hass, STORAGE_VERSION, f"{STORAGE_KEY}_{entry.entry_id}")
        self._stored_data: dict[str, Any] = {}

        # Energy tracking for daily calculations
        # Will be loaded from persistent storage in async_setup
        stored_data: dict[str, Any] = {}

        self._daily_reset_date: str | None = stored_data.get("reset_date")
        self._daily_charged_start: float = stored_data.get("charged_start", 0)
        self._daily_discharged_start: float = stored_data.get("discharged_start", 0)
        self._consumption_24h_history: list[tuple[str, float]] = stored_data.get("consumption_history", [])

        # SOC-based energy tracking (fallback when meters don't track battery energy)
        self._last_soc: int | None = stored_data.get("last_soc")
        self._daily_soc_charged: float = stored_data.get("soc_charged", 0)
        self._daily_soc_discharged: float = stored_data.get("soc_discharged", 0)

        # Power integration energy tracking (most accurate method)
        self._last_power: float | None = stored_data.get("last_power")
        self._last_update_time: str | None = stored_data.get("last_update_time")
        self._daily_power_charged: float = stored_data.get("power_charged", 0)
        self._daily_power_discharged: float = stored_data.get("power_discharged", 0)

        # Determine connection mode (default to cloud for backward compatibility)
        self._connection_mode = entry.data.get(CONF_CONNECTION_MODE, CONNECTION_MODE_CLOUD)

        # Track last warning time for rate limiting repeated errors
        self._last_cloud_error_warning: datetime | None = None

        # Track last save time for batching storage writes (save every 5 minutes)
        self._last_storage_save: datetime | None = None
        self._storage_save_interval = timedelta(minutes=5)

        # Cache for cloud control states in hybrid mode (refresh every 2 minutes)
        self._last_cloud_control_fetch: datetime | None = None
        self._cloud_control_cache: dict[str, Any] = {}
        self._cloud_control_cache_interval = timedelta(minutes=2)

        # Determine update interval based on connection mode
        if self._connection_mode == CONNECTION_MODE_LOCAL:
            # Local mode: Fast polling (10s)
            update_interval = timedelta(seconds=LOCAL_SCAN_INTERVAL)
            mode_description = "Local (Envoy direct)"
        else:
            # Cloud mode: Standard polling (60s)
            update_interval = timedelta(seconds=DEFAULT_SCAN_INTERVAL)
            mode_description = "Cloud (polling)"

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=update_interval,
        )

        _LOGGER.debug(
            "Coordinator initialized in %s mode (interval: %ss)",
            mode_description,
            update_interval.total_seconds(),
        )

    async def _async_setup(self) -> None:
        """Set up the coordinator based on connection mode."""
        # Load persistent energy tracking data
        await self._load_energy_tracking()

        session = async_get_clientsession(self.hass)
        enable_cloud_control = self.entry.data.get("enable_cloud_control", False)

        if self._connection_mode == CONNECTION_MODE_LOCAL:
            # Local mode: Initialize Envoy local API
            await self._setup_local_api(session)

            # Hybrid mode: Also initialize cloud API for control if enabled
            if enable_cloud_control:
                _LOGGER.debug("Hybrid mode enabled: initializing cloud API for control")
                await self._setup_cloud_api_from_local_creds(session)
        else:
            # Cloud mode: Initialize cloud API
            await self._setup_cloud_api(session)

    async def _setup_local_api(self, session) -> None:
        """Set up local Envoy API client."""
        host = self.entry.data.get(CONF_ENVOY_HOST, "envoy.local")
        username = self.entry.data.get(CONF_USERNAME, "installer")
        password = self.entry.data.get(CONF_PASSWORD)
        cloud_username = self.entry.data.get("cloud_username")
        cloud_password = self.entry.data.get("cloud_password")

        _LOGGER.debug("Setting up local Envoy API connection to %s", host)

        self.local_api = EnphaseEnvoyLocalAPI(
            session=session,
            host=host,
            username=username,
            password=password,
            cloud_username=cloud_username,
            cloud_password=cloud_password,
        )

        # Authenticate
        try:
            await self.local_api.authenticate()
            _LOGGER.debug("Successfully authenticated with local Envoy at %s", host)
        except EnvoyLocalApiError as err:
            _LOGGER.error("Failed to authenticate with local Envoy: %s", err)
            raise

    async def _setup_cloud_api(self, session) -> None:
        """Set up cloud Enlighten API client."""
        # Get optional site_id and user_id from config
        site_id_str = self.entry.data.get(CONF_SITE_ID)
        site_id = int(site_id_str) if site_id_str else None

        user_id_str = self.entry.data.get(CONF_USER_ID)
        user_id = int(user_id_str) if user_id_str else None

        _LOGGER.debug("Setting up cloud API connection to Enphase Enlighten")

        # Initialize API client
        self.api = EnphaseBatteryAPI(
            session=session,
            username=self.entry.data.get(CONF_USERNAME, ""),
            password=self.entry.data.get(CONF_PASSWORD, ""),
            site_id=site_id,
            user_id=user_id,
        )

        # Authenticate
        try:
            await self.api.authenticate()
            _LOGGER.debug("Successfully authenticated with Enphase cloud")

            # Save auto-detected IDs to config to avoid re-detection on next startup
            if self.api._site_id and self.api._user_id and (not site_id or not user_id):
                _LOGGER.debug("Saving auto-detected IDs: site_id=%s, user_id=%s", self.api._site_id, self.api._user_id)
                new_data = {
                    **self.entry.data,
                    CONF_SITE_ID: str(self.api._site_id),
                    CONF_USER_ID: str(self.api._user_id),
                }
                self.hass.config_entries.async_update_entry(self.entry, data=new_data)
        except EnphaseBatteryApiError as err:
            _LOGGER.error("Failed to authenticate with cloud: %s", err)
            raise

    async def _setup_cloud_api_from_local_creds(self, session) -> None:
        """Set up cloud API using credentials from local mode config (hybrid mode)."""
        cloud_username = self.entry.data.get("cloud_username")
        cloud_password = self.entry.data.get("cloud_password")

        if not cloud_username or not cloud_password:
            _LOGGER.error("Cloud credentials not found in local mode config. Cannot enable cloud control.")
            return

        # Get saved site_id and user_id to avoid re-detection (saves 5-7 seconds)
        site_id_str = self.entry.data.get(CONF_SITE_ID)
        site_id = int(site_id_str) if site_id_str else None

        user_id_str = self.entry.data.get(CONF_USER_ID)
        user_id = int(user_id_str) if user_id_str else None

        _LOGGER.debug("Setting up cloud API for control (hybrid mode)")

        # Initialize API client
        self.api = EnphaseBatteryAPI(
            session=session,
            username=cloud_username,
            password=cloud_password,
            site_id=site_id,
            user_id=user_id,
        )

        # Authenticate
        try:
            await self.api.authenticate()
            _LOGGER.debug("Successfully authenticated with Enphase cloud for control")

            # Save auto-detected IDs to config to avoid re-detection on next startup
            if self.api._site_id and self.api._user_id and (not site_id or not user_id):
                _LOGGER.debug(
                    "Saving auto-detected IDs: site_id=%s, user_id=%s",
                    self.api._site_id,
                    self.api._user_id,
                )
                new_data = {
                    **self.entry.data,
                    CONF_SITE_ID: str(self.api._site_id),
                    CONF_USER_ID: str(self.api._user_id),
                }
                self.hass.config_entries.async_update_entry(self.entry, data=new_data)
        except EnphaseBatteryApiError as err:
            _LOGGER.error("Failed to authenticate with cloud for control: %s", err)
            # Don't raise - allow local mode to continue without control
            self.api = None

    async def _load_energy_tracking(self) -> None:
        """Load energy tracking data from persistent storage."""
        try:
            self._stored_data = await self._store.async_load() or {}

            # Restore variables from storage
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
                _LOGGER.debug(f"Restored energy tracking from {self._daily_reset_date}")
        except Exception as err:
            _LOGGER.error(f"Failed to load energy tracking data: {err}")

    async def _save_energy_tracking(self) -> None:
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
            _LOGGER.error(f"Failed to save energy tracking data: {err}")

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from API.

        Mode behavior:
        - Local mode: Primary data source (every 10s)
        - Cloud mode: Primary data source (every 60s)
        """
        try:
            # Ensure API is initialized
            if self._connection_mode == CONNECTION_MODE_LOCAL:
                if not self.local_api:
                    await self._async_setup()
            else:
                if not self.api:
                    await self._async_setup()

            # Get battery data from appropriate source
            if self._connection_mode == CONNECTION_MODE_LOCAL:
                # Local mode: Get data from Envoy
                try:
                    data = await self.local_api.get_battery_data()
                except EnvoyLocalApiError as err:
                    raise UpdateFailed(f"Error fetching local data: {err}") from err

                # Hybrid mode: Merge control states from cloud API (cached for 2 minutes)
                # In hybrid mode, control changes (switch/select) are made via cloud API,
                # but local API may not immediately reflect these changes.
                # Read charge_from_grid, mode, dtgControl, and rbdControl from cloud to show real-time UI updates.
                if self.api:  # Cloud API is initialized (hybrid mode)
                    now = datetime.now()
                    # Only fetch from cloud if cache is stale (older than 2 minutes)
                    should_fetch = (
                        self._last_cloud_control_fetch is None
                        or (now - self._last_cloud_control_fetch) >= self._cloud_control_cache_interval
                    )

                    if should_fetch:
                        try:
                            cloud_settings = await self.api.get_battery_settings()
                            self._cloud_control_cache = {
                                "charge_from_grid": cloud_settings.get("chargeFromGrid", False),
                                "mode": cloud_settings.get("profile", "unknown"),
                                "discharge_to_grid": (
                                    cloud_settings.get("dtgControl", {}).get("enabled", False)
                                    if isinstance(cloud_settings.get("dtgControl"), dict)
                                    else False
                                ),
                                "reserve_battery_discharge": (
                                    cloud_settings.get("rbdControl", {}).get("enabled", False)
                                    if isinstance(cloud_settings.get("rbdControl"), dict)
                                    else False
                                ),
                            }
                            self._last_cloud_control_fetch = now
                        except Exception as err:
                            # Rate limit warnings: only log every 5 minutes to avoid spam
                            if self._last_cloud_error_warning is None or (
                                now - self._last_cloud_error_warning
                            ) > timedelta(minutes=5):
                                _LOGGER.warning(
                                    "Hybrid mode: Failed to fetch cloud control states, using cached/local values: %s "
                                    "(This warning will be suppressed for 5 minutes)",
                                    err,
                                )
                                self._last_cloud_error_warning = now

                    # Apply cached values if available
                    if self._cloud_control_cache:
                        data["charge_from_grid"] = self._cloud_control_cache.get(
                            "charge_from_grid", data.get("charge_from_grid", False)
                        )
                        data["mode"] = self._cloud_control_cache.get("mode", data.get("mode", "unknown"))
                        data["discharge_to_grid"] = self._cloud_control_cache.get(
                            "discharge_to_grid", data.get("discharge_to_grid", False)
                        )
                        data["reserve_battery_discharge"] = self._cloud_control_cache.get(
                            "reserve_battery_discharge", data.get("reserve_battery_discharge", False)
                        )

            else:
                # Cloud mode: Get data from Enlighten API
                try:
                    data = await self.api.get_battery_data()
                except EnphaseBatteryApiError as err:
                    raise UpdateFailed(f"Error fetching cloud data: {err}") from err

            # Calculate daily energy and 24h consumption
            self._calculate_daily_values(data)

            return data

        except UpdateFailed:
            raise
        except Exception as err:
            raise UpdateFailed(f"Unexpected error fetching data: {err}") from err

    def _calculate_daily_values(self, data: dict[str, Any]) -> None:
        """Calculate daily energy values and 24h consumption.

        Args:
            data: Battery data dictionary to update with calculated values
        """
        from datetime import datetime

        now = datetime.now()
        today_str = now.strftime("%Y-%m-%d")

        # Get cumulative energy values from data
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

        # Calculate daily energy from meters (if available)
        energy_charged_today = max(0, total_charged - self._daily_charged_start)
        energy_discharged_today = max(0, total_discharged - self._daily_discharged_start)

        # Fallback: If meters don't track battery energy (= 0), use power integration
        if energy_charged_today == 0 and energy_discharged_today == 0:
            current_power = data.get("power", 0)  # W (negative=charging, positive=discharging)

            # Power integration: energy = ∫ power × time
            if self._last_power is not None and self._last_update_time is not None:
                try:
                    last_time = datetime.fromisoformat(self._last_update_time)
                    time_delta_hours = (now - last_time).total_seconds() / 3600  # Convert to hours

                    # Use average power over the interval (trapezoidal integration)
                    avg_power = (current_power + self._last_power) / 2  # W
                    energy_delta_kwh = (avg_power * time_delta_hours) / 1000  # Convert Wh to kWh

                    if avg_power < 0:
                        # Battery charging (negative power)
                        self._daily_power_charged += abs(energy_delta_kwh)
                    elif avg_power > 0:
                        # Battery discharging (positive power)
                        self._daily_power_discharged += energy_delta_kwh
                except (ValueError, TypeError) as e:
                    _LOGGER.warning(f"Error in power integration: {e}")

            # Update tracking variables for next iteration
            self._last_power = current_power
            self._last_update_time = now.isoformat()

            energy_charged_today = self._daily_power_charged
            energy_discharged_today = self._daily_power_discharged

            # SOC tracking for backup reference
            current_soc = data.get("soc", 0)
            self._last_soc = current_soc

        data["energy_charged_today"] = round(energy_charged_today, 2)
        data["energy_discharged_today"] = round(energy_discharged_today, 2)

        # 24h rolling consumption calculation
        timestamp_str = now.isoformat()
        self._consumption_24h_history.append((timestamp_str, total_consumption))

        # Remove entries older than 24h
        cutoff_time = now - timedelta(hours=24)
        self._consumption_24h_history = [
            (ts, cons) for ts, cons in self._consumption_24h_history if datetime.fromisoformat(ts) > cutoff_time
        ]

        # Calculate 24h consumption (delta between oldest and newest)
        if len(self._consumption_24h_history) >= 2:
            oldest_consumption = self._consumption_24h_history[0][1]
            consumption_24h = max(0, total_consumption - oldest_consumption)
        else:
            consumption_24h = 0

        data["consumption_24h"] = round(consumption_24h, 2)

        # Calculate estimated backup time (minutes)
        # Based on: available_energy (Wh) / current consumption rate (W) * 60
        available_energy_wh = data.get("available_energy", 0)
        discharge_power = abs(data.get("power", 0))  # Current power draw

        if discharge_power > 0:
            # Battery is discharging, calculate based on current rate
            backup_time_minutes = int((available_energy_wh / discharge_power) * 60)
        elif consumption_24h > 0 and len(self._consumption_24h_history) >= 2:
            # Use average consumption from 24h
            hours_tracked = (now - datetime.fromisoformat(self._consumption_24h_history[0][0])).total_seconds() / 3600
            avg_power = (consumption_24h * 1000) / hours_tracked  # Convert kWh to W
            backup_time_minutes = int((available_energy_wh / avg_power) * 60) if avg_power > 0 else 0
        else:
            backup_time_minutes = 0

        data["estimated_backup_time"] = backup_time_minutes

        # Save tracking data to persistent storage (batched every 5 minutes)
        now_time = datetime.now()
        if self._last_storage_save is None or (now_time - self._last_storage_save) >= self._storage_save_interval:
            self._last_storage_save = now_time
            self.hass.async_create_task(self._save_energy_tracking())

    def invalidate_cloud_control_cache(self) -> None:
        """Invalidate cached cloud control states to force immediate refresh.

        Call this after making control changes (switch/select) to ensure
        the next update fetches fresh values from the cloud API.
        """
        self._last_cloud_control_fetch = None
        _LOGGER.debug("Cloud control cache invalidated, will refresh on next update")

    async def async_shutdown(self) -> None:
        """Shutdown coordinator and cleanup resources."""
        # Save energy tracking data before shutdown
        await self._save_energy_tracking()
        _LOGGER.debug("Energy tracking data saved on shutdown")

        if self.local_api:
            await self.local_api.close()
            _LOGGER.debug("Local Envoy API client closed")

    @property
    def connection_mode(self) -> str:
        """Return current connection mode."""
        return self._connection_mode

    @property
    def is_local_mode(self) -> bool:
        """Return True if using local Envoy connection."""
        return self._connection_mode == CONNECTION_MODE_LOCAL

    @property
    def battery_soc(self) -> int | None:
        """Return current battery state of charge."""
        if not self.data:
            return None
        return self.data.get("soc")

    @property
    def battery_power(self) -> int | None:
        """Return current battery power (negative = charging, positive = discharging)."""
        if not self.data:
            return None
        return self.data.get("power")

    @property
    def battery_mode(self) -> str | None:
        """Return current battery operation mode."""
        if not self.data:
            return None
        return self.data.get("mode")

    @property
    def is_charging(self) -> bool:
        """Return True if battery is charging."""
        power = self.battery_power
        if power is None:
            return False
        return power < 0
