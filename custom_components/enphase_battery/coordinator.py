"""DataUpdateCoordinator for Enphase Battery."""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)

from .api import EnphaseBatteryAPI, EnphaseBatteryApiError
from .envoy_local_api import EnphaseEnvoyLocalAPI, EnvoyLocalApiError
from .const import (
    CONF_SITE_ID,
    CONF_USER_ID,
    CONF_USE_MQTT,
    CONF_CONNECTION_MODE,
    CONF_ENVOY_HOST,
    CONNECTION_MODE_LOCAL,
    CONNECTION_MODE_CLOUD,
    DEFAULT_SCAN_INTERVAL,
    LOCAL_SCAN_INTERVAL,
    DOMAIN,
    MQTT_SCAN_INTERVAL,
)

try:
    from .mqtt_client import EnphaseMQTTClient, MQTT_AVAILABLE
except ImportError:
    MQTT_AVAILABLE = False

_LOGGER = logging.getLogger(__name__)


class EnphaseBatteryDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching Enphase Battery data.

    Supports dual connection modes:
    - Local mode: Direct connection to Envoy (10s polling, no API limits)
    - Cloud mode: Enphase Enlighten API (60s polling OR MQTT real-time)

    Cloud mode supports two sub-modes:
    - Polling mode (default): Updates every 60 seconds via HTTP API
    - MQTT mode (optional): Real-time updates via AWS IoT + backup polling every 5 min
    """

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the coordinator."""
        self.entry = entry
        self.api: EnphaseBatteryAPI | None = None
        self.local_api: EnphaseEnvoyLocalAPI | None = None
        self.mqtt_client: EnphaseMQTTClient | None = None

        # Determine connection mode (default to cloud for backward compatibility)
        self._connection_mode = entry.data.get(CONF_CONNECTION_MODE, CONNECTION_MODE_CLOUD)
        self._use_mqtt = entry.options.get(CONF_USE_MQTT, False) and self._connection_mode == CONNECTION_MODE_CLOUD

        # Determine update interval based on connection mode and MQTT
        if self._connection_mode == CONNECTION_MODE_LOCAL:
            # Local mode: Fast polling (10s)
            update_interval = timedelta(seconds=LOCAL_SCAN_INTERVAL)
            mode_description = "Local (Envoy direct)"
        elif self._use_mqtt:
            # Cloud mode with MQTT: Slow backup polling (5min)
            update_interval = timedelta(seconds=MQTT_SCAN_INTERVAL)
            mode_description = "Cloud (MQTT + backup polling)"
        else:
            # Cloud mode standard polling (60s)
            update_interval = timedelta(seconds=DEFAULT_SCAN_INTERVAL)
            mode_description = "Cloud (polling)"

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=update_interval,
        )

        _LOGGER.info(
            "Coordinator initialized in %s mode (interval: %ss)",
            mode_description,
            update_interval.total_seconds(),
        )

    async def _async_setup(self) -> None:
        """Set up the coordinator based on connection mode."""
        session = async_get_clientsession(self.hass)

        if self._connection_mode == CONNECTION_MODE_LOCAL:
            # Local mode: Initialize Envoy local API
            await self._setup_local_api(session)
        else:
            # Cloud mode: Initialize cloud API
            await self._setup_cloud_api(session)

            # Initialize MQTT if enabled (cloud mode only)
            if self._use_mqtt and MQTT_AVAILABLE:
                await self._setup_mqtt()

    async def _setup_local_api(self, session) -> None:
        """Set up local Envoy API client."""
        host = self.entry.data.get(CONF_ENVOY_HOST, "envoy.local")
        username = self.entry.data.get(CONF_USERNAME, "installer")
        password = self.entry.data.get(CONF_PASSWORD)

        _LOGGER.info("Setting up local Envoy API connection to %s", host)

        self.local_api = EnphaseEnvoyLocalAPI(
            session=session,
            host=host,
            username=username,
            password=password,
        )

        # Authenticate
        try:
            await self.local_api.authenticate()
            _LOGGER.info("✅ Successfully authenticated with local Envoy at %s", host)
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

        _LOGGER.info("Setting up cloud API connection to Enphase Enlighten")

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
            _LOGGER.info("✅ Successfully authenticated with Enphase cloud")
        except EnphaseBatteryApiError as err:
            _LOGGER.error("Failed to authenticate with cloud: %s", err)
            raise

    async def _setup_mqtt(self) -> None:
        """Set up MQTT connection for real-time updates."""
        try:
            _LOGGER.info("Setting up MQTT connection...")

            # Get MQTT credentials from API
            mqtt_data = await self.api.get_mqtt_credentials()

            if not mqtt_data:
                _LOGGER.warning("Failed to get MQTT credentials, falling back to polling")
                self._use_mqtt = False
                return

            # Create MQTT client
            self.mqtt_client = EnphaseMQTTClient(
                endpoint=mqtt_data["aws_iot_endpoint"],
                topic=mqtt_data["topic"],
                token_key=mqtt_data["aws_token_key"],
                token_value=mqtt_data["aws_token_value"],
                on_message_callback=self._handle_mqtt_message,
            )

            # Connect
            connected = await self.mqtt_client.connect()
            if connected:
                _LOGGER.info("MQTT connected successfully")
            else:
                _LOGGER.warning("MQTT connection failed, using polling only")
                self._use_mqtt = False

        except Exception as err:
            _LOGGER.error("Error setting up MQTT: %s", err)
            self._use_mqtt = False

    def _handle_mqtt_message(self, message: dict[str, Any]) -> None:
        """Handle incoming MQTT message with battery updates."""
        _LOGGER.debug("Received MQTT update: %s", message)

        # Update coordinator data immediately
        self.async_set_updated_data(message)

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from API.

        Mode behavior:
        - Local mode: Primary data source (every 10s)
        - Cloud polling mode: Primary data source (every 60s)
        - Cloud MQTT mode: Backup data source (every 5 minutes)
        """
        try:
            # Ensure API is initialized
            if self._connection_mode == CONNECTION_MODE_LOCAL:
                if not self.local_api:
                    await self._async_setup()
            else:
                if not self.api:
                    await self._async_setup()

            _LOGGER.debug(
                "Fetching battery data from %s API",
                "local" if self._connection_mode == CONNECTION_MODE_LOCAL else "cloud"
            )

            # Get battery data from appropriate source
            if self._connection_mode == CONNECTION_MODE_LOCAL:
                # Local mode: Get data from Envoy
                try:
                    data = await self.local_api.get_battery_data()
                except EnvoyLocalApiError as err:
                    raise UpdateFailed(f"Error fetching local data: {err}") from err
            else:
                # Cloud mode: Get data from Enlighten API
                try:
                    data = await self.api.get_battery_data()
                except EnphaseBatteryApiError as err:
                    raise UpdateFailed(f"Error fetching cloud data: {err}") from err

                # If MQTT is enabled but stale, reconnect
                if self._use_mqtt and self.mqtt_client:
                    if self.mqtt_client.is_stale():
                        _LOGGER.warning("MQTT data is stale, reconnecting...")
                        await self._setup_mqtt()

            return data

        except UpdateFailed:
            raise
        except Exception as err:
            raise UpdateFailed(f"Unexpected error fetching data: {err}") from err

    async def async_shutdown(self) -> None:
        """Shutdown coordinator and cleanup resources."""
        if self.mqtt_client:
            await self.mqtt_client.disconnect()
            _LOGGER.info("MQTT client disconnected")

        if self.local_api:
            await self.local_api.close()
            _LOGGER.info("Local Envoy API client closed")

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

    @property
    def is_mqtt_active(self) -> bool:
        """Return True if MQTT is active and connected."""
        return (
            self._use_mqtt
            and self.mqtt_client is not None
            and self.mqtt_client.is_connected
        )
