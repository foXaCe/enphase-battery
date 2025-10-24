"""MQTT Client for real-time Enphase Battery updates."""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable
from datetime import datetime, timedelta

try:
    from awscrt import mqtt
    from awsiot import mqtt_connection_builder
    MQTT_AVAILABLE = True
except ImportError:
    MQTT_AVAILABLE = False
    _LOGGER = logging.getLogger(__name__)
    _LOGGER.warning("AWS IoT SDK not available. Install with: pip install awsiotsdk")

_LOGGER = logging.getLogger(__name__)


class EnphaseMQTTClient:
    """MQTT client for real-time battery updates via AWS IoT."""

    def __init__(
        self,
        endpoint: str,
        topic: str,
        token_key: str,
        token_value: str,
        on_message_callback: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        """Initialize MQTT client.

        Args:
            endpoint: AWS IoT endpoint
            topic: MQTT topic to subscribe
            token_key: Token key for authentication
            token_value: Token value for authentication
            on_message_callback: Callback function for received messages
        """
        if not MQTT_AVAILABLE:
            raise ImportError("AWS IoT SDK not installed. Run: pip install awsiotsdk")

        self._endpoint = endpoint
        self._topic = topic
        self._token_key = token_key
        self._token_value = token_value
        self._on_message_callback = on_message_callback
        self._connection = None
        self._connected = False
        self._last_message: dict[str, Any] | None = None
        self._last_update: datetime | None = None

    async def connect(self) -> bool:
        """Connect to AWS IoT MQTT broker."""
        try:
            _LOGGER.info(f"Connecting to MQTT endpoint: {self._endpoint}")

            # TODO: Implémenter la connexion AWS IoT avec custom authorizer
            # Note: L'app Enphase utilise aws-lambda-authoriser-prod
            # Nécessite de passer le token via le header MQTT

            # Pour l'instant, retourne False (non implémenté)
            _LOGGER.warning("MQTT connection not yet fully implemented")
            return False

        except Exception as err:
            _LOGGER.error(f"Failed to connect to MQTT: {err}")
            return False

    async def disconnect(self) -> None:
        """Disconnect from MQTT broker."""
        if self._connection and self._connected:
            try:
                _LOGGER.info("Disconnecting from MQTT")
                # await self._connection.disconnect()
                self._connected = False
            except Exception as err:
                _LOGGER.error(f"Error disconnecting MQTT: {err}")

    def _on_message_received(self, topic: str, payload: bytes, **kwargs) -> None:
        """Handle received MQTT message."""
        try:
            import json
            message = json.loads(payload.decode("utf-8"))

            self._last_message = message
            self._last_update = datetime.now()

            _LOGGER.debug(f"Received MQTT message on {topic}: {message}")

            if self._on_message_callback:
                self._on_message_callback(message)

        except Exception as err:
            _LOGGER.error(f"Error processing MQTT message: {err}")

    @property
    def is_connected(self) -> bool:
        """Return True if connected."""
        return self._connected

    @property
    def last_message(self) -> dict[str, Any] | None:
        """Return last received message."""
        return self._last_message

    @property
    def last_update(self) -> datetime | None:
        """Return timestamp of last message."""
        return self._last_update

    def is_stale(self, max_age: timedelta = timedelta(minutes=2)) -> bool:
        """Check if last update is stale."""
        if not self._last_update:
            return True
        return datetime.now() - self._last_update > max_age
