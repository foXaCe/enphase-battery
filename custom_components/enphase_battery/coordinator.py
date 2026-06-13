"""DataUpdateCoordinator for Enphase Battery."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.debounce import Debouncer
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)

from .api import (
    BatteryData,
    EnphaseBatteryAPI,
    EnphaseBatteryApiError,
    EnphaseBatteryAuthError,
    EnphaseEnvoyLocalAPI,
    EnvoyAuthError,
    EnvoyLocalApiError,
)
from .const import (
    CONF_CONNECTION_MODE,
    CONF_ENABLE_CLOUD_CONTROL,
    CONF_ENVOY_HOST,
    CONF_SITE_ID,
    CONF_USER_ID,
    CONNECTION_MODE_CLOUD,
    CONNECTION_MODE_LOCAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    LOCAL_SCAN_INTERVAL,
)
from .energy import STORAGE_KEY, STORAGE_VERSION, EnergyTracker

_LOGGER = logging.getLogger(__name__)

# Debounce delay for refresh requests (prevents rapid consecutive refreshes)
REQUEST_REFRESH_DEBOUNCE_COOLDOWN = 1.0  # seconds


class EnphaseBatteryDataUpdateCoordinator(DataUpdateCoordinator[BatteryData]):
    """Class to manage fetching Enphase Battery data.

    Supports dual connection modes:
    - Local mode: Direct connection to Envoy (10s polling, no API limits)
    - Cloud mode: Enphase Enlighten API (60s polling)
    """

    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the coordinator."""
        self.entry = entry
        self.api: EnphaseBatteryAPI | None = None
        self.local_api: EnphaseEnvoyLocalAPI | None = None

        # Persistent energy tracking (daily counters, 24h consumption, backup time)
        store: Store[dict[str, Any]] = Store(hass, STORAGE_VERSION, f"{STORAGE_KEY}_{entry.entry_id}")
        self._energy = EnergyTracker(store)

        # Determine connection mode (default to cloud for backward compatibility)
        self._connection_mode = entry.data.get(CONF_CONNECTION_MODE, CONNECTION_MODE_CLOUD)

        # Track last warning time for rate limiting repeated errors
        self._last_cloud_error_warning: datetime | None = None

        # Track unavailable state for log-when-unavailable pattern
        self._previously_unavailable: bool = False

        # Offset first poll to avoid colliding with official enphase_envoy integration
        self._first_poll: bool = True

        # Cache for cloud control states in hybrid mode (refresh every 5 minutes)
        self._last_cloud_control_fetch: datetime | None = None
        self._cloud_control_cache: dict[str, Any] = {}
        self._cloud_control_cache_interval = timedelta(minutes=1)

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
            config_entry=entry,
            update_interval=update_interval,
            request_refresh_debouncer=Debouncer(
                hass,
                _LOGGER,
                cooldown=REQUEST_REFRESH_DEBOUNCE_COOLDOWN,
                immediate=False,
            ),
        )

        _LOGGER.debug(
            "Coordinator initialized in %s mode (interval: %ss)",
            mode_description,
            update_interval.total_seconds(),
        )

    async def _async_setup(self) -> None:
        """Authenticate and load persistent state.

        Called once by ``async_config_entry_first_refresh`` before the first
        data fetch. Authentication and storage loading run in parallel. Auth
        failures are translated to ``ConfigEntryAuthFailed`` (triggers reauth)
        and connection failures to ``UpdateFailed`` (HA retries the setup).
        """
        session = async_get_clientsession(self.hass)
        enable_cloud_control = self.entry.data.get(CONF_ENABLE_CLOUD_CONTROL, False)

        try:
            if self._connection_mode == CONNECTION_MODE_LOCAL:
                if enable_cloud_control:
                    # Hybrid mode: parallelize local API + cloud API + storage loading
                    _LOGGER.debug("Hybrid mode: parallelizing local + cloud auth + storage")
                    await asyncio.gather(
                        self._setup_local_api(session),
                        self._setup_cloud_api_from_local_creds(session),
                        self._energy.async_load(),
                    )
                else:
                    # Local mode only: parallelize local API + storage loading
                    await asyncio.gather(
                        self._setup_local_api(session),
                        self._energy.async_load(),
                    )
            else:
                # Cloud mode: parallelize cloud API + storage loading
                await asyncio.gather(
                    self._setup_cloud_api(session),
                    self._energy.async_load(),
                )
        except (EnvoyAuthError, EnphaseBatteryAuthError) as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except (EnvoyLocalApiError, EnphaseBatteryApiError) as err:
            raise UpdateFailed(f"Error setting up Enphase Battery: {err}") from err

    async def _setup_local_api(self, session) -> None:  # type: ignore[no-untyped-def]
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

        # Authenticate. Errors are logged with the right severity by HA once
        # _async_setup maps them to ConfigEntryNotReady / ConfigEntryAuthFailed.
        try:
            await self.local_api.authenticate()
            _LOGGER.debug("Successfully authenticated with local Envoy at %s", host)
        except EnvoyLocalApiError as err:
            _LOGGER.debug("Failed to authenticate with local Envoy: %s", err)
            raise

    async def _setup_cloud_api(self, session) -> None:  # type: ignore[no-untyped-def]
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

    async def _setup_cloud_api_from_local_creds(self, session) -> None:  # type: ignore[no-untyped-def]
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

    async def _async_update_data(self) -> BatteryData:
        """Fetch data from API.

        Mode behavior:
        - Local mode: Primary data source (every 10s)
        - Cloud mode: Primary data source (every 60s)
        """
        try:
            # Offset first poll by 5s to desynchronize from official enphase_envoy integration
            # Both integrations start at HA boot, so without offset their cycles collide
            # causing Envoy 503 overload errors
            if self._first_poll and self._connection_mode == CONNECTION_MODE_LOCAL:
                self._first_poll = False
                await asyncio.sleep(5)

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
                    data = await self.local_api.get_battery_data()  # type: ignore[union-attr]
                except EnvoyAuthError:
                    # Token expired - try to re-authenticate automatically
                    _LOGGER.info("Token expired, attempting automatic re-authentication")
                    try:
                        await self.local_api.authenticate()  # type: ignore[union-attr]
                        _LOGGER.info("Re-authentication successful, retrying data fetch")
                        data = await self.local_api.get_battery_data()  # type: ignore[union-attr]
                    except EnvoyAuthError as err:
                        # Re-auth also failed - trigger reauth flow
                        raise ConfigEntryAuthFailed(f"Authentication failed: {err}") from err
                    except EnvoyLocalApiError as err:
                        raise UpdateFailed(f"Error fetching local data after reauth: {err}") from err
                except EnvoyLocalApiError as err:
                    raise UpdateFailed(f"Error fetching local data: {err}") from err

                # Hybrid mode: Merge control states from cloud API (cached for 5 minutes)
                # In hybrid mode, control changes (switch/select) are made via cloud API,
                # but local API may not immediately reflect these changes.
                # Read charge_from_grid, mode, dtgControl, and rbdControl from cloud to show real-time UI updates.
                if self.api:  # Cloud API is initialized (hybrid mode)
                    now = datetime.now()
                    # Only fetch from cloud if cache is stale (older than 5 minutes)
                    should_fetch = (
                        self._last_cloud_control_fetch is None
                        or (now - self._last_cloud_control_fetch) >= self._cloud_control_cache_interval
                    )

                    if should_fetch:
                        try:
                            cloud_settings = await self.api.get_battery_settings()
                            _LOGGER.debug(
                                "Cloud battery settings raw: dtgControl=%s, rbdControl=%s, chargeFromGrid=%s",
                                cloud_settings.get("dtgControl"),
                                cloud_settings.get("rbdControl"),
                                cloud_settings.get("chargeFromGrid"),
                            )
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
                                "power_match": (
                                    cloud_settings.get("powerMatchControl", {}).get("enabled", False)
                                    if isinstance(cloud_settings.get("powerMatchControl"), dict)
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
                        data["power_match"] = self._cloud_control_cache.get(
                            "power_match", data.get("power_match", False)
                        )

            else:
                # Cloud mode: Get data from Enlighten API
                try:
                    data = await self.api.get_battery_data()  # type: ignore[union-attr]
                except EnphaseBatteryAuthError:
                    # Token expired - try to re-authenticate automatically
                    _LOGGER.info("Cloud token expired, attempting automatic re-authentication")
                    try:
                        await self.api.authenticate()  # type: ignore[union-attr]
                        _LOGGER.info("Cloud re-authentication successful, retrying data fetch")
                        data = await self.api.get_battery_data()  # type: ignore[union-attr]
                    except EnphaseBatteryAuthError as err:
                        raise ConfigEntryAuthFailed(f"Authentication failed: {err}") from err
                    except EnphaseBatteryApiError as err:
                        raise UpdateFailed(f"Error fetching cloud data after reauth: {err}") from err
                except EnphaseBatteryApiError as err:
                    raise UpdateFailed(f"Error fetching cloud data: {err}") from err

            # Update derived energy values; persist (batched) when the tracker says it is due.
            # async_save never raises (it logs and swallows), so it is safe as a background task.
            if self._energy.update(data):
                self.hass.async_create_task(self._energy.async_save(), "enphase_battery_save_energy")

            # Log once when connection is restored after being unavailable
            if self._previously_unavailable:
                _LOGGER.info("Connection restored to Enphase system")
                self._previously_unavailable = False

            return data

        except UpdateFailed:
            if not self._previously_unavailable:
                _LOGGER.warning("Connection lost to Enphase system")
                self._previously_unavailable = True
            raise
        except ConfigEntryAuthFailed:
            raise
        except Exception as err:
            if not self._previously_unavailable:
                _LOGGER.warning("Connection lost to Enphase system")
                self._previously_unavailable = True
            raise UpdateFailed(f"Unexpected error fetching data: {err}") from err

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
        await self._energy.async_save()
        _LOGGER.debug("Energy tracking data saved on shutdown")

        if self.local_api:
            await self.local_api.close()
            _LOGGER.debug("Local Envoy API client closed")

    @property
    def unique_id_prefix(self) -> str:
        """Stable per-entry prefix for entity unique IDs."""
        return self.config_entry.entry_id

    @property
    def envoy_serial(self) -> str | None:
        """Return the Envoy serial number (local mode), if known."""
        return self.local_api.serial_number if self.local_api else None

    @property
    def envoy_firmware(self) -> str | None:
        """Return the Envoy firmware version (local mode), if known."""
        return self.local_api.firmware_version if self.local_api else None

    @property
    def connection_mode(self) -> str:
        """Return current connection mode."""
        return self._connection_mode  # type: ignore[no-any-return]

    @property
    def is_local_mode(self) -> bool:
        """Return True if using local Envoy connection."""
        return self._connection_mode == CONNECTION_MODE_LOCAL  # type: ignore[no-any-return]

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
