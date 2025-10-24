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
from .const import (
    CONF_SITE_ID,
    CONF_USER_ID,
    CONF_USE_MQTT,
    DEFAULT_SCAN_INTERVAL,
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

    Supports two modes:
    - Polling mode (default): Updates every 60 seconds via HTTP API
    - MQTT mode (optional): Real-time updates via AWS IoT + backup polling every 5 min
    """

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the coordinator."""
        self.entry = entry
        self.api: EnphaseBatteryAPI | None = None
        self.mqtt_client: EnphaseMQTTClient | None = None
        self._use_mqtt = entry.options.get(CONF_USE_MQTT, False)

        # Determine update interval based on mode
        update_interval = (
            timedelta(seconds=MQTT_SCAN_INTERVAL)
            if self._use_mqtt
            else timedelta(seconds=DEFAULT_SCAN_INTERVAL)
        )

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=update_interval,
        )

        _LOGGER.info(
            "Coordinator initialized in %s mode (interval: %ss)",
            "MQTT" if self._use_mqtt else "Polling",
            update_interval.total_seconds(),
        )

    async def _async_setup(self) -> None:
        """Set up the coordinator."""
        session = async_get_clientsession(self.hass)

        # Get optional site_id and user_id from config
        site_id_str = self.entry.data.get(CONF_SITE_ID)
        site_id = int(site_id_str) if site_id_str else None

        user_id_str = self.entry.data.get(CONF_USER_ID)
        user_id = int(user_id_str) if user_id_str else None

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
            _LOGGER.info("Successfully authenticated with Enphase")
        except EnphaseBatteryApiError as err:
            _LOGGER.error("Failed to authenticate: %s", err)
            raise

        # Initialize MQTT if enabled
        if self._use_mqtt and MQTT_AVAILABLE:
            await self._setup_mqtt()

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

        In MQTT mode: This is a backup that runs every 5 minutes
        In Polling mode: This is the primary data source (every 60s)
        """
        try:
            if not self.api:
                await self._async_setup()

            _LOGGER.debug("Fetching battery data from API")

            # Get battery data
            data = await self.api.get_battery_data()

            # If MQTT is enabled but stale, reconnect
            if self._use_mqtt and self.mqtt_client:
                if self.mqtt_client.is_stale():
                    _LOGGER.warning("MQTT data is stale, reconnecting...")
                    await self._setup_mqtt()

            return data

        except EnphaseBatteryApiError as err:
            raise UpdateFailed(f"Error fetching data: {err}") from err

    async def async_shutdown(self) -> None:
        """Shutdown coordinator and cleanup resources."""
        if self.mqtt_client:
            await self.mqtt_client.disconnect()
            _LOGGER.info("MQTT client disconnected")

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
