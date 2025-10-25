"""Local Envoy API Client for Enphase IQ Gateway."""
from __future__ import annotations

import logging
from typing import Any
from datetime import datetime
import hashlib
import jwt

import aiohttp
from aiohttp import ClientSession, ClientTimeout

_LOGGER = logging.getLogger(__name__)

# Local API defaults
DEFAULT_ENVOY_HOST = "envoy.local"
DEFAULT_TIMEOUT = 10  # Local network - faster timeout

# Enphase Cloud endpoints for token retrieval (firmware 7.x+)
ENLIGHTEN_LOGIN_URL = "https://enlighten.enphaseenergy.com/login/login.json"
ENTREZ_TOKEN_URL = "https://entrez.enphaseenergy.com/tokens"


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
        cloud_username: str | None = None,
        cloud_password: str | None = None,
        token: str | None = None,
    ) -> None:
        """Initialize the local Envoy API client.

        Args:
            session: aiohttp ClientSession
            host: Envoy hostname or IP (default: envoy.local)
            username: Local username (default: installer, for firmware < 7.0)
            password: Local password (optional, derived from serial for < 7.0)
            cloud_username: Enlighten cloud email (for firmware >= 7.0 token)
            cloud_password: Enlighten cloud password (for firmware >= 7.0 token)
            token: Pre-existing JWT token (optional, will fetch if not provided)
        """
        self._session = session
        self._host = host
        self._username = username
        self._password = password
        self._cloud_username = cloud_username
        self._cloud_password = cloud_password
        self._base_url = f"https://{host}"
        self._jwt_token: str | None = token
        self._serial_number: str | None = None
        self._firmware_version: str | None = None

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
                    _LOGGER.debug(f"Non-JSON response from {endpoint} (length={len(text)}): {text[:200]}")
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

            # Try multiple ways to extract serial
            self._serial_number = (
                info.get("device", {}).get("sn") or
                info.get("device", {}).get("serial_num") or
                info.get("sn") or
                info.get("serial_num") or
                info.get("serialNumber")
            )

            if not self._serial_number:
                _LOGGER.error(f"Cannot find serial in /info response. Keys found: {list(info.keys())}")
                _LOGGER.error(f"Full response: {info}")
                raise EnvoyAuthError(
                    f"Could not retrieve Envoy serial number from /info endpoint. "
                    f"Response keys: {list(info.keys())}"
                )

            _LOGGER.info(f"✅ Envoy serial number: {self._serial_number}")

            # Step 2: Extract firmware version from info
            self._firmware_version = (
                info.get("device", {}).get("software") or
                info.get("software") or
                info.get("fw_version") or
                info.get("version")
            )

            if self._firmware_version:
                _LOGGER.info(f"Envoy firmware version: {self._firmware_version}")

            # Step 3: Determine authentication method based on firmware
            if self._is_firmware_7_or_higher():
                _LOGGER.info("Firmware 7.x+ detected, using cloud token authentication")

                # Try to use existing token or obtain new one
                if not self._jwt_token:
                    if self._cloud_username and self._cloud_password:
                        self._jwt_token = await self._obtain_cloud_token()
                    else:
                        raise EnvoyAuthError(
                            "Firmware 7.x+ requires cloud credentials (Enlighten email/password) "
                            "to obtain authentication token. Please reconfigure with cloud credentials."
                        )

                # Validate token with local Envoy
                try:
                    test_response = await self._make_request(
                        "GET",
                        "/auth/check_jwt",
                        auth_required=True,
                    )
                    _LOGGER.info("✅ Token validated with local Envoy")
                    return True
                except Exception as err:
                    raise EnvoyAuthError(f"Token validation failed: {err}") from err

            else:
                # Firmware < 7.0: Use installer username/password
                _LOGGER.info("Firmware < 7.0 detected, using installer password authentication")

                if not self._password:
                    self._password = self._generate_installer_password(self._serial_number)
                    _LOGGER.debug("Generated installer password from serial")

                # Authenticate to get JWT token
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

    def _is_firmware_7_or_higher(self) -> bool:
        """Check if firmware version is 7.0 or higher.

        Returns:
            True if firmware >= 7.0, False otherwise or if unknown
        """
        if not self._firmware_version:
            return False

        try:
            # Extract version number (e.g., "D7.3.466" -> "7.3")
            import re
            match = re.search(r'[dD]?(\d+)\.(\d+)', self._firmware_version)
            if match:
                major = int(match.group(1))
                return major >= 7
        except Exception:
            pass

        return False

    async def _obtain_cloud_token(self) -> str:
        """Obtain JWT token from Enphase cloud for firmware 7.x+ authentication.

        Returns:
            JWT token string

        Raises:
            EnvoyAuthError: Failed to obtain token
        """
        if not self._cloud_username or not self._cloud_password:
            raise EnvoyAuthError(
                "Cloud credentials required for firmware 7.x+ authentication. "
                "Please provide cloud_username and cloud_password."
            )

        if not self._serial_number:
            raise EnvoyAuthError("Serial number must be retrieved before obtaining token")

        _LOGGER.info("Obtaining cloud token for firmware 7.x+ authentication...")

        try:
            # Step 1: Login to Enlighten to get session ID
            login_data = {
                "user[email]": self._cloud_username,
                "user[password]": self._cloud_password,
            }

            async with self._session.post(
                ENLIGHTEN_LOGIN_URL,
                data=login_data,
                timeout=ClientTimeout(total=10),
            ) as response:
                response.raise_for_status()
                login_response = await response.json()

                session_id = login_response.get("session_id")
                if not session_id:
                    raise EnvoyAuthError(
                        f"No session_id in login response. Keys: {list(login_response.keys())}"
                    )

                _LOGGER.debug(f"✅ Enlighten login successful, session_id obtained")

            # Step 2: Request token from Entrez using session ID
            token_data = {
                "session_id": session_id,
                "serial_num": self._serial_number,
                "username": self._cloud_username,
            }

            async with self._session.post(
                ENTREZ_TOKEN_URL,
                json=token_data,
                timeout=ClientTimeout(total=10),
            ) as response:
                response.raise_for_status()
                token = await response.text()

                # Response is plain text JWT token
                if not token or len(token) < 50:
                    raise EnvoyAuthError(f"Invalid token received: {token[:50]}")

                _LOGGER.info("✅ Cloud token obtained successfully")

                # Decode token to check expiration (without verification)
                try:
                    decoded = jwt.decode(token, options={"verify_signature": False})
                    exp = decoded.get("exp")
                    if exp:
                        exp_date = datetime.fromtimestamp(exp)
                        _LOGGER.info(f"Token expires: {exp_date}")
                except Exception as err:
                    _LOGGER.warning(f"Could not decode token expiration: {err}")

                return token

        except aiohttp.ClientError as err:
            _LOGGER.error(f"Cloud token request failed: {err}")
            raise EnvoyAuthError(f"Failed to obtain cloud token: {err}") from err
        except Exception as err:
            _LOGGER.error(f"Unexpected error obtaining token: {err}")
            raise EnvoyAuthError(f"Token retrieval error: {err}") from err

    async def _get_info(self) -> dict[str, Any]:
        """Get Envoy info (no authentication required).

        Returns:
            Device information including serial, model, firmware
        """
        try:
            response = await self._make_request("GET", "/info", auth_required=False)
            _LOGGER.debug(f"Envoy /info response type: {type(response)}")

            # Handle different response formats
            xml_content = None

            if isinstance(response, dict):
                # Check if response contains XML in 'raw' key (common in newer firmware)
                if "raw" in response and isinstance(response["raw"], str):
                    xml_content = response["raw"]
                    _LOGGER.debug("Found XML content in 'raw' key")
                # Try different possible locations for device info
                elif "device" in response:
                    return response
                elif "serial_num" in response or "sn" in response:
                    # Wrap in expected format
                    return {"device": response}
                else:
                    # Log full response to debug
                    _LOGGER.warning(f"Unexpected /info structure: {list(response.keys())}")
                    return response
            elif isinstance(response, str):
                xml_content = response
                _LOGGER.debug("Response is string, treating as XML")

            # Parse XML if we have it
            if xml_content:
                _LOGGER.info(f"Full response: {response}")
                import re

                # Extract serial number
                serial_match = re.search(r'<sn>(\d+)</sn>', xml_content)
                serial = serial_match.group(1) if serial_match else None

                # Extract firmware version
                software_match = re.search(r'<software>([\w.]+)</software>', xml_content)
                software = software_match.group(1) if software_match else None

                # Extract part number
                pn_match = re.search(r'<device>.*?<pn>([\w-]+)</pn>', xml_content, re.DOTALL)
                part_num = pn_match.group(1) if pn_match else None

                if serial:
                    _LOGGER.debug(f"Extracted from XML - Serial: {serial}, Software: {software}, PN: {part_num}")
                    return {
                        "device": {
                            "sn": serial,
                            "software": software,
                            "pn": part_num,
                        }
                    }
                else:
                    _LOGGER.error(f"Cannot find serial in /info response. Keys found: {list(response.keys()) if isinstance(response, dict) else 'string'}")

            return response or {}
        except Exception as err:
            _LOGGER.error(f"Failed to get /info: {err}")
            raise

    async def get_production_data(self) -> dict[str, Any]:
        """Get production data from Envoy.

        Note: /production.json is deprecated. Use get_meters_readings() instead.

        Returns:
            Production data
        """
        return await self._make_request("GET", "/production.json")

    async def get_production_v1(self) -> dict[str, Any]:
        """Get production data from /api/v1/production.json or /production.json.

        This endpoint includes ACB battery power via storage.wNow field.
        Firmware 7.x uses /api/v1/production.json
        Firmware 8.x uses /production.json

        Returns:
            Production data including battery power (wNow)
        """
        # Try /api/v1/production.json first (firmware 7.x)
        try:
            return await self._make_request("GET", "/api/v1/production.json")
        except EnvoyConnectionError as err:
            # If 404, try /production.json (firmware 8.x)
            if "404" in str(err):
                _LOGGER.debug("/api/v1/production.json not found (404), trying /production.json")
                return await self._make_request("GET", "/production.json")
            raise

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

    async def get_ensemble_power(self) -> dict[str, Any]:
        """Get ensemble (battery) real-time power data.

        Returns real_power_mw and apparent_power_mva for each battery device.
        This is the accurate power reading used by the official Enphase integration.

        Returns:
            Battery power data (real_power_mw in milliwatts, apparent_power_mva, soc)
        """
        return await self._make_request("GET", "/ivp/ensemble/power")

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
                self.get_ensemble_power(),
                return_exceptions=True,
            )

            ensemble_status = results[0] if not isinstance(results[0], Exception) else {}
            meters = results[1] if not isinstance(results[1], Exception) else {}
            inventory = results[2] if not isinstance(results[2], Exception) else {}
            ensemble_power = results[3] if not isinstance(results[3], Exception) else {}

            # Debug: Log raw responses
            _LOGGER.debug(f"Ensemble status response: {ensemble_status}")
            _LOGGER.debug(f"Meters response: {meters}")
            _LOGGER.debug(f"Inventory response: {inventory}")
            _LOGGER.debug(f"Ensemble power response: {ensemble_power}")

            # Parse JSON from 'raw' key if present (firmware 8.x format)
            import json

            if isinstance(ensemble_status, dict) and "raw" in ensemble_status:
                ensemble_status = json.loads(ensemble_status["raw"])
                _LOGGER.debug("Parsed ensemble_status from 'raw' key")

            if isinstance(meters, dict) and "raw" in meters:
                meters = json.loads(meters["raw"])
                _LOGGER.debug("Parsed meters from 'raw' key")

            if isinstance(inventory, dict) and "raw" in inventory:
                inventory = json.loads(inventory["raw"])
                _LOGGER.debug("Parsed inventory from 'raw' key")

            if isinstance(ensemble_power, dict) and "raw" in ensemble_power:
                ensemble_power = json.loads(ensemble_power["raw"])
                _LOGGER.debug("Parsed ensemble_power from 'raw' key")

            # Parse battery data from responses
            battery_data = {
                "timestamp": datetime.now().isoformat(),
                "source": "local_envoy",
            }

            # SOC from ensemble status (firmware 8.x structure)
            if ensemble_status:
                # Try secctrl path first (firmware 8.x)
                secctrl = ensemble_status.get("secctrl", {})
                if secctrl:
                    battery_data["soc"] = secctrl.get("agg_soc", secctrl.get("ENC_agg_soc", 0))
                    battery_data["soh"] = secctrl.get("ENC_agg_soh", 100)
                    battery_data["available_energy"] = secctrl.get("ENC_agg_avail_energy", 0)
                    battery_data["max_capacity"] = secctrl.get("Enc_max_available_capacity", 0)
                    battery_data["status"] = "grid-tied" if ensemble_status.get("relay", {}).get("Enchg_grid_mode") == "grid-tied" else "unknown"

                    # DEBUG: Log all secctrl fields to find power field
                    _LOGGER.debug(f"secctrl keys available: {list(secctrl.keys())}")
                else:
                    # Fallback to direct fields (older firmware)
                    battery_data["soc"] = ensemble_status.get("percentage", 0)
                    battery_data["status"] = ensemble_status.get("state", "unknown")
                    battery_data["available_energy"] = ensemble_status.get("available_energy", 0)
                    battery_data["max_capacity"] = ensemble_status.get("max_available_capacity", 0)

                _LOGGER.debug(f"Parsed SOC: {battery_data.get('soc')}%, Status: {battery_data.get('status')}, Available: {battery_data.get('available_energy')}Wh")

            # Power and energy from meters (battery meter)
            # In firmware 8.x, meters is a list with multiple EIDs:
            # - 704643328 (0x2A00FE00): Net consumption meter
            # - 704643584 (0x2A010000): Production meter
            # - 1023410688 (0x3D00FE00): Storage/Battery meter (but often returns 0 for energy)
            if meters and isinstance(meters, list):
                battery_power = 0
                production_power = 0
                consumption_power = 0
                battery_energy_discharged = 0  # actEnergyDlvd
                battery_energy_charged = 0  # actEnergyRcvd
                consumption_energy = 0
                production_energy = 0

                for meter in meters:
                    eid = meter.get("eid")
                    active_power = meter.get("activePower", 0)

                    # Storage meter (EID starts with 0x3D)
                    if eid and (eid & 0xFF000000) == 0x3D000000:
                        battery_power = active_power
                        battery_energy_discharged = meter.get("actEnergyDlvd", 0) / 1000  # Convert Wh to kWh
                        battery_energy_charged = meter.get("actEnergyRcvd", 0) / 1000
                        _LOGGER.debug(f"Battery meter (EID {eid}): {active_power}W, Discharged: {battery_energy_discharged:.2f}kWh, Charged: {battery_energy_charged:.2f}kWh")
                    # Production meter (EID 0x2A010000 range)
                    elif eid == 704643584:
                        production_power = active_power
                        production_energy = meter.get("actEnergyDlvd", 0) / 1000  # kWh
                        _LOGGER.debug(f"Production meter: {active_power}W, Energy: {production_energy:.2f}kWh")
                    # Consumption meter (EID 0x2A00FE00 range)
                    elif eid == 704643328:
                        consumption_power = active_power
                        consumption_energy = meter.get("actEnergyDlvd", 0) / 1000  # kWh
                        _LOGGER.debug(f"Consumption meter: {active_power}W, Energy: {consumption_energy:.2f}kWh")

                # If battery meter doesn't report power (value = 0), use /ivp/ensemble/power
                # This endpoint has the accurate real_power_mw field (same as official Enphase addon)
                if battery_power == 0 and ensemble_power and isinstance(ensemble_power, dict):
                    devices = ensemble_power.get("devices:", [])
                    if devices and len(devices) > 0:
                        # real_power_mw is in milliwatts, convert to watts
                        real_power_mw = devices[0].get("real_power_mw", 0)
                        battery_power = real_power_mw / 1000  # Convert mW to W
                        _LOGGER.debug(f"Battery power from /ivp/ensemble/power: {battery_power}W (real_power_mw: {real_power_mw}mW)")

                # Final fallback: calculate from production - consumption (least accurate)
                if battery_power == 0 and (production_power != 0 or consumption_power != 0):
                    battery_power = production_power - consumption_power
                    _LOGGER.debug(f"Battery power calculated from meters (fallback): {production_power}W (production) - {consumption_power}W (consumption) = {battery_power}W")

                # Power convention: negative = charging, positive = discharging
                battery_data["power"] = int(battery_power)
                battery_data["charge_power"] = int(abs(battery_power)) if battery_power < 0 else 0
                battery_data["discharge_power"] = int(battery_power) if battery_power > 0 else 0

                # Store cumulative energy values (will be used by coordinator for daily calc)
                # If battery meter doesn't track energy, use production/consumption energies as proxy
                battery_data["total_energy_discharged"] = battery_energy_discharged if battery_energy_discharged > 0 else 0
                battery_data["total_energy_charged"] = battery_energy_charged if battery_energy_charged > 0 else 0
                battery_data["total_consumption"] = consumption_energy
                battery_data["total_production"] = production_energy

                _LOGGER.debug(f"Battery power: {battery_power}W (charge: {battery_data['charge_power']}W, discharge: {battery_data['discharge_power']}W)")

            # Device inventory
            if inventory and isinstance(inventory, list):
                for inv_type in inventory:
                    if inv_type.get("type") == "ENCHARGE":
                        devices = inv_type.get("devices", [])
                        battery_data["devices"] = devices

                        # Get power and SOC from first device if available
                        if devices:
                            device = devices[0]
                            # Override SOC if device has more accurate value
                            if "percentFull" in device:
                                battery_data["soc"] = device.get("percentFull", battery_data.get("soc", 0))
                            battery_data["temperature"] = device.get("temperature")
                            battery_data["max_cell_temp"] = device.get("maxCellTemp")
                            _LOGGER.debug(f"Device SOC: {device.get('percentFull')}%, Temp: {device.get('temperature')}°C")
                        break
            elif inventory:
                # Fallback for older format
                battery_data["devices"] = inventory.get("devices", [])

            # Get charge_from_grid setting from tariff configuration
            try:
                tariff_data = await self._make_request("GET", "/admin/lib/tariff", auth_required=True)

                # Parse JSON from 'raw' key if present (firmware 8.x format)
                if isinstance(tariff_data, dict) and "raw" in tariff_data:
                    tariff_data = json.loads(tariff_data["raw"])
                    _LOGGER.debug(f"Parsed tariff_data from 'raw' key. Keys: {list(tariff_data.keys())}")

                # Check if tariff has storage_settings (it should be in tariff_data["tariff"]["storage_settings"])
                if tariff_data and "tariff" in tariff_data and "storage_settings" in tariff_data["tariff"]:
                    battery_data["charge_from_grid"] = tariff_data["tariff"]["storage_settings"].get("charge_from_grid", False)
                    _LOGGER.debug(f"charge_from_grid: {battery_data.get('charge_from_grid')}")
                elif tariff_data and "storage_settings" in tariff_data:
                    battery_data["charge_from_grid"] = tariff_data["storage_settings"].get("charge_from_grid", False)
                    _LOGGER.debug(f"charge_from_grid: {battery_data.get('charge_from_grid')}")
                else:
                    battery_data["charge_from_grid"] = False
                    _LOGGER.debug("tariff configuration does not contain storage_settings, defaulting charge_from_grid to False")
            except Exception as tariff_err:
                _LOGGER.debug(f"Failed to get tariff data: {tariff_err}")
                battery_data["charge_from_grid"] = False

            _LOGGER.info(f"Final battery data: {battery_data}")

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
            Endpoint: PUT /admin/lib/tariff
            Requires firmware 7.x+ with tariff configuration
            Uses same approach as pyenphase: GET current tariff, modify, PUT back
        """
        try:
            # Step 1: Get current tariff configuration
            tariff_data = await self._make_request(
                "GET",
                "/admin/lib/tariff",
                auth_required=True,
            )

            if not tariff_data:
                _LOGGER.error("Failed to get tariff configuration")
                return False

            # Parse JSON from 'raw' key if present (firmware 8.x format)
            import json
            if isinstance(tariff_data, dict) and "raw" in tariff_data:
                tariff_data = json.loads(tariff_data["raw"])
                _LOGGER.debug(f"Parsed tariff_data from 'raw' key for set operation. Keys: {list(tariff_data.keys())}")

            # Step 2: Verify storage_settings exists
            # The structure is {"tariff": {"storage_settings": {...}}}
            if "tariff" not in tariff_data or "storage_settings" not in tariff_data["tariff"]:
                _LOGGER.error(f"Tariff configuration does not contain storage_settings. Keys: {list(tariff_data.keys())}")
                return False

            # Step 3: Modify charge_from_grid setting
            tariff_data["tariff"]["storage_settings"]["charge_from_grid"] = enabled

            # Step 4: Send updated configuration back (send the whole structure)
            response = await self._make_request(
                "PUT",
                "/admin/lib/tariff",
                json=tariff_data,  # Send complete structure, not wrapped again
                auth_required=True,
            )

            _LOGGER.info(f"Set charge_from_grid to {enabled}: {response}")
            return True

        except Exception as err:
            _LOGGER.error(f"Failed to set charge_from_grid: {err}")
            # Don't raise - return False to indicate failure
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
