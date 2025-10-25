"""Local Envoy API Client for Enphase IQ Gateway."""
from __future__ import annotations

import logging
from typing import Any
from datetime import datetime
import hashlib

import aiohttp
from aiohttp import ClientSession, ClientTimeout

_LOGGER = logging.getLogger(__name__)

# Local API defaults
DEFAULT_ENVOY_HOST = "envoy.local"
DEFAULT_TIMEOUT = 10  # Local network - faster timeout


class EnvoyLocalApiError(Exception):
    """Base exception for Envoy Local API errors."""


class EnvoyAuthError(EnvoyLocalApiError):
    """Authentication error."""


class EnvoyConnectionError(EnvoyLocalApiError):
    """Connection error."""


class EnphaseEnvoyLocalAPI:
    """Local API client for Enphase IQ Gateway (Envoy)."""

    def __init__(
        self,
        session: ClientSession,
        host: str = DEFAULT_ENVOY_HOST,
        username: str = "installer",
        password: str | None = None,
    ) -> None:
        """Initialize the local Envoy API client.

        Args:
            session: aiohttp ClientSession
            host: Envoy hostname or IP (default: envoy.local)
            username: Username for local auth (default: installer)
            password: Password for local auth (optional, can be derived from serial)
        """
        self._session = session
        self._host = host
        self._username = username
        self._password = password
        self._base_url = f"https://{host}"
        self._jwt_token: str | None = None
        self._serial_number: str | None = None

    async def _make_request(
        self,
        method: str,
        endpoint: str,
        auth_required: bool = True,
        **kwargs,
    ) -> dict[str, Any] | list[Any] | None:
        """Make HTTP request to local Envoy.

        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint
            auth_required: Whether authentication is required
            **kwargs: Additional arguments for aiohttp request

        Returns:
            JSON response data

        Raises:
            EnvoyConnectionError: Connection failed
            EnvoyAuthError: Authentication failed
        """
        url = f"{self._base_url}/{endpoint.lstrip('/')}"

        headers = kwargs.pop("headers", {})
        if auth_required and self._jwt_token:
            headers["Authorization"] = f"Bearer {self._jwt_token}"

        # Local Envoy uses self-signed certificate
        ssl = kwargs.pop("ssl", False)
        timeout = ClientTimeout(total=kwargs.pop("timeout", DEFAULT_TIMEOUT))

        try:
            async with self._session.request(
                method,
                url,
                headers=headers,
                ssl=ssl,
                timeout=timeout,
                **kwargs,
            ) as response:
                if response.status == 401:
                    raise EnvoyAuthError("Authentication required or token expired")

                response.raise_for_status()

                # Some endpoints return text/html or empty responses
                content_type = response.headers.get("Content-Type", "")
                if "application/json" in content_type:
                    return await response.json()
                else:
                    text = await response.text()
                    _LOGGER.debug(f"Non-JSON response from {endpoint}: {text[:200]}")
                    return {"raw": text}

        except aiohttp.ClientError as err:
            _LOGGER.error(f"Connection error to Envoy at {url}: {err}")
            raise EnvoyConnectionError(f"Failed to connect to Envoy: {err}") from err

    async def authenticate(self) -> bool:
        """Authenticate with local Envoy gateway.

        Returns:
            True if authentication successful

        Raises:
            EnvoyAuthError: Authentication failed
        """
        try:
            # Step 1: Get info (no auth required) to retrieve serial number
            info = await self._get_info()
            self._serial_number = info.get("device", {}).get("sn")

            if not self._serial_number:
                raise EnvoyAuthError("Could not retrieve Envoy serial number")

            _LOGGER.info(f"Envoy serial number: {self._serial_number}")

            # Step 2: Generate password from serial if not provided
            if not self._password:
                self._password = self._generate_installer_password(self._serial_number)
                _LOGGER.debug("Generated installer password from serial")

            # Step 3: Authenticate to get JWT token
            auth_data = {
                "username": self._username,
                "password": self._password,
            }

            response = await self._make_request(
                "POST",
                "/auth/check_jwt",
                auth_required=False,
                json=auth_data,
            )

            if response and "token" in response:
                self._jwt_token = response["token"]
                _LOGGER.info("✅ Successfully authenticated with local Envoy")
                return True

            raise EnvoyAuthError("No JWT token received from Envoy")

        except Exception as err:
            _LOGGER.error(f"Authentication failed: {err}")
            raise EnvoyAuthError(f"Failed to authenticate with Envoy: {err}") from err

    def _generate_installer_password(self, serial_number: str) -> str:
        """Generate installer password from Envoy serial number.

        The installer password is derived from the last 6 digits of the serial.

        Args:
            serial_number: Envoy serial number

        Returns:
            Generated password
        """
        # Standard Enphase installer password algorithm
        # Password is typically last 6 digits of serial number
        return serial_number[-6:]

    async def _get_info(self) -> dict[str, Any]:
        """Get Envoy info (no authentication required).

        Returns:
            Device information including serial, model, firmware
        """
        response = await self._make_request("GET", "/info", auth_required=False)
        return response or {}

    async def get_production_data(self) -> dict[str, Any]:
        """Get production data from Envoy.

        Note: /production.json is deprecated. Use get_meters_readings() instead.

        Returns:
            Production data
        """
        return await self._make_request("GET", "/production.json")

    async def get_meters_readings(self) -> dict[str, Any]:
        """Get real-time meter readings (FAST - ~64ms vs 2500ms).

        This is the recommended endpoint for real-time data.

        Returns:
            Meter readings including battery data
        """
        return await self._make_request("GET", "/ivp/meters/readings")

    async def get_ensemble_inventory(self) -> dict[str, Any]:
        """Get ensemble (battery system) inventory.

        Returns:
            Battery devices and status
        """
        return await self._make_request("GET", "/ivp/ensemble/inventory")

    async def get_ensemble_status(self) -> dict[str, Any]:
        """Get ensemble (battery system) status.

        Returns:
            Battery status including SOC, power, etc.
        """
        return await self._make_request("GET", "/ivp/ensemble/status")

    async def get_home_json(self) -> dict[str, Any]:
        """Get gateway summary status.

        Returns:
            Summary of gateway status
        """
        return await self._make_request("GET", "/home.json")

    async def get_battery_data(self) -> dict[str, Any]:
        """Get comprehensive battery data from local Envoy.

        Combines data from multiple endpoints for complete battery status.

        Returns:
            Dictionary containing:
                - soc: State of charge (%)
                - power: Current power (W, negative=charging, positive=discharging)
                - available_energy: Available energy (Wh)
                - max_capacity: Maximum capacity (Wh)
                - status: Battery status
                - devices: Individual battery devices info
        """
        try:
            # Get data from multiple endpoints in parallel
            import asyncio

            results = await asyncio.gather(
                self.get_ensemble_status(),
                self.get_meters_readings(),
                self.get_ensemble_inventory(),
                return_exceptions=True,
            )

            ensemble_status = results[0] if not isinstance(results[0], Exception) else {}
            meters = results[1] if not isinstance(results[1], Exception) else {}
            inventory = results[2] if not isinstance(results[2], Exception) else {}

            # Parse battery data from responses
            battery_data = {
                "timestamp": datetime.now().isoformat(),
                "source": "local_envoy",
            }

            # SOC from ensemble status
            if ensemble_status:
                battery_data["soc"] = ensemble_status.get("percentage", 0)
                battery_data["status"] = ensemble_status.get("state", "unknown")
                battery_data["available_energy"] = ensemble_status.get("available_energy", 0)
                battery_data["max_capacity"] = ensemble_status.get("max_available_capacity", 0)

            # Power from meters (battery meter)
            if meters and isinstance(meters, list):
                for meter in meters:
                    if meter.get("measurementType") == "storage":
                        battery_data["power"] = meter.get("activePower", 0)
                        battery_data["apparent_power"] = meter.get("apparentPower", 0)
                        battery_data["voltage"] = meter.get("voltage", 0)
                        break

            # Device inventory
            if inventory:
                battery_data["devices"] = inventory.get("devices", [])

            return battery_data

        except Exception as err:
            _LOGGER.error(f"Failed to get battery data: {err}")
            raise EnvoyLocalApiError(f"Failed to retrieve battery data: {err}") from err

    async def set_battery_mode(self, mode: str) -> bool:
        """Set battery operation mode.

        Args:
            mode: Battery mode (self-consumption, backup, etc.)

        Returns:
            True if successful

        Note:
            This endpoint may vary by firmware version.
            Implementation may need adjustment based on actual Envoy responses.
        """
        _LOGGER.warning("set_battery_mode: Local API endpoint not yet fully documented")
        # TODO: Implement once endpoint is confirmed via MITM capture
        return False

    async def set_charge_from_grid(self, enabled: bool) -> bool:
        """Enable/disable charging from grid.

        Args:
            enabled: True to enable charging from grid

        Returns:
            True if successful

        Note:
            This endpoint may vary by firmware version.
            Implementation may need adjustment based on actual Envoy responses.
        """
        _LOGGER.warning("set_charge_from_grid: Local API endpoint not yet fully documented")
        # TODO: Implement once endpoint is confirmed via MITM capture
        return False

    async def get_acb_config(self) -> dict[str, Any]:
        """Get AC Battery (ACB) configuration.

        Returns:
            ACB configuration
        """
        return await self._make_request("GET", "/admin/lib/acb_config.json")

    async def set_acb_sleep_mode(self, sleep: bool) -> bool:
        """Set AC Battery sleep mode.

        Args:
            sleep: True to enable sleep mode

        Returns:
            True if successful
        """
        try:
            endpoint = "/admin/lib/acb_config.json"
            data = {"sleep": sleep}
            await self._make_request("POST", endpoint, json=data)
            return True
        except Exception as err:
            _LOGGER.error(f"Failed to set sleep mode: {err}")
            return False

    async def close(self) -> None:
        """Close the API client (session managed externally)."""
        self._jwt_token = None
        _LOGGER.debug("Local Envoy API client closed")
