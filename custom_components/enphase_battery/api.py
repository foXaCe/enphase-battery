"""API Client for Enphase Battery IQ 5P."""
from __future__ import annotations

import logging
from typing import Any
from datetime import datetime

import aiohttp
from aiohttp import ClientSession, ClientTimeout

_LOGGER = logging.getLogger(__name__)

API_BASE_URL = "https://enlighten.enphaseenergy.com"
API_TIMEOUT = 30


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
            _LOGGER.info("Authenticating with Enphase Enlighten...")

            # Étape 1: Login avec username/password pour obtenir session cookies
            login_success = await self._login()
            if not login_success:
                raise EnphaseBatteryAuthError("Login failed")

            # Étape 2: Obtenir le token de session
            session_token = await self._get_session_token()
            if session_token:
                self._session_token = session_token
                _LOGGER.debug("Session token obtained")

            # Étape 3: Récupérer site_id et user_id de l'utilisateur (si pas déjà fourni)
            if not self._site_id or not self._user_id:
                _LOGGER.info("Site ID or User ID not provided, attempting auto-detection...")
                _LOGGER.debug(f"Current state: site_id={self._site_id}, user_id={self._user_id}")

                try:
                    detected_site_id, detected_user_id = await self._get_user_sites()

                    if not self._site_id and detected_site_id:
                        self._site_id = detected_site_id
                        _LOGGER.info(f"✅ Auto-detected site_id: {self._site_id}")

                    if not self._user_id and detected_user_id:
                        self._user_id = detected_user_id
                        _LOGGER.info(f"✅ Auto-detected user_id: {self._user_id}")

                    # Si on a trouvé site_id mais pas user_id, essayer la méthode alternative
                    if self._site_id and not self._user_id:
                        _LOGGER.info(f"🔍 Auto-detected site_id ({self._site_id}) but not user_id. Trying alternative method...")
                        alternative_user_id = await self._get_user_id_from_battery_settings()
                        if alternative_user_id:
                            self._user_id = alternative_user_id
                            _LOGGER.info(f"✅ Found user_id via alternative method: {self._user_id}")
                        else:
                            _LOGGER.warning(
                                f"⚠️ Could not auto-detect user_id. "
                                "You may need to provide user_id manually in configuration."
                            )

                except EnphaseBatteryAuthError as err:
                    _LOGGER.error(f"❌ Auto-detection failed: {err}")

                    # Si on n'a toujours pas les IDs nécessaires
                    if not self._site_id:
                        raise EnphaseBatteryAuthError(
                            "Could not auto-detect site_id. Please add 'site_id: YOUR_SITE_ID' to your configuration. "
                            f"Error details: {err}"
                        )

                    if not self._user_id:
                        _LOGGER.warning("Could not auto-detect user_id, will try alternative methods later")
                        # On continue, user_id sera tenté via alternative methods si nécessaire

            if self._site_id:
                _LOGGER.info(f"Using site_id: {self._site_id}")
            if self._user_id:
                _LOGGER.info(f"Using user_id: {self._user_id}")

            # Étape 4 (optionnel): Obtenir envoy serial si disponible
            try:
                envoy_serial = await self._get_envoy_serial()
                if envoy_serial:
                    self._envoy_serial = envoy_serial
                    _LOGGER.debug(f"Envoy serial: {envoy_serial}")
            except Exception as err:
                _LOGGER.debug(f"Could not get envoy serial: {err}")

            _LOGGER.info(f"✅ Authenticated successfully - site_id: {self._site_id}")
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
                timeout=ClientTimeout(total=API_TIMEOUT),
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    _LOGGER.debug(f"Login response: {data}")

                    # Vérifier si le login a réussi
                    # L'API retourne généralement un status ou message
                    if data.get("status") == "success" or data.get("message") == "success":
                        _LOGGER.debug("Login successful, session cookies obtained")
                        return True

                    # Certaines réponses contiennent directement le site_id
                    if "user" in data and isinstance(data["user"], dict):
                        user_data = data["user"]
                        if "default_system_id" in user_data:
                            # Site ID trouvé dans la réponse du login!
                            _LOGGER.info("Site ID found in login response")
                            return True

                    # Parfois le login réussit avec un 200 même sans message
                    _LOGGER.debug("Login returned 200, assuming success")
                    return True

                elif response.status == 401:
                    raise EnphaseBatteryAuthError("Invalid credentials")
                else:
                    _LOGGER.error(f"Login failed with status {response.status}")
                    return False

        except aiohttp.ClientError as err:
            _LOGGER.error(f"Login request failed: {err}")
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

                    _LOGGER.debug("Session token response received but format unexpected")
                    return None

                else:
                    _LOGGER.debug(f"Session token request returned status {response.status}")
                    return None

        except Exception as err:
            _LOGGER.debug(f"Failed to get session token: {err}")
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

        except Exception as err:
            _LOGGER.debug(f"Failed to get envoy serial: {err}")
            return None

    async def _get_user_id_from_battery_settings(self) -> int | None:
        """Try to extract user_id by calling batterySettings and parsing response.

        Some Enphase API responses include user_id in their data.

        Returns:
            user_id as int or None if not found
        """
        if not self._site_id:
            _LOGGER.warning("Cannot get user_id: site_id is not set")
            return None

        _LOGGER.info(f"🔍 ALTERNATIVE METHOD: Searching for user_id in various endpoints")

        # Try different endpoints that might include user info
        endpoints_to_try = [
            f"{API_BASE_URL}/pv/systems/{self._site_id}/today",
            f"{API_BASE_URL}/app-api/{self._site_id}/data.json?app=1",
        ]

        for url in endpoints_to_try:
            try:
                _LOGGER.info(f"📡 Trying endpoint: {url}")
                async with self._session.get(
                    url,
                    headers=self._get_headers(),
                    timeout=ClientTimeout(total=API_TIMEOUT),
                ) as response:
                    _LOGGER.info(f"📡 Response status: {response.status}")

                    if response.status == 200:
                        data = await response.json()
                        _LOGGER.info(f"📦 Response data preview: {str(data)[:300]}")

                        # Search for user_id in various possible locations
                        # Sometimes it's in system.user_id, sometimes in meta.user_id, etc.
                        def find_user_id(obj, depth=0, path=""):
                            if depth > 5:  # Limit recursion
                                return None
                            if isinstance(obj, dict):
                                if "user_id" in obj:
                                    _LOGGER.info(f"🎯 Found user_id at path: {path}.user_id")
                                    return obj["user_id"]
                                for key, value in obj.items():
                                    result = find_user_id(value, depth + 1, f"{path}.{key}")
                                    if result:
                                        return result
                            elif isinstance(obj, list):
                                for idx, item in enumerate(obj):
                                    result = find_user_id(item, depth + 1, f"{path}[{idx}]")
                                    if result:
                                        return result
                            return None

                        user_id = find_user_id(data)
                        if user_id:
                            _LOGGER.info(f"✅ Found user_id {user_id} in {url}")
                            return int(user_id)
                        else:
                            _LOGGER.warning(f"⚠️ No user_id found in {url}")

            except Exception as err:
                _LOGGER.debug(f"Failed to get user_id from {url}: {err}")
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
        _LOGGER.info("🔍 MÉTHODE 1: Trying /app-api/search_sites.json")
        url = f"{API_BASE_URL}/app-api/search_sites.json"
        params = {"searchText": "", "favourite": "false"}

        try:
            async with self._session.get(
                url,
                params=params,
                headers=self._get_headers(),
                timeout=ClientTimeout(total=API_TIMEOUT),
            ) as response:
                _LOGGER.info(f"📡 Response status: {response.status}")
                _LOGGER.info(f"📡 Response headers: {dict(response.headers)}")

                if response.status == 200:
                    response_text = await response.text()
                    _LOGGER.info(f"📄 RAW RESPONSE TEXT (first 500 chars):\n{response_text[:500]}")

                    try:
                        data = await response.json()
                    except Exception as json_err:
                        _LOGGER.error(f"❌ Failed to parse JSON: {json_err}")
                        _LOGGER.error(f"Response was: {response_text}")
                        raise

                    _LOGGER.info(f"📦 Parsed data type: {type(data)}")
                    _LOGGER.info(f"📦 Full data structure: {data}")

                    # Extraire le premier site
                    if isinstance(data, list):
                        _LOGGER.info(f"✅ Data is a list with {len(data)} items")
                        if len(data) > 0:
                            first_site = data[0]
                            _LOGGER.info(f"🏠 First site keys: {first_site.keys()}")
                            _LOGGER.info(f"🏠 First site data: {first_site}")

                            site_id = first_site.get("system_id")
                            user_id = first_site.get("user_id")

                            _LOGGER.info(f"🔑 Extracted: site_id={site_id}, user_id={user_id}")

                            if site_id and user_id:
                                _LOGGER.info(f"✅ SUCCESS: Found site_id={site_id}, user_id={user_id}")
                                return int(site_id), int(user_id)
                            else:
                                _LOGGER.warning(f"⚠️ Missing fields in first site")
                        else:
                            _LOGGER.warning(f"⚠️ List is empty")

                    # Si data est un dict avec "systems"
                    elif isinstance(data, dict):
                        _LOGGER.info(f"✅ Data is a dict with keys: {data.keys()}")

                        # Essayer plusieurs clés possibles
                        for key in ["systems", "sites", "data", "result", "response"]:
                            if key in data:
                                _LOGGER.info(f"🔍 Found key '{key}' in response")
                                systems = data[key]
                                _LOGGER.info(f"📦 Type of data['{key}']: {type(systems)}")

                                if isinstance(systems, list):
                                    _LOGGER.info(f"✅ data['{key}'] is a list with {len(systems)} items")
                                    if len(systems) > 0:
                                        first_site = systems[0]
                                        _LOGGER.info(f"🏠 First site keys: {first_site.keys()}")
                                        _LOGGER.info(f"🏠 First site data: {first_site}")

                                        site_id = first_site.get("system_id") or first_site.get("site_id") or first_site.get("id")
                                        user_id = first_site.get("user_id") or first_site.get("owner_id")

                                        _LOGGER.info(f"🔑 Extracted from '{key}': site_id={site_id}, user_id={user_id}")

                                        if site_id and user_id:
                                            _LOGGER.info(f"✅ SUCCESS: Found site_id={site_id}, user_id={user_id} from key '{key}'")
                                            return int(site_id), int(user_id)
                                elif isinstance(systems, dict):
                                    _LOGGER.info(f"📦 data['{key}'] is a dict: {systems}")
                    else:
                        _LOGGER.warning(f"⚠️ Unexpected data type: {type(data)}")
                else:
                    _LOGGER.warning(f"⚠️ Non-200 response: {response.status}")

        except Exception as err:
            _LOGGER.error(f"❌ MÉTHODE 1 FAILED: {err}", exc_info=True)

        # Méthode 2: Essayer /pv/systems endpoint et extraire site_id de l'URL de redirection
        _LOGGER.info("🔍 MÉTHODE 2: Trying /pv/systems endpoint")
        try:
            url = f"{API_BASE_URL}/pv/systems"
            async with self._session.get(
                url,
                headers=self._get_headers(),
                timeout=ClientTimeout(total=API_TIMEOUT),
                allow_redirects=True,
            ) as response:
                _LOGGER.info(f"📡 /pv/systems response status: {response.status}")
                _LOGGER.info(f"📡 /pv/systems final URL: {response.url}")

                # Extraire site_id de l'URL (format: /web/2168380?v=3.4.0)
                import re
                url_str = str(response.url)
                match = re.search(r'/web/(\d+)', url_str)
                if match:
                    extracted_site_id = int(match.group(1))
                    _LOGGER.info(f"✅ Extracted site_id from redirect URL: {extracted_site_id}")

                    # Maintenant on doit trouver le user_id
                    # Essayer de le récupérer depuis les settings de la batterie
                    _LOGGER.info("🔍 Trying to get user_id from battery settings")
                    try:
                        settings_url = f"{API_BASE_URL}/service/batteryConfig/api/v1/batterySettings/{extracted_site_id}"
                        async with self._session.get(
                            settings_url,
                            headers=self._get_headers(),
                            timeout=ClientTimeout(total=API_TIMEOUT),
                        ) as settings_response:
                            _LOGGER.info(f"📡 Battery settings response status: {settings_response.status}")

                            if settings_response.status == 200:
                                settings_text = await settings_response.text()
                                _LOGGER.info(f"📄 Battery settings response (first 500 chars): {settings_text[:500]}")

                                # L'URL doit contenir userId en paramètre
                                settings_data = await settings_response.json()
                                _LOGGER.info(f"📦 Battery settings data: {settings_data}")

                                # Chercher user_id dans la réponse
                                if isinstance(settings_data, dict):
                                    extracted_user_id = settings_data.get("userId") or settings_data.get("user_id")
                                    if extracted_user_id:
                                        _LOGGER.info(f"✅ SUCCESS: Found site_id={extracted_site_id}, user_id={extracted_user_id}")
                                        return int(extracted_site_id), int(extracted_user_id)
                    except Exception as settings_err:
                        _LOGGER.warning(f"⚠️ Could not get user_id from battery settings: {settings_err}")

                    # Si on a site_id mais pas user_id, essayer l'endpoint system summary
                    _LOGGER.info("🔍 Trying to get user_id from system summary")
                    try:
                        summary_url = f"{API_BASE_URL}/api/v4/systems/{extracted_site_id}/summary"
                        async with self._session.get(
                            summary_url,
                            headers=self._get_headers(),
                            timeout=ClientTimeout(total=API_TIMEOUT),
                        ) as summary_response:
                            _LOGGER.info(f"📡 System summary response status: {summary_response.status}")

                            if summary_response.status == 200:
                                summary_data = await summary_response.json()
                                _LOGGER.info(f"📦 System summary data: {summary_data}")

                                if isinstance(summary_data, dict):
                                    extracted_user_id = summary_data.get("user_id") or summary_data.get("userId") or summary_data.get("owner_id")
                                    if extracted_user_id:
                                        _LOGGER.info(f"✅ SUCCESS: Found site_id={extracted_site_id}, user_id={extracted_user_id}")
                                        return int(extracted_site_id), int(extracted_user_id)
                    except Exception as summary_err:
                        _LOGGER.warning(f"⚠️ Could not get user_id from system summary: {summary_err}")

                    # site_id trouvé, mais pas user_id - on va essayer la méthode 3
                    _LOGGER.info(f"⚠️ Found site_id={extracted_site_id} but could not auto-detect user_id from endpoints. Trying JWT method...")

        except Exception as err:
            _LOGGER.error(f"❌ MÉTHODE 2 FAILED: {err}", exc_info=True)

        # Méthode 3: Essayer d'extraire user_id depuis le JWT token dans les cookies
        _LOGGER.info("🔍 MÉTHODE 3: Trying to extract user_id from JWT token in cookies")
        try:
            import json
            import base64

            cookies = self._session.cookie_jar.filter_cookies(API_BASE_URL)
            _LOGGER.info(f"🍪 Found {len(cookies)} cookies")

            for cookie in cookies.values():
                _LOGGER.debug(f"🍪 Cookie: {cookie.key}")

                # Chercher le token JWT enlighten_manager_token_production
                if "enlighten_manager_token" in cookie.key.lower():
                    _LOGGER.info(f"🎯 Found JWT token cookie: {cookie.key}")

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

                            _LOGGER.info(f"📦 JWT payload: {payload_data}")

                            # Extraire user_id du JWT
                            # Format: {"data": {"user_id": 3057320, ...}, ...}
                            if "data" in payload_data and "user_id" in payload_data["data"]:
                                extracted_user_id = payload_data["data"]["user_id"]
                                _LOGGER.info(f"✅ Extracted user_id from JWT: {extracted_user_id}")
                    except Exception as jwt_err:
                        _LOGGER.warning(f"⚠️ Failed to decode JWT: {jwt_err}")
        except Exception as err:
            _LOGGER.error(f"❌ MÉTHODE 3 FAILED: {err}")

        # Vérifier ce qu'on a trouvé
        if extracted_site_id and extracted_user_id:
            _LOGGER.info(f"✅ SUCCESS: Found both site_id={extracted_site_id} and user_id={extracted_user_id}")
            return int(extracted_site_id), int(extracted_user_id)
        elif extracted_site_id:
            _LOGGER.warning(f"⚠️ Found site_id={extracted_site_id} but not user_id. Returning with user_id=0")
            return int(extracted_site_id), 0
        elif extracted_user_id:
            _LOGGER.error(f"❌ Found user_id={extracted_user_id} but not site_id. Cannot proceed without site_id.")
            raise EnphaseBatteryAuthError(
                "Could not determine site_id. Please check logs for details. "
                "You may need to configure the site_id manually."
            )
        else:
            _LOGGER.error("❌ ALL METHODS FAILED - Could not auto-detect site_id or user_id")
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
                except Exception as err:
                    _LOGGER.debug(f"Could not fetch battery settings: {err}")

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
        """
        # TODO: Implémenter après capture de la requête POST
        _LOGGER.warning("set_battery_mode not yet implemented")
        raise NotImplementedError("Setting battery mode requires POST endpoint discovery")

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

                if result.get("message") == "success":
                    _LOGGER.debug(f"Successfully set backup_reserve to {percentage}%")
                    return True
                else:
                    _LOGGER.warning(f"Unexpected response from set_backup_reserve: {result}")
                    return False

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

                if result.get("message") == "success":
                    _LOGGER.debug(f"Successfully set very_low_soc to {percentage}%")
                    return True
                else:
                    _LOGGER.warning(f"Unexpected response from set_very_low_soc: {result}")
                    return False

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
                if result.get("message") == "success":
                    _LOGGER.debug(f"Successfully set charge_from_grid to {enabled}")
                    return True
                else:
                    _LOGGER.warning(f"Unexpected response from charge_from_grid: {result}")
                    return False

        except aiohttp.ClientError as err:
            raise EnphaseBatteryConnectionError(f"Failed to set charge from grid: {err}") from err
