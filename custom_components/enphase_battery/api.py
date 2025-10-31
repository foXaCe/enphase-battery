"""API Client for Enphase Battery IQ 5P."""
from __future__ import annotations

import logging
from typing import Any
from datetime import datetime

import aiohttp
from aiohttp import ClientSession, ClientTimeout

_LOGGER = logging.getLogger(__name__)

API_BASE_URL = "https://enlighten.enphaseenergy.com"
API_TIMEOUT = 15  # Standard API timeout
API_TIMEOUT_DISCOVERY = 5  # Faster timeout for auto-discovery endpoints


class EnphaseBatteryApiError(Exception):
    """Base exception for Enphase Battery API errors."""


class EnphaseBatteryAuthError(EnphaseBatteryApiError):
    """Authentication error."""


class EnphaseBatteryConnectionError(EnphaseBatteryApiError):
    """Connection error."""


class EnphaseBatteryAPI:
    """API client for Enphase Battery system."""

    def __init__(
        self,
        session: ClientSession,
        username: str,
        password: str,
        site_id: int | None = None,
        user_id: int | None = None,
    ) -> None:
        """Initialize the API client."""
        self._session = session
        self._username = username
        self._password = password
        self._site_id: int | None = site_id  # Peut être fourni manuellement
        self._user_id: int | None = user_id  # Peut être fourni manuellement
        self._session_token: str | None = None
        self._envoy_serial: str | None = None

    def _get_headers(self) -> dict[str, str]:
        """Get headers for API requests with token if available.

        Returns:
            Dictionary of headers
        """
        headers = {
            "User-Agent": "Mozilla/5.0 (Linux; Android 14; MI PAD 4) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.6167.164 Safari/537.36",
            "Accept": "application/json",
        }

        # L'API Enphase utilise le header "e-auth-token" avec le cookie de session _enlighten_4_session
        # Et le header X-XSRF-Token pour la protection CSRF
        cookies = self._session.cookie_jar.filter_cookies(API_BASE_URL)
        for cookie in cookies.values():
            if cookie.key == "_enlighten_4_session":
                headers["e-auth-token"] = cookie.value
            # Ajouter le token CSRF pour les requêtes de modification
            if cookie.key == "BP-XSRF-Token":
                headers["X-XSRF-Token"] = cookie.value

        return headers

    async def authenticate(self) -> bool:
        """Authenticate with Enphase Enlighten with automatic token management."""
        try:
            # Étape 1: Login avec username/password pour obtenir session cookies
            login_success = await self._login()
            if not login_success:
                raise EnphaseBatteryAuthError("Login failed")

            # Note: Session token endpoint skipped - cookies are sufficient for auth
            # This saves 1-2 seconds during authentication

            # Étape 2: Récupérer site_id et user_id de l'utilisateur (si pas déjà fourni)
            # Skip auto-detection if both IDs are already provided (saves 5-10 seconds at startup)
            if self._site_id and self._user_id:
                _LOGGER.info("Using provided site_id=%s and user_id=%s", self._site_id, self._user_id)
            elif not self._site_id or not self._user_id:
                _LOGGER.info("Auto-detecting site_id and user_id (this takes 5-7 seconds)...")
                try:
                    detected_site_id, detected_user_id = await self._get_user_sites()

                    if not self._site_id and detected_site_id:
                        self._site_id = detected_site_id
                        _LOGGER.info(f"Auto-detected site_id: {self._site_id}")

                    if not self._user_id and detected_user_id:
                        self._user_id = detected_user_id

                    # Si on a trouvé site_id mais pas user_id, essayer la méthode alternative
                    if self._site_id and not self._user_id:
                        alternative_user_id = await self._get_user_id_from_battery_settings()
                        if alternative_user_id:
                            self._user_id = alternative_user_id
                        else:
                            _LOGGER.warning(
                                "Could not auto-detect user_id. "
                                "You may need to provide user_id manually in configuration."
                            )

                except EnphaseBatteryAuthError as err:
                    _LOGGER.error(f"Auto-detection failed: {err}")

                    # Si on n'a toujours pas les IDs nécessaires
                    if not self._site_id:
                        raise EnphaseBatteryAuthError(
                            "Could not auto-detect site_id. Please add 'site_id: YOUR_SITE_ID' to your configuration. "
                            f"Error details: {err}"
                        )

            # Note: Envoy serial is fetched later on-demand, not during auth
            # This saves 1-2 seconds during authentication

            _LOGGER.info(f"Authenticated successfully - site_id: {self._site_id}")
            return True

        except EnphaseBatteryAuthError:
            raise
        except aiohttp.ClientError as err:
            raise EnphaseBatteryConnectionError(f"Connection error: {err}") from err
        except Exception as err:
            raise EnphaseBatteryApiError(f"Authentication failed: {err}") from err

    async def _login(self) -> bool:
        """Login to Enphase Enlighten to obtain session cookies.

        Returns:
            True if login successful
        """
        url = f"{API_BASE_URL}/login/login.json"

        # Payload basé sur la capture mitmdump
        payload = {
            "user[email]": self._username,
            "user[password]": self._password,
        }

        try:
            async with self._session.post(
                url,
                data=payload,
                timeout=ClientTimeout(total=API_TIMEOUT_DISCOVERY),
            ) as response:
                if response.status == 200:
                    data = await response.json()

                    # Vérifier si le login a réussi
                    # L'API retourne généralement un status ou message
                    if data.get("status") == "success" or data.get("message") == "success":
                        return True

                    # Certaines réponses contiennent directement le site_id
                    if "user" in data and isinstance(data["user"], dict):
                        user_data = data["user"]
                        if "default_system_id" in user_data:
                            return True

                    # Parfois le login réussit avec un 200 même sans message
                    return True

                elif response.status == 401:
                    raise EnphaseBatteryAuthError("Invalid credentials")
                else:
                    _LOGGER.error(f"Login failed with status {response.status}")
                    return False

        except aiohttp.ClientError as err:
            raise EnphaseBatteryConnectionError(f"Login connection error: {err}") from err

    async def _get_session_token(self) -> str | None:
        """Get session token after login.

        Returns:
            Session token string or None if not available
        """
        url = f"{API_BASE_URL}/service/auth_ms_enho/api/v1/session/token"

        try:
            async with self._session.get(
                url,
                timeout=ClientTimeout(total=API_TIMEOUT),
            ) as response:
                if response.status == 200:
                    data = await response.json()

                    # Le token peut être dans différents formats selon l'API
                    if isinstance(data, dict):
                        # Chercher le token dans la réponse
                        token = data.get("token") or data.get("access_token") or data.get("session_token")
                        if token:
                            return token

                    # Parfois la réponse est directement le token
                    if isinstance(data, str):
                        return data

                    return None

        except Exception:
            return None

    async def _get_envoy_serial(self) -> str | None:
        """Get Envoy serial number from devices list.

        Returns:
            Envoy serial number or None
        """
        if not self._site_id:
            return None

        try:
            devices_data = await self.get_devices()

            # Chercher l'envoy dans la liste des devices
            result = devices_data.get("result", [])
            for device_group in result:
                if device_group.get("type") == "envoy":
                    devices = device_group.get("devices", [])
                    if len(devices) > 0:
                        envoy = devices[0]
                        return envoy.get("serial_number")

            return None

        except Exception:
            return None

    async def _get_user_id_from_battery_settings(self) -> int | None:
        """Try to extract user_id by calling batterySettings and parsing response.

        Some Enphase API responses include user_id in their data.

        Returns:
            user_id as int or None if not found
        """
        if not self._site_id:
            return None

        # Try different endpoints that might include user info
        endpoints_to_try = [
            f"{API_BASE_URL}/pv/systems/{self._site_id}/today",
            f"{API_BASE_URL}/app-api/{self._site_id}/data.json?app=1",
        ]

        for url in endpoints_to_try:
            try:
                async with self._session.get(
                    url,
                    headers=self._get_headers(),
                    timeout=ClientTimeout(total=API_TIMEOUT_DISCOVERY),
                ) as response:
                    if response.status == 200:
                        data = await response.json()

                        # Search for user_id in various possible locations
                        def find_user_id(obj, depth=0):
                            if depth > 5:  # Limit recursion
                                return None
                            if isinstance(obj, dict):
                                if "user_id" in obj:
                                    return obj["user_id"]
                                for value in obj.values():
                                    result = find_user_id(value, depth + 1)
                                    if result:
                                        return result
                            elif isinstance(obj, list):
                                for item in obj:
                                    result = find_user_id(item, depth + 1)
                                    if result:
                                        return result
                            return None

                        user_id = find_user_id(data)
                        if user_id:
                            return int(user_id)

            except Exception:
                continue

        return None

    async def _get_user_sites(self) -> tuple[int, int]:
        """Try to get user's site_id and user_id from API using multiple methods.

        Returns:
            Tuple of (site_id, user_id)
        """
        # Variables pour stocker les résultats au fur et à mesure
        extracted_site_id = None
        extracted_user_id = None

        # Méthode 1: Essayer /app-api/search_sites.json
        url = f"{API_BASE_URL}/app-api/search_sites.json"
        params = {"searchText": "", "favourite": "false"}

        try:
            async with self._session.get(
                url,
                params=params,
                headers=self._get_headers(),
                timeout=ClientTimeout(total=API_TIMEOUT_DISCOVERY),
            ) as response:
                if response.status == 200:
                    try:
                        data = await response.json()
                    except Exception as json_err:
                        _LOGGER.error(f"Failed to parse JSON from search_sites: {json_err}")
                        raise

                    # Extraire le premier site
                    if isinstance(data, list):
                        if len(data) > 0:
                            first_site = data[0]
                            site_id = first_site.get("system_id")
                            user_id = first_site.get("user_id")

                            if site_id and user_id:
                                return int(site_id), int(user_id)

                    # Si data est un dict avec "systems"
                    elif isinstance(data, dict):
                        # Essayer plusieurs clés possibles
                        for key in ["systems", "sites", "data", "result", "response"]:
                            if key in data:
                                systems = data[key]

                                if isinstance(systems, list) and len(systems) > 0:
                                    first_site = systems[0]
                                    site_id = first_site.get("system_id") or first_site.get("site_id") or first_site.get("id")
                                    user_id = first_site.get("user_id") or first_site.get("owner_id")

                                    if site_id and user_id:
                                        return int(site_id), int(user_id)

        except Exception:
            pass  # Try next method

        # Méthode 2: Essayer /pv/systems endpoint et extraire site_id de l'URL de redirection
        try:
            url = f"{API_BASE_URL}/pv/systems"
            async with self._session.get(
                url,
                headers=self._get_headers(),
                timeout=ClientTimeout(total=API_TIMEOUT_DISCOVERY),
                allow_redirects=True,
            ) as response:
                # Extraire site_id de l'URL (format: /web/2168380?v=3.4.0)
                import re
                url_str = str(response.url)
                match = re.search(r'/web/(\d+)', url_str)
                if match:
                    extracted_site_id = int(match.group(1))

                    # Maintenant on doit trouver le user_id
                    # Essayer de le récupérer depuis les settings de la batterie
                    try:
                        settings_url = f"{API_BASE_URL}/service/batteryConfig/api/v1/batterySettings/{extracted_site_id}"
                        async with self._session.get(
                            settings_url,
                            headers=self._get_headers(),
                            timeout=ClientTimeout(total=API_TIMEOUT_DISCOVERY),
                        ) as settings_response:
                            if settings_response.status == 200:
                                settings_data = await settings_response.json()

                                # Chercher user_id dans la réponse
                                if isinstance(settings_data, dict):
                                    extracted_user_id = settings_data.get("userId") or settings_data.get("user_id")
                                    if extracted_user_id:
                                        return int(extracted_site_id), int(extracted_user_id)
                    except Exception:
                        pass

                    # Si on a site_id mais pas user_id, essayer l'endpoint system summary
                    try:
                        summary_url = f"{API_BASE_URL}/api/v4/systems/{extracted_site_id}/summary"
                        async with self._session.get(
                            summary_url,
                            headers=self._get_headers(),
                            timeout=ClientTimeout(total=API_TIMEOUT_DISCOVERY),
                        ) as summary_response:
                            if summary_response.status == 200:
                                summary_data = await summary_response.json()

                                if isinstance(summary_data, dict):
                                    extracted_user_id = summary_data.get("user_id") or summary_data.get("userId") or summary_data.get("owner_id")
                                    if extracted_user_id:
                                        return int(extracted_site_id), int(extracted_user_id)
                    except Exception:
                        pass

        except Exception:
            pass  # Try next method

        # Méthode 3: Essayer d'extraire user_id depuis le JWT token dans les cookies
        try:
            import json
            import base64

            cookies = self._session.cookie_jar.filter_cookies(API_BASE_URL)

            for cookie in cookies.values():
                # Chercher le token JWT enlighten_manager_token_production
                if "enlighten_manager_token" in cookie.key.lower():
                    try:
                        # Décoder le JWT (format: header.payload.signature)
                        token_parts = cookie.value.split('.')
                        if len(token_parts) >= 2:
                            # Décoder la partie payload (partie 2)
                            payload_b64 = token_parts[1]
                            # Ajouter le padding si nécessaire
                            padding = 4 - len(payload_b64) % 4
                            if padding != 4:
                                payload_b64 += '=' * padding

                            payload_json = base64.b64decode(payload_b64).decode('utf-8')
                            payload_data = json.loads(payload_json)

                            # Extraire user_id du JWT
                            # Format: {"data": {"user_id": 3057320, ...}, ...}
                            if "data" in payload_data and "user_id" in payload_data["data"]:
                                extracted_user_id = payload_data["data"]["user_id"]
                    except Exception:
                        pass
        except Exception:
            pass

        # Vérifier ce qu'on a trouvé
        if extracted_site_id and extracted_user_id:
            return int(extracted_site_id), int(extracted_user_id)
        elif extracted_site_id:
            _LOGGER.warning(f"Found site_id={extracted_site_id} but not user_id. Returning with user_id=0")
            return int(extracted_site_id), 0
        elif extracted_user_id:
            raise EnphaseBatteryAuthError(
                "Could not determine site_id. Please check logs for details. "
                "You may need to configure the site_id manually."
            )
        else:
            raise EnphaseBatteryAuthError(
                "Could not determine site_id. Please check logs for details. "
                "You may need to configure the site_id manually."
            )

    async def get_battery_data(self) -> dict[str, Any]:
        """Get current battery data including SOC, power, and stats.

        Returns comprehensive battery information from /pv/systems/{site_id}/today endpoint.
        """
        if not self._site_id:
            raise EnphaseBatteryAuthError("Not authenticated - site_id missing")

        url = f"{API_BASE_URL}/pv/systems/{self._site_id}/today"

        try:
            async with self._session.get(
                url,
                headers=self._get_headers(),
                timeout=ClientTimeout(total=API_TIMEOUT),
            ) as response:
                response.raise_for_status()
                data = await response.json()

                # Récupérer aussi les battery settings pour avoir les paramètres de configuration
                battery_settings = None
                try:
                    battery_settings = await self.get_battery_settings()
                except Exception:
                    pass

                return self._parse_battery_data(data, battery_settings)

        except aiohttp.ClientError as err:
            raise EnphaseBatteryConnectionError(f"Failed to get battery data: {err}") from err

    def _parse_battery_data(self, data: dict[str, Any], battery_settings: dict[str, Any] | None = None) -> dict[str, Any]:
        """Parse battery data from API response."""
        battery_details = data.get("battery_details", {})
        battery_config = data.get("batteryConfig", {})
        stats = data.get("stats", [{}])[0]

        # Dernières valeurs (dernier intervalle non-null)
        latest_soc = self._get_latest_value(stats.get("soc", []))
        latest_charge = self._get_latest_value(stats.get("charge", []))
        latest_discharge = self._get_latest_value(stats.get("discharge", []))

        # Utiliser battery_settings si disponible pour les paramètres de configuration
        # Sinon fallback sur batteryConfig (qui peut être vide/absent)
        config_source = battery_settings if battery_settings else battery_config

        # Extract dtgControl (Discharge To Grid) setting
        dtg_control = config_source.get("dtgControl", {})
        discharge_to_grid_enabled = dtg_control.get("enabled", False) if isinstance(dtg_control, dict) else False

        # Extract rbdControl (Reserve Battery Discharge) setting
        rbd_control = config_source.get("rbdControl", {})
        reserve_battery_discharge_enabled = rbd_control.get("enabled", False) if isinstance(rbd_control, dict) else False

        return {
            # État de charge
            "soc": battery_details.get("aggregate_soc", latest_soc),

            # Puissances instantanées
            "power": self._calculate_battery_power(latest_charge, latest_discharge),
            "charge_power": latest_charge or 0,
            "discharge_power": latest_discharge or 0,

            # Statistiques journalières
            "consumption_24h": battery_details.get("last_24h_consumption", 0),
            "estimated_backup_time": battery_details.get("estimated_time", 0),

            # Configuration - prioriser battery_settings (camelCase) puis batteryConfig (snake_case)
            "mode": config_source.get("profile", battery_config.get("usage", "unknown")),
            "backup_reserve": config_source.get("batteryBackupPercentage", battery_config.get("battery_backup_percentage", 0)),
            "charge_from_grid": config_source.get("chargeFromGrid", battery_config.get("charge_from_grid", False)),
            "discharge_to_grid": discharge_to_grid_enabled,
            "reserve_battery_discharge": reserve_battery_discharge_enabled,
            "very_low_soc": config_source.get("veryLowSoc", battery_config.get("very_low_soc", 5)),

            # Totaux du jour
            "energy_charged_today": stats.get("totals", {}).get("charge", 0) / 1000,  # Wh -> kWh
            "energy_discharged_today": stats.get("totals", {}).get("discharge", 0) / 1000,

            # État système
            "status": data.get("siteStatus", "unknown"),
            "last_update": datetime.now().isoformat(),
        }

    def _get_latest_value(self, values: list) -> int | None:
        """Get the latest non-null value from a list."""
        for value in reversed(values):
            if value is not None:
                return value
        return None

    def _calculate_battery_power(self, charge: int | None, discharge: int | None) -> int:
        """Calculate net battery power (negative = charging, positive = discharging)."""
        charge_val = charge or 0
        discharge_val = discharge or 0

        # Convention: discharge positif, charge négatif
        return discharge_val - charge_val

    async def get_battery_settings(self) -> dict[str, Any]:
        """Get battery settings and configuration."""
        if not self._site_id or not self._user_id:
            raise EnphaseBatteryAuthError("Not authenticated")

        url = f"{API_BASE_URL}/service/batteryConfig/api/v1/batterySettings/{self._site_id}"
        params = {"source": "enho", "userId": self._user_id}

        try:
            async with self._session.get(
                url,
                params=params,
                headers=self._get_headers(),
                timeout=ClientTimeout(total=API_TIMEOUT),
            ) as response:
                response.raise_for_status()
                result = await response.json()
                return result.get("data", {})

        except aiohttp.ClientError as err:
            raise EnphaseBatteryConnectionError(f"Failed to get battery settings: {err}") from err

    async def get_battery_profile(self) -> dict[str, Any]:
        """Get battery profile details."""
        if not self._site_id or not self._user_id:
            raise EnphaseBatteryAuthError("Not authenticated")

        url = f"{API_BASE_URL}/service/batteryConfig/api/v1/profile/{self._site_id}"
        params = {"source": "enho", "userId": self._user_id}

        try:
            async with self._session.get(
                url,
                params=params,
                headers=self._get_headers(),
                timeout=ClientTimeout(total=API_TIMEOUT),
            ) as response:
                response.raise_for_status()
                result = await response.json()
                return result.get("data", {})

        except aiohttp.ClientError as err:
            raise EnphaseBatteryConnectionError(f"Failed to get battery profile: {err}") from err

    async def get_battery_schedules(self) -> dict[str, Any]:
        """Get battery charge/discharge schedules."""
        if not self._site_id:
            raise EnphaseBatteryAuthError("Not authenticated")

        url = f"{API_BASE_URL}/service/batteryConfig/api/v1/battery/sites/{self._site_id}/schedules"

        try:
            async with self._session.get(
                url,
                headers=self._get_headers(),
                timeout=ClientTimeout(total=API_TIMEOUT),
            ) as response:
                response.raise_for_status()
                return await response.json()

        except aiohttp.ClientError as err:
            raise EnphaseBatteryConnectionError(f"Failed to get schedules: {err}") from err

    async def get_devices(self) -> dict[str, Any]:
        """Get list of Enphase devices."""
        if not self._site_id:
            raise EnphaseBatteryAuthError("Not authenticated")

        url = f"{API_BASE_URL}/app-api/{self._site_id}/devices.json"

        try:
            async with self._session.get(
                url,
                headers=self._get_headers(),
                timeout=ClientTimeout(total=API_TIMEOUT),
            ) as response:
                response.raise_for_status()
                return await response.json()

        except aiohttp.ClientError as err:
            raise EnphaseBatteryConnectionError(f"Failed to get devices: {err}") from err

    async def get_mqtt_credentials(self) -> dict[str, Any] | None:
        """Get MQTT connection credentials for real-time updates.

        Returns AWS IoT endpoint, topic, and authentication token.
        """
        if not self._site_id:
            raise EnphaseBatteryAuthError("Not authenticated")

        url = f"{API_BASE_URL}/service/batteryConfig/api/v1/mqttSignedUrl/{self._site_id}"

        try:
            async with self._session.get(
                url,
                headers=self._get_headers(),
                timeout=ClientTimeout(total=API_TIMEOUT),
            ) as response:
                response.raise_for_status()
                return await response.json()

        except aiohttp.ClientError as err:
            _LOGGER.error(f"Failed to get MQTT credentials: {err}")
            return None

    async def set_battery_mode(self, mode: str) -> bool:
        """Set battery operation mode.

        Args:
            mode: One of 'self-consumption', 'cost_savings', 'backup_only', 'expert'

        Returns:
            True if successful
        """
        if not self._site_id or not self._user_id:
            raise EnphaseBatteryAuthError("Not authenticated")

        # Get current battery settings to preserve other values
        try:
            current_settings = await self.get_battery_settings()
        except Exception as err:
            raise EnphaseBatteryConnectionError(f"Failed to get current settings: {err}") from err

        # Update the profile field (battery mode)
        data = current_settings.copy()
        data["profile"] = mode

        # Send PUT request
        url = f"{API_BASE_URL}/service/batteryConfig/api/v1/batterySettings/{self._site_id}"
        params = {"userId": self._user_id, "source": "enho"}

        try:
            async with self._session.put(
                url,
                params=params,
                json=data,
                headers=self._get_headers(),
                timeout=ClientTimeout(total=API_TIMEOUT),
            ) as response:
                response.raise_for_status()
                result = await response.json()

                # Check for success message
                return result.get("message") == "success"

        except aiohttp.ClientError as err:
            raise EnphaseBatteryConnectionError(f"Failed to set battery mode: {err}") from err

    async def set_backup_reserve(self, percentage: int) -> bool:
        """Set battery backup reserve percentage (batteryBackupPercentage).

        Args:
            percentage: Reserve percentage (10-100)
        """
        if not self._site_id or not self._user_id:
            raise EnphaseBatteryAuthError("Not authenticated")

        # Get current battery settings to preserve other values
        try:
            current_settings = await self.get_battery_settings()
        except Exception as err:
            raise EnphaseBatteryConnectionError(f"Failed to get current settings: {err}") from err

        # Update the batteryBackupPercentage field
        data = current_settings.copy()
        data["batteryBackupPercentage"] = percentage

        # Send PUT request
        url = f"{API_BASE_URL}/service/batteryConfig/api/v1/batterySettings/{self._site_id}"
        params = {"userId": self._user_id, "source": "enho"}

        try:
            async with self._session.put(
                url,
                params=params,
                json=data,
                headers=self._get_headers(),
                timeout=ClientTimeout(total=API_TIMEOUT),
            ) as response:
                response.raise_for_status()
                result = await response.json()

                return result.get("message") == "success"

        except aiohttp.ClientError as err:
            raise EnphaseBatteryConnectionError(f"Failed to set backup reserve: {err}") from err

    async def set_very_low_soc(self, percentage: int) -> bool:
        """Set battery very low SOC (minimum discharge level).

        Args:
            percentage: Very low SOC percentage (5-25)
        """
        if not self._site_id or not self._user_id:
            raise EnphaseBatteryAuthError("Not authenticated")

        # Get current battery settings to preserve other values
        try:
            current_settings = await self.get_battery_settings()
        except Exception as err:
            raise EnphaseBatteryConnectionError(f"Failed to get current settings: {err}") from err

        # Update the veryLowSoc field
        data = current_settings.copy()
        data["veryLowSoc"] = percentage

        # Send PUT request
        url = f"{API_BASE_URL}/service/batteryConfig/api/v1/batterySettings/{self._site_id}"
        params = {"userId": self._user_id, "source": "enho"}

        try:
            async with self._session.put(
                url,
                params=params,
                json=data,
                headers=self._get_headers(),
                timeout=ClientTimeout(total=API_TIMEOUT),
            ) as response:
                response.raise_for_status()
                result = await response.json()

                return result.get("message") == "success"

        except aiohttp.ClientError as err:
            raise EnphaseBatteryConnectionError(f"Failed to set very low SOC: {err}") from err

    async def set_charge_from_grid(self, enabled: bool) -> bool:
        """Enable/disable charging from grid.

        Args:
            enabled: True to enable, False to disable

        Returns:
            True if successful
        """
        if not self._site_id or not self._user_id:
            raise EnphaseBatteryAuthError("Not authenticated")

        # First, get current battery settings to preserve other values
        try:
            current_settings = await self.get_battery_settings()
        except Exception as err:
            raise EnphaseBatteryConnectionError(f"Failed to get current settings: {err}") from err

        # Update the charge_from_grid field
        # Note: current_settings is already the "data" object from get_battery_settings()
        data = current_settings.copy()  # Make a copy to avoid modifying cached data
        data["chargeFromGrid"] = enabled

        # Send PUT request
        url = f"{API_BASE_URL}/service/batteryConfig/api/v1/batterySettings/{self._site_id}"
        params = {"userId": self._user_id, "source": "enho"}

        try:
            async with self._session.put(
                url,
                params=params,
                json=data,
                headers=self._get_headers(),
                timeout=ClientTimeout(total=API_TIMEOUT),
            ) as response:
                response.raise_for_status()
                result = await response.json()

                # Check for success message
                return result.get("message") == "success"

        except aiohttp.ClientError as err:
            raise EnphaseBatteryConnectionError(f"Failed to set charge from grid: {err}") from err

    async def set_limit_discharge(self, enabled: bool) -> bool:
        """Enable/disable battery discharge to grid limit (Discharge To Grid control).

        Args:
            enabled: True to enable discharge to grid, False to disable

        Returns:
            True if successful
        """
        if not self._site_id or not self._user_id:
            raise EnphaseBatteryAuthError("Not authenticated")

        # Get current battery settings to preserve other values
        try:
            current_settings = await self.get_battery_settings()
        except Exception as err:
            raise EnphaseBatteryConnectionError(f"Failed to get current settings: {err}") from err

        # Update the dtgControl.enabled field (Discharge To Grid)
        data = current_settings.copy()

        # Ensure dtgControl exists
        if "dtgControl" not in data:
            data["dtgControl"] = {
                "show": True,
                "showDaySchedule": True,
                "enabled": enabled,
                "locked": False,
                "scheduleSupported": True,
                "startTime": 960,
                "endTime": 1140
            }
        else:
            # Update only the enabled field
            data["dtgControl"]["enabled"] = enabled

        # Send PUT request
        url = f"{API_BASE_URL}/service/batteryConfig/api/v1/batterySettings/{self._site_id}"
        params = {"userId": self._user_id, "source": "enho"}

        try:
            async with self._session.put(
                url,
                params=params,
                json=data,
                headers=self._get_headers(),
                timeout=ClientTimeout(total=API_TIMEOUT),
            ) as response:
                response.raise_for_status()
                result = await response.json()

                # Check for success message
                return result.get("message") == "success"

        except aiohttp.ClientError as err:
            raise EnphaseBatteryConnectionError(f"Failed to set limit discharge: {err}") from err

    async def set_reserve_battery_discharge(self, enabled: bool) -> bool:
        """Enable/disable reserve battery discharge (rbdControl).

        Args:
            enabled: True to enable reserve/limit discharge, False to disable

        Returns:
            True if successful
        """
        if not self._site_id or not self._user_id:
            raise EnphaseBatteryAuthError("Not authenticated")

        # Get current battery settings to preserve other values
        try:
            current_settings = await self.get_battery_settings()
        except Exception as err:
            raise EnphaseBatteryConnectionError(f"Failed to get current settings: {err}") from err

        # Update the rbdControl.enabled field (Reserve Battery Discharge)
        data = current_settings.copy()

        # Ensure rbdControl exists
        if "rbdControl" not in data:
            data["rbdControl"] = {
                "show": True,
                "showDaySchedule": True,
                "enabled": enabled,
                "locked": False,
                "scheduleSupported": True,
                "startTime": None,
                "endTime": None
            }
        else:
            # Update only the enabled field
            data["rbdControl"]["enabled"] = enabled

        # Send PUT request
        url = f"{API_BASE_URL}/service/batteryConfig/api/v1/batterySettings/{self._site_id}"
        params = {"userId": self._user_id, "source": "enho"}

        try:
            async with self._session.put(
                url,
                params=params,
                json=data,
                headers=self._get_headers(),
                timeout=ClientTimeout(total=API_TIMEOUT),
            ) as response:
                response.raise_for_status()
                result = await response.json()

                # Check for success message
                return result.get("message") == "success"

        except aiohttp.ClientError as err:
            raise EnphaseBatteryConnectionError(f"Failed to set reserve battery discharge: {err}") from err
