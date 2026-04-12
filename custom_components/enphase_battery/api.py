"""API Client for Enphase Battery IQ 5P."""

from __future__ import annotations

import asyncio
import base64
from datetime import datetime
import json
import logging
import re
from typing import Any

import aiohttp
from aiohttp import ClientSession, ClientTimeout

_LOGGER = logging.getLogger(__name__)

API_BASE_URL = "https://enlighten.enphaseenergy.com"
API_TIMEOUT = 30  # Increased timeout for slow/unstable cloud API (was 15s)
API_TIMEOUT_DISCOVERY = 5  # Faster timeout for auto-discovery endpoints


class EnphaseBatteryApiError(Exception):
    """Base exception for Enphase Battery API errors."""


class EnphaseBatteryAuthError(EnphaseBatteryApiError):
    """Authentication error."""


class EnphaseBatteryConnectionError(EnphaseBatteryApiError):
    """Connection error."""


class EnphaseBatteryRateLimitError(EnphaseBatteryApiError):
    """Rate limit exceeded error."""


# Retry configuration
MAX_RETRIES = 3
RETRY_BACKOFF_FACTOR = 2  # Exponential backoff: 1s, 2s, 4s
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


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
        self._is_authenticated: bool = False

    async def _request_with_reauth(  # type: ignore[no-untyped-def]
        self,
        method: str,
        url: str,
        return_json: bool = True,
        **kwargs,
    ) -> dict[str, Any] | list[Any] | None:
        """Make HTTP request with retry, backoff, and automatic re-authentication.

        Features:
        - Automatic retry with exponential backoff for transient errors
        - Re-authentication on 401 Unauthorized
        - Rate limit handling with 429 responses

        Args:
            method: HTTP method (GET, POST, PUT, etc.)
            url: Full URL to request
            return_json: Whether to parse and return JSON response
            **kwargs: Additional arguments for aiohttp request

        Returns:
            Parsed JSON response (dict or list)

        Raises:
            EnphaseBatteryConnectionError: Connection failed after retries
            EnphaseBatteryAuthError: Authentication failed after retry
            EnphaseBatteryRateLimitError: Rate limit exceeded
        """
        # Ensure headers are set
        if "headers" not in kwargs:
            kwargs["headers"] = self._get_headers()

        # Set default timeout if not provided
        if "timeout" not in kwargs:
            kwargs["timeout"] = ClientTimeout(total=API_TIMEOUT)

        last_error: Exception | None = None

        for attempt in range(MAX_RETRIES):
            try:
                async with self._session.request(method, url, **kwargs) as response:
                    # Handle 401 Unauthorized - re-authenticate
                    if response.status == 401:
                        _LOGGER.info("Session expired (401), re-authenticating...")
                        self._is_authenticated = False

                        try:
                            await self._login()
                            self._is_authenticated = True
                        except Exception as err:
                            raise EnphaseBatteryAuthError(f"Re-authentication failed: {err}") from err

                        # Update headers with new session cookies and retry
                        kwargs["headers"] = self._get_headers()
                        async with self._session.request(method, url, **kwargs) as retry_response:
                            if retry_response.status == 401:
                                raise EnphaseBatteryAuthError("Authentication failed after re-login")
                            retry_response.raise_for_status()
                            if return_json:
                                return await retry_response.json()  # type: ignore[no-any-return]
                            return None

                    # Handle rate limiting (429)
                    if response.status == 429:
                        retry_after = int(response.headers.get("Retry-After", 60))
                        _LOGGER.warning("Rate limited by Enphase API, retry after %ds", retry_after)
                        if attempt < MAX_RETRIES - 1:
                            await asyncio.sleep(min(retry_after, 120))  # Cap at 2 minutes
                            continue
                        raise EnphaseBatteryRateLimitError(f"Rate limit exceeded, retry after {retry_after}s")

                    # Handle retryable server errors (500, 502, 503, 504)
                    if response.status in RETRYABLE_STATUS_CODES:
                        if attempt < MAX_RETRIES - 1:
                            wait_time = RETRY_BACKOFF_FACTOR**attempt
                            _LOGGER.debug(
                                "Server error %d, retrying in %ds (attempt %d/%d)",
                                response.status,
                                wait_time,
                                attempt + 1,
                                MAX_RETRIES,
                            )
                            await asyncio.sleep(wait_time)
                            continue
                        response.raise_for_status()

                    response.raise_for_status()
                    if return_json:
                        return await response.json()  # type: ignore[no-any-return]
                    return None

            except aiohttp.ClientError as err:
                last_error = err
                if attempt < MAX_RETRIES - 1:
                    wait_time = RETRY_BACKOFF_FACTOR**attempt
                    _LOGGER.debug(
                        "Connection error: %s, retrying in %ds (attempt %d/%d)",
                        err,
                        wait_time,
                        attempt + 1,
                        MAX_RETRIES,
                    )
                    await asyncio.sleep(wait_time)
                    continue
                raise EnphaseBatteryConnectionError(f"Request failed after {MAX_RETRIES} retries: {err}") from err

        # Should not reach here, but handle edge case
        raise EnphaseBatteryConnectionError(f"Request failed: {last_error}")

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
        cookies = self._session.cookie_jar.filter_cookies(API_BASE_URL)  # type: ignore[arg-type]
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
                        _LOGGER.info("Auto-detected site_id: %s", self._site_id)

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
                    _LOGGER.error("Auto-detection failed: %s", err)

                    # Si on n'a toujours pas les IDs nécessaires
                    if not self._site_id:
                        raise EnphaseBatteryAuthError(
                            "Could not auto-detect site_id. Please add 'site_id: YOUR_SITE_ID' to your configuration. "
                            f"Error details: {err}"
                        )

            # Note: Envoy serial is fetched later on-demand, not during auth
            # This saves 1-2 seconds during authentication

            _LOGGER.info("Authenticated successfully - site_id: %s", self._site_id)
            self._is_authenticated = True
            return True

        except EnphaseBatteryAuthError:
            self._is_authenticated = False
            raise
        except aiohttp.ClientError as err:
            raise EnphaseBatteryConnectionError(f"Connection error: {err}") from err
        except Exception as err:
            raise EnphaseBatteryApiError(f"Authentication failed: {err}") from err

    async def _login(self) -> bool:
        """Login to Enphase Enlighten to obtain session cookies.

        Uses a fresh aiohttp session (like pyenphase) to avoid
        HA-managed session headers causing 406 errors.

        Returns:
            True if login successful
        """
        url = f"{API_BASE_URL}/login/login.json?"

        payload = {
            "user[email]": self._username,
            "user[password]": self._password,
        }

        try:
            # Use fresh session for cloud auth (HA session may have conflicting headers)
            async with (
                aiohttp.ClientSession(
                    timeout=ClientTimeout(total=API_TIMEOUT_DISCOVERY),
                ) as cloud_session,
                cloud_session.post(url, data=payload) as response,
            ):
                if response.status == 200:
                    # Transfer cookies to the main session
                    if response.cookies:
                        self._session.cookie_jar.update_cookies(response.cookies, response.url)
                    _LOGGER.debug("Enlighten login successful")
                    return True

                if response.status == 401:
                    raise EnphaseBatteryAuthError("Invalid credentials")

                _LOGGER.error("Login failed with status %s", response.status)
                return False

        except aiohttp.ClientError as err:
            raise EnphaseBatteryConnectionError(f"Login connection error: {err}") from err

    async def _get_session_token(self) -> str | None:  # type: ignore[return]
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
                            return token  # type: ignore[no-any-return]

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
                        return envoy.get("serial_number")  # type: ignore[no-any-return]

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
                        def find_user_id(obj, depth=0):  # type: ignore[no-untyped-def]
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
        # Variables to store results as we go
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
                        _LOGGER.error("Failed to parse JSON from search_sites: %s", json_err)
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
                                    site_id = (
                                        first_site.get("system_id") or first_site.get("site_id") or first_site.get("id")
                                    )
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
                url_str = str(response.url)
                match = re.search(r"/web/(\d+)", url_str)
                if match:
                    extracted_site_id = int(match.group(1))

                    # Maintenant on doit trouver le user_id
                    # Essayer de le récupérer depuis les settings de la batterie
                    try:
                        settings_url = (
                            f"{API_BASE_URL}/service/batteryConfig/api/v1/batterySettings/{extracted_site_id}"
                        )
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
                                    extracted_user_id = (
                                        summary_data.get("user_id")
                                        or summary_data.get("userId")
                                        or summary_data.get("owner_id")
                                    )
                                    if extracted_user_id:
                                        return int(extracted_site_id), int(extracted_user_id)
                    except Exception:
                        pass

        except Exception:
            pass  # Try next method

        # Méthode 3: Essayer d'extraire user_id depuis le JWT token dans les cookies
        try:
            cookies = self._session.cookie_jar.filter_cookies(API_BASE_URL)  # type: ignore[arg-type]

            for cookie in cookies.values():
                # Chercher le token JWT enlighten_manager_token_production
                if "enlighten_manager_token" in cookie.key.lower():
                    try:
                        # Décoder le JWT (format: header.payload.signature)
                        token_parts = cookie.value.split(".")
                        if len(token_parts) >= 2:
                            # Décoder la partie payload (partie 2)
                            payload_b64 = token_parts[1]
                            # Ajouter le padding si nécessaire
                            padding = 4 - len(payload_b64) % 4
                            if padding != 4:
                                payload_b64 += "=" * padding

                            payload_json = base64.b64decode(payload_b64).decode("utf-8")
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
            _LOGGER.warning("Found site_id=%s but not user_id. Returning with user_id=0", extracted_site_id)
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
        Optimized: Fetches main data and battery settings in parallel.
        """
        if not self._site_id:
            raise EnphaseBatteryAuthError("Not authenticated - site_id missing")

        url = f"{API_BASE_URL}/pv/systems/{self._site_id}/today"

        async def _fetch_today_data():  # type: ignore[no-untyped-def]
            async with self._session.get(
                url,
                headers=self._get_headers(),
                timeout=ClientTimeout(total=API_TIMEOUT),
            ) as response:
                response.raise_for_status()
                return await response.json()

        async def _fetch_battery_settings():  # type: ignore[no-untyped-def]
            try:
                return await self.get_battery_settings()
            except Exception:
                return None

        try:
            # Parallel fetch: main data + battery settings (saves ~1-2s)
            data, battery_settings = await asyncio.gather(
                _fetch_today_data(),
                _fetch_battery_settings(),
            )

            return self._parse_battery_data(data, battery_settings)

        except aiohttp.ClientError as err:
            raise EnphaseBatteryConnectionError(f"Failed to get battery data: {err}") from err

    def _parse_battery_data(
        self, data: dict[str, Any], battery_settings: dict[str, Any] | None = None
    ) -> dict[str, Any]:
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
        reserve_battery_discharge_enabled = (
            rbd_control.get("enabled", False) if isinstance(rbd_control, dict) else False
        )

        # Extract powerMatchControl (PowerMatch) setting
        power_match_control = config_source.get("powerMatchControl", {})
        power_match_enabled = (
            power_match_control.get("enabled", False) if isinstance(power_match_control, dict) else False
        )

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
            "backup_reserve": config_source.get(
                "batteryBackupPercentage", battery_config.get("battery_backup_percentage", 0)
            ),
            "charge_from_grid": config_source.get("chargeFromGrid", battery_config.get("charge_from_grid", False)),
            "discharge_to_grid": discharge_to_grid_enabled,
            "reserve_battery_discharge": reserve_battery_discharge_enabled,
            "power_match": power_match_enabled,
            "very_low_soc": config_source.get("veryLowSoc", battery_config.get("very_low_soc", 5)),
            # Totaux du jour
            "energy_charged_today": stats.get("totals", {}).get("charge", 0) / 1000,  # Wh -> kWh
            "energy_discharged_today": stats.get("totals", {}).get("discharge", 0) / 1000,
            # État système
            "status": data.get("siteStatus", "unknown"),
            "last_update": datetime.now().isoformat(),
        }

    def _get_latest_value(self, values: list) -> int | None:  # type: ignore[type-arg]
        """Get the latest non-null value from a list."""
        for value in reversed(values):
            if value is not None:
                return value  # type: ignore[no-any-return]
        return None

    def _calculate_battery_power(self, charge: int | None, discharge: int | None) -> int:
        """Calculate net battery power (negative = charging, positive = discharging)."""
        charge_val = charge or 0
        discharge_val = discharge or 0

        # Convention: discharge positif, charge négatif
        return discharge_val - charge_val

    async def get_battery_settings(self) -> dict[str, Any]:
        """Get battery settings and configuration.

        Uses automatic re-authentication on 401 to handle session expiry.
        """
        if not self._site_id or not self._user_id:
            raise EnphaseBatteryAuthError("Not authenticated")

        url = f"{API_BASE_URL}/service/batteryConfig/api/v1/batterySettings/{self._site_id}"
        params = {"source": "enho", "userId": self._user_id}

        try:
            result = await self._request_with_reauth("GET", url, params=params)
            return result.get("data", {}) if result else {}  # type: ignore[union-attr]
        except (EnphaseBatteryAuthError, EnphaseBatteryConnectionError):
            raise
        except Exception as err:
            raise EnphaseBatteryConnectionError(f"Failed to get battery settings: {err}") from err

    async def _update_battery_settings(self, data: dict[str, Any]) -> bool:
        """Update battery settings with automatic re-authentication on 401.

        Args:
            data: Battery settings data to update

        Returns:
            True if successful
        """
        url = f"{API_BASE_URL}/service/batteryConfig/api/v1/batterySettings/{self._site_id}"
        params = {"userId": self._user_id, "source": "enho"}

        try:
            result = await self._request_with_reauth("PUT", url, params=params, json=data)
            return result.get("message") == "success" if result else False  # type: ignore[union-attr]
        except (EnphaseBatteryAuthError, EnphaseBatteryConnectionError):
            raise
        except Exception as err:
            raise EnphaseBatteryConnectionError(f"Failed to update battery settings: {err}") from err

    async def get_battery_profile(self) -> dict[str, Any]:
        """Get battery profile details."""
        if not self._site_id or not self._user_id:
            raise EnphaseBatteryAuthError("Not authenticated")

        url = f"{API_BASE_URL}/service/batteryConfig/api/v1/profile/{self._site_id}"
        params = {"source": "enho", "userId": self._user_id}

        try:
            async with self._session.get(
                url,
                params=params,  # type: ignore[arg-type]
                headers=self._get_headers(),
                timeout=ClientTimeout(total=API_TIMEOUT),
            ) as response:
                response.raise_for_status()
                result = await response.json()
                return result.get("data", {})  # type: ignore[no-any-return]

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
                return await response.json()  # type: ignore[no-any-return]

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
                return await response.json()  # type: ignore[no-any-return]

        except aiohttp.ClientError as err:
            raise EnphaseBatteryConnectionError(f"Failed to get devices: {err}") from err

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
        current_settings = await self.get_battery_settings()

        # Update the profile field (battery mode)
        data = current_settings.copy()
        data["profile"] = mode

        return await self._update_battery_settings(data)

    async def set_backup_reserve(self, percentage: int) -> bool:
        """Set battery backup reserve percentage (batteryBackupPercentage).

        Args:
            percentage: Reserve percentage (10-100)
        """
        if not self._site_id or not self._user_id:
            raise EnphaseBatteryAuthError("Not authenticated")

        # Get current battery settings to preserve other values
        current_settings = await self.get_battery_settings()

        # Update the batteryBackupPercentage field
        data = current_settings.copy()
        data["batteryBackupPercentage"] = percentage

        return await self._update_battery_settings(data)

    async def set_very_low_soc(self, percentage: int) -> bool:
        """Set battery very low SOC (minimum discharge level).

        Args:
            percentage: Very low SOC percentage (5-25)
        """
        if not self._site_id or not self._user_id:
            raise EnphaseBatteryAuthError("Not authenticated")

        # Get current battery settings to preserve other values
        current_settings = await self.get_battery_settings()

        # Update the veryLowSoc field
        data = current_settings.copy()
        data["veryLowSoc"] = percentage

        return await self._update_battery_settings(data)

    async def set_charge_from_grid(self, enabled: bool) -> bool:
        """Enable/disable charging from grid.

        Args:
            enabled: True to enable, False to disable

        Returns:
            True if successful
        """
        if not self._site_id or not self._user_id:
            raise EnphaseBatteryAuthError("Not authenticated")

        # Get current battery settings to preserve other values
        current_settings = await self.get_battery_settings()

        # Update the charge_from_grid field
        data = current_settings.copy()
        data["chargeFromGrid"] = enabled

        return await self._update_battery_settings(data)

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
        current_settings = await self.get_battery_settings()

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
                "endTime": 1140,
            }
        else:
            # Update only the enabled field
            data["dtgControl"]["enabled"] = enabled

        return await self._update_battery_settings(data)

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
        current_settings = await self.get_battery_settings()

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
                "endTime": None,
            }
        else:
            # Update only the enabled field
            data["rbdControl"]["enabled"] = enabled

        return await self._update_battery_settings(data)

    async def set_power_match(self, enabled: bool) -> bool:
        """Enable/disable PowerMatch (powerMatchControl).

        PowerMatch optimizes battery usage to match grid power patterns.

        Args:
            enabled: True to enable, False to disable

        Returns:
            True if successful
        """
        if not self._site_id or not self._user_id:
            raise EnphaseBatteryAuthError("Not authenticated")

        # Get current battery settings to preserve other values
        current_settings = await self.get_battery_settings()

        # Update the powerMatchControl.enabled field
        data = current_settings.copy()

        # Ensure powerMatchControl exists
        if "powerMatchControl" not in data:
            data["powerMatchControl"] = {
                "show": True,
                "enabled": enabled,
            }
        else:
            # Update only the enabled field
            data["powerMatchControl"]["enabled"] = enabled

        return await self._update_battery_settings(data)
