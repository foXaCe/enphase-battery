"""Tests for Enphase Battery API client."""

from __future__ import annotations

import base64
import json
import re
from unittest.mock import AsyncMock, patch

import aiohttp
from aiohttp import ClientSession, ClientTimeout
from aioresponses import aioresponses
import pytest
from yarl import URL

from custom_components.enphase_battery.api.cloud_client import (
    API_BASE_URL,
    API_TIMEOUT,
    API_TIMEOUT_DISCOVERY,
    MAX_RETRIES,
    RETRYABLE_STATUS_CODES,
    EnphaseBatteryAPI,
    EnphaseBatteryApiError,
    EnphaseBatteryAuthError,
    EnphaseBatteryConnectionError,
    EnphaseBatteryRateLimitError,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


# Patterns that match any query-string variation for aioresponses
def _url_pattern(path: str) -> re.Pattern:
    """Build a regex pattern that matches the base URL + path, optionally with query params."""
    escaped = re.escape(f"{API_BASE_URL}{path}")
    return re.compile(rf"^{escaped}(\?.*)?$")


def _set_session_cookie(session: ClientSession, key: str, value: str) -> None:
    """Set a cookie on the session for the API base URL."""
    session.cookie_jar.update_cookies(
        {key: value},
        response_url=URL(API_BASE_URL),
    )


def _make_jwt(payload: dict) -> str:
    """Build a fake JWT string from a payload dict."""
    header = base64.b64encode(json.dumps({"alg": "HS256"}).encode()).decode().rstrip("=")
    body = base64.b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    return f"{header}.{body}.fakesig"


# Patterns used in many tests
LOGIN_URL = f"{API_BASE_URL}/login/login.json?"
SEARCH_SITES_PAT = _url_pattern("/app-api/search_sites.json")
SETTINGS_12345_PAT = _url_pattern("/service/batteryConfig/api/v1/batterySettings/12345")
PROFILE_12345_PAT = _url_pattern("/service/batteryConfig/api/v1/profile/12345")
SCHEDULES_12345_PAT = _url_pattern("/service/batteryConfig/api/v1/battery/sites/12345/schedules")
DEVICES_12345_PAT = _url_pattern("/app-api/12345/devices.json")
TODAY_12345_PAT = _url_pattern("/pv/systems/12345/today")
PV_SYSTEMS_PAT = _url_pattern("/pv/systems")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def session():
    """Create an aiohttp ClientSession for tests."""
    async with aiohttp.ClientSession() as sess:
        yield sess


@pytest.fixture
def api(session: ClientSession) -> EnphaseBatteryAPI:
    """Create an API client with default test credentials."""
    return EnphaseBatteryAPI(
        session=session,
        username="test@example.com",
        password="testpass",
        site_id=12345,
        user_id=67890,
    )


@pytest.fixture
def api_no_ids(session: ClientSession) -> EnphaseBatteryAPI:
    """Create an API client without site_id/user_id."""
    return EnphaseBatteryAPI(
        session=session,
        username="test@example.com",
        password="testpass",
    )


@pytest.fixture
def api_site_only(session: ClientSession) -> EnphaseBatteryAPI:
    """Create an API client with only site_id."""
    return EnphaseBatteryAPI(
        session=session,
        username="test@example.com",
        password="testpass",
        site_id=12345,
    )


# ===========================================================================
# Exception classes
# ===========================================================================


class TestExceptions:
    """Test exception hierarchy."""

    def test_api_error_is_exception(self):
        assert issubclass(EnphaseBatteryApiError, Exception)

    def test_auth_error_is_api_error(self):
        assert issubclass(EnphaseBatteryAuthError, EnphaseBatteryApiError)

    def test_connection_error_is_api_error(self):
        assert issubclass(EnphaseBatteryConnectionError, EnphaseBatteryApiError)

    def test_rate_limit_error_is_api_error(self):
        assert issubclass(EnphaseBatteryRateLimitError, EnphaseBatteryApiError)


# ===========================================================================
# __init__
# ===========================================================================


class TestInit:
    """Test constructor."""

    def test_init_with_all_params(self, session):
        api = EnphaseBatteryAPI(session, "u", "p", site_id=1, user_id=2)
        assert api._username == "u"
        assert api._password == "p"
        assert api._site_id == 1
        assert api._user_id == 2
        assert api._session is session
        assert api._session_token is None
        assert api._is_authenticated is False

    def test_init_defaults(self, session):
        api = EnphaseBatteryAPI(session, "u", "p")
        assert api._site_id is None
        assert api._user_id is None


# ===========================================================================
# _get_headers
# ===========================================================================


class TestGetHeaders:
    """Test _get_headers."""

    def test_headers_without_cookies(self, api):
        headers = api._get_headers()
        assert "User-Agent" in headers
        assert headers["Accept"] == "application/json"
        assert "e-auth-token" not in headers
        assert "X-XSRF-Token" not in headers

    def test_headers_with_session_cookie(self, api, session):
        _set_session_cookie(session, "_enlighten_4_session", "session-abc")
        headers = api._get_headers()
        assert headers["e-auth-token"] == "session-abc"

    def test_headers_with_xsrf_cookie(self, api, session):
        _set_session_cookie(session, "BP-XSRF-Token", "xsrf-xyz")
        headers = api._get_headers()
        assert headers["X-XSRF-Token"] == "xsrf-xyz"

    def test_headers_with_both_cookies(self, api, session):
        _set_session_cookie(session, "_enlighten_4_session", "sess123")
        _set_session_cookie(session, "BP-XSRF-Token", "xsrf456")
        headers = api._get_headers()
        assert headers["e-auth-token"] == "sess123"
        assert headers["X-XSRF-Token"] == "xsrf456"


# ===========================================================================
# _request_with_reauth
# ===========================================================================


class TestRequestWithReauth:
    """Test _request_with_reauth method."""

    async def test_success_json(self, api):
        """Successful request returning JSON."""
        url = f"{API_BASE_URL}/test"
        with aioresponses() as m:
            m.get(url, payload={"key": "value"})
            result = await api._request_with_reauth("GET", url)
        assert result == {"key": "value"}

    async def test_success_no_json(self, api):
        """Successful request with return_json=False."""
        url = f"{API_BASE_URL}/test"
        with aioresponses() as m:
            m.put(url, status=200)
            result = await api._request_with_reauth("PUT", url, return_json=False)
        assert result is None

    async def test_custom_headers_preserved(self, api):
        """When headers are explicitly provided, they are kept."""
        url = f"{API_BASE_URL}/test"
        with aioresponses() as m:
            m.get(url, payload={"ok": True})
            result = await api._request_with_reauth("GET", url, headers={"X-Custom": "yes"})
        assert result == {"ok": True}

    async def test_custom_timeout_preserved(self, api):
        """When timeout is explicitly provided, it is kept."""
        url = f"{API_BASE_URL}/test"
        with aioresponses() as m:
            m.get(url, payload={"ok": True})
            result = await api._request_with_reauth("GET", url, timeout=ClientTimeout(total=5))
        assert result == {"ok": True}

    async def test_401_reauth_success(self, api):
        """401 triggers re-login then retries the request."""
        url = f"{API_BASE_URL}/test"
        with aioresponses() as m:
            m.get(url, status=401)
            m.post(LOGIN_URL, payload={"status": "success"})
            m.get(url, payload={"result": "ok"})
            result = await api._request_with_reauth("GET", url)
        assert result == {"result": "ok"}
        assert api._is_authenticated is True

    async def test_401_reauth_login_fails(self, api):
        """401 then re-login also fails raises EnphaseBatteryAuthError."""
        url = f"{API_BASE_URL}/test"
        with aioresponses() as m:
            m.get(url, status=401)
            m.post(LOGIN_URL, status=401)
            with pytest.raises(EnphaseBatteryAuthError, match="Re-authentication failed"):
                await api._request_with_reauth("GET", url)

    async def test_401_reauth_retry_still_401(self, api):
        """401 -> re-login ok -> retry still 401 raises auth error."""
        url = f"{API_BASE_URL}/test"
        with aioresponses() as m:
            m.get(url, status=401)
            m.post(LOGIN_URL, payload={"status": "success"})
            m.get(url, status=401)
            with pytest.raises(EnphaseBatteryAuthError, match="Authentication failed after re-login"):
                await api._request_with_reauth("GET", url)

    async def test_401_reauth_retry_returns_none_when_no_json(self, api):
        """401 re-auth retry with return_json=False returns None."""
        url = f"{API_BASE_URL}/test"
        with aioresponses() as m:
            m.get(url, status=401)
            m.post(LOGIN_URL, payload={"status": "success"})
            m.get(url, status=200)
            result = await api._request_with_reauth("GET", url, return_json=False)
        assert result is None

    @patch("custom_components.enphase_battery.api.cloud_client.asyncio.sleep", new_callable=AsyncMock)
    async def test_429_rate_limit_retry_then_success(self, mock_sleep, api):
        """429 retried after Retry-After header, then success."""
        url = f"{API_BASE_URL}/test"
        with aioresponses() as m:
            m.get(url, status=429, headers={"Retry-After": "5"})
            m.get(url, payload={"ok": True})
            result = await api._request_with_reauth("GET", url)
        assert result == {"ok": True}
        mock_sleep.assert_called_once_with(5)

    @patch("custom_components.enphase_battery.api.cloud_client.asyncio.sleep", new_callable=AsyncMock)
    async def test_429_rate_limit_exhausted(self, mock_sleep, api):
        """429 on every attempt raises EnphaseBatteryRateLimitError."""
        url = f"{API_BASE_URL}/test"
        with aioresponses() as m:
            for _ in range(MAX_RETRIES):
                m.get(url, status=429, headers={"Retry-After": "30"})
            with pytest.raises(EnphaseBatteryRateLimitError, match="Rate limit exceeded"):
                await api._request_with_reauth("GET", url)

    @patch("custom_components.enphase_battery.api.cloud_client.asyncio.sleep", new_callable=AsyncMock)
    async def test_429_default_retry_after(self, mock_sleep, api):
        """429 without Retry-After header uses default 60s."""
        url = f"{API_BASE_URL}/test"
        with aioresponses() as m:
            m.get(url, status=429)
            m.get(url, payload={"ok": True})
            await api._request_with_reauth("GET", url)
        mock_sleep.assert_called_once_with(60)

    @patch("custom_components.enphase_battery.api.cloud_client.asyncio.sleep", new_callable=AsyncMock)
    async def test_429_retry_after_capped_at_120(self, mock_sleep, api):
        """429 with very large Retry-After is capped at 120s."""
        url = f"{API_BASE_URL}/test"
        with aioresponses() as m:
            m.get(url, status=429, headers={"Retry-After": "999"})
            m.get(url, payload={"ok": True})
            await api._request_with_reauth("GET", url)
        mock_sleep.assert_called_once_with(120)

    @patch("custom_components.enphase_battery.api.cloud_client.asyncio.sleep", new_callable=AsyncMock)
    async def test_500_retryable_then_success(self, mock_sleep, api):
        """500 is retried with backoff, then succeeds."""
        url = f"{API_BASE_URL}/test"
        with aioresponses() as m:
            m.get(url, status=500)
            m.get(url, payload={"recovered": True})
            result = await api._request_with_reauth("GET", url)
        assert result == {"recovered": True}
        mock_sleep.assert_called_once_with(1)

    @patch("custom_components.enphase_battery.api.cloud_client.asyncio.sleep", new_callable=AsyncMock)
    async def test_retryable_exhausted_raises_connection_error(self, mock_sleep, api):
        """Retryable status on every attempt eventually raises EnphaseBatteryConnectionError.

        Note: raise_for_status() raises ClientResponseError which is a ClientError,
        so it gets caught by the ClientError retry handler.
        """
        url = f"{API_BASE_URL}/test"
        with aioresponses() as m:
            for _ in range(MAX_RETRIES):
                m.get(url, status=502)
            with pytest.raises(EnphaseBatteryConnectionError, match="Request failed after"):
                await api._request_with_reauth("GET", url)

    @patch("custom_components.enphase_battery.api.cloud_client.asyncio.sleep", new_callable=AsyncMock)
    async def test_503_retryable(self, mock_sleep, api):
        """503 is in RETRYABLE_STATUS_CODES."""
        url = f"{API_BASE_URL}/test"
        with aioresponses() as m:
            m.get(url, status=503)
            m.get(url, payload={"ok": True})
            result = await api._request_with_reauth("GET", url)
        assert result == {"ok": True}

    @patch("custom_components.enphase_battery.api.cloud_client.asyncio.sleep", new_callable=AsyncMock)
    async def test_504_retryable(self, mock_sleep, api):
        """504 is in RETRYABLE_STATUS_CODES."""
        url = f"{API_BASE_URL}/test"
        with aioresponses() as m:
            m.get(url, status=504)
            m.get(url, payload={"ok": True})
            result = await api._request_with_reauth("GET", url)
        assert result == {"ok": True}

    @patch("custom_components.enphase_battery.api.cloud_client.asyncio.sleep", new_callable=AsyncMock)
    async def test_connection_error_retry_then_success(self, mock_sleep, api):
        """Connection error is retried then succeeds."""
        url = f"{API_BASE_URL}/test"
        with aioresponses() as m:
            m.get(url, exception=aiohttp.ClientConnectionError("refused"))
            m.get(url, payload={"ok": True})
            result = await api._request_with_reauth("GET", url)
        assert result == {"ok": True}

    @patch("custom_components.enphase_battery.api.cloud_client.asyncio.sleep", new_callable=AsyncMock)
    async def test_connection_error_exhausted(self, mock_sleep, api):
        """Connection error on every attempt raises EnphaseBatteryConnectionError."""
        url = f"{API_BASE_URL}/test"
        with aioresponses() as m:
            for _ in range(MAX_RETRIES):
                m.get(url, exception=aiohttp.ClientConnectionError("refused"))
            with pytest.raises(EnphaseBatteryConnectionError, match="Request failed after"):
                await api._request_with_reauth("GET", url)

    @patch("custom_components.enphase_battery.api.cloud_client.asyncio.sleep", new_callable=AsyncMock)
    async def test_non_retryable_status_raises_connection_error(self, mock_sleep, api):
        """Non-retryable error (e.g. 403) raises_for_status -> ClientError -> retried -> ConnectionError.

        Because raise_for_status() produces ClientResponseError which is a ClientError,
        it gets caught by the retry handler and eventually raises EnphaseBatteryConnectionError.
        """
        url = f"{API_BASE_URL}/test"
        with aioresponses() as m:
            for _ in range(MAX_RETRIES):
                m.get(url, status=403)
            with pytest.raises(EnphaseBatteryConnectionError, match="Request failed after"):
                await api._request_with_reauth("GET", url)


# ===========================================================================
# _login
# ===========================================================================


class TestLogin:
    """Test _login method."""

    async def test_login_success_status(self, api):
        with aioresponses() as m:
            m.post(LOGIN_URL, payload={"status": "success"})
            assert await api._login() is True

    async def test_login_success_message(self, api):
        with aioresponses() as m:
            m.post(LOGIN_URL, payload={"message": "success"})
            assert await api._login() is True

    async def test_login_success_user_data(self, api):
        with aioresponses() as m:
            m.post(LOGIN_URL, payload={"user": {"default_system_id": 12345}})
            assert await api._login() is True

    async def test_login_success_200_no_special_keys(self, api):
        with aioresponses() as m:
            m.post(LOGIN_URL, payload={"something": "else"})
            assert await api._login() is True

    async def test_login_success_user_not_dict(self, api):
        with aioresponses() as m:
            m.post(LOGIN_URL, payload={"user": "some_string"})
            assert await api._login() is True

    async def test_login_401(self, api):
        with aioresponses() as m:
            m.post(LOGIN_URL, status=401)
            with pytest.raises(EnphaseBatteryAuthError, match="Invalid credentials"):
                await api._login()

    async def test_login_other_status(self, api):
        with aioresponses() as m:
            m.post(LOGIN_URL, status=500)
            assert await api._login() is False

    async def test_login_connection_error(self, api):
        with aioresponses() as m:
            m.post(LOGIN_URL, exception=aiohttp.ClientConnectionError("no route"))
            with pytest.raises(EnphaseBatteryConnectionError, match="Login connection error"):
                await api._login()


# ===========================================================================
# authenticate
# ===========================================================================


class TestAuthenticate:
    """Test authenticate method."""

    async def test_authenticate_with_provided_ids(self, api):
        """Both site_id and user_id provided: skip auto-detect."""
        with aioresponses() as m:
            m.post(LOGIN_URL, payload={"status": "success"})
            result = await api.authenticate()
        assert result is True
        assert api._is_authenticated is True

    async def test_authenticate_auto_detect_ids(self, api_no_ids):
        """Auto-detect site_id and user_id."""
        with aioresponses() as m:
            m.post(LOGIN_URL, payload={"status": "success"})
            m.get(SEARCH_SITES_PAT, payload=[{"system_id": 111, "user_id": 222}])
            result = await api_no_ids.authenticate()
        assert result is True
        assert api_no_ids._site_id == 111
        assert api_no_ids._user_id == 222

    async def test_authenticate_login_fails(self, api):
        """Login failure raises auth error."""
        with aioresponses() as m:
            m.post(LOGIN_URL, status=401)
            with pytest.raises(EnphaseBatteryAuthError):
                await api.authenticate()
        assert api._is_authenticated is False

    async def test_authenticate_login_returns_false(self, api):
        """Login returns False raises auth error."""
        with aioresponses() as m:
            m.post(LOGIN_URL, status=500)
            with pytest.raises(EnphaseBatteryAuthError, match="Login failed"):
                await api.authenticate()

    async def test_authenticate_connection_error(self, api_no_ids):
        """aiohttp.ClientError during login raises EnphaseBatteryConnectionError.

        Note: EnphaseBatteryConnectionError is a subclass of EnphaseBatteryApiError,
        so the except block for generic Exception catches it and wraps it.
        """
        with aioresponses() as m:
            m.post(LOGIN_URL, exception=aiohttp.ClientConnectionError("down"))
            with pytest.raises(EnphaseBatteryApiError):
                await api_no_ids.authenticate()

    async def test_authenticate_unexpected_error(self, api):
        """Unexpected error raises EnphaseBatteryApiError."""
        with aioresponses() as m:
            m.post(LOGIN_URL, exception=RuntimeError("boom"))
            with pytest.raises(EnphaseBatteryApiError, match="Authentication failed"):
                await api.authenticate()

    async def test_authenticate_auto_detect_site_only_then_user_from_settings(self, api_no_ids):
        """Auto-detect finds site_id but not user_id, falls back to _get_user_id_from_battery_settings."""
        with (
            patch.object(api_no_ids, "_login", return_value=True),
            patch.object(api_no_ids, "_get_user_sites", return_value=(99999, 0)),
            patch.object(api_no_ids, "_get_user_id_from_battery_settings", return_value=55555),
        ):
            result = await api_no_ids.authenticate()
        assert result is True
        assert api_no_ids._site_id == 99999
        assert api_no_ids._user_id == 55555

    async def test_authenticate_auto_detect_fails_no_site_id(self, api_no_ids):
        """Auto-detect completely fails raises auth error about site_id."""
        with (
            patch.object(api_no_ids, "_login", return_value=True),
            patch.object(
                api_no_ids,
                "_get_user_sites",
                side_effect=EnphaseBatteryAuthError("Could not determine site_id"),
            ),
            pytest.raises(EnphaseBatteryAuthError, match="Could not auto-detect site_id"),
        ):
            await api_no_ids.authenticate()

    async def test_authenticate_auto_detect_site_no_user_warns(self, api_no_ids):
        """Auto-detect finds site_id but not user_id from any source (warning logged)."""
        with (
            patch.object(api_no_ids, "_login", return_value=True),
            patch.object(api_no_ids, "_get_user_sites", return_value=(88888, 0)),
            patch.object(api_no_ids, "_get_user_id_from_battery_settings", return_value=None),
        ):
            result = await api_no_ids.authenticate()
        assert result is True
        assert api_no_ids._site_id == 88888
        assert api_no_ids._user_id is None  # 0 is falsy so not assigned

    async def test_authenticate_only_site_id_provided(self, session):
        """Only site_id provided, user_id auto-detected."""
        api = EnphaseBatteryAPI(session, "u", "p", site_id=12345)
        with (
            patch.object(api, "_login", return_value=True),
            patch.object(api, "_get_user_sites", return_value=(12345, 999)),
        ):
            result = await api.authenticate()
        assert result is True
        assert api._user_id == 999

    async def test_authenticate_only_user_id_provided(self, session):
        """Only user_id provided, site_id auto-detected."""
        api = EnphaseBatteryAPI(session, "u", "p", user_id=999)
        with (
            patch.object(api, "_login", return_value=True),
            patch.object(api, "_get_user_sites", return_value=(555, 999)),
        ):
            result = await api.authenticate()
        assert result is True
        assert api._site_id == 555

    async def test_authenticate_auto_detect_user_id_already_set(self, session):
        """site_id provided, user_id from _get_user_sites is not used if already set."""
        api = EnphaseBatteryAPI(session, "u", "p", site_id=123, user_id=456)
        with aioresponses() as m:
            m.post(LOGIN_URL, payload={"status": "success"})
            result = await api.authenticate()
        assert result is True
        assert api._user_id == 456

    async def test_authenticate_client_error_during_auto_detect(self, api_no_ids):
        """aiohttp.ClientError from _get_user_sites is caught and wrapped.

        This covers the `except aiohttp.ClientError` branch in authenticate() (line 257).
        """
        with (
            patch.object(api_no_ids, "_login", return_value=True),
            patch.object(
                api_no_ids,
                "_get_user_sites",
                side_effect=aiohttp.ClientConnectionError("raw client error"),
            ),
            pytest.raises(EnphaseBatteryConnectionError, match="Connection error"),
        ):
            await api_no_ids.authenticate()


# ===========================================================================
# _get_user_id_from_battery_settings
# ===========================================================================


class TestGetUserIdFromBatterySettings:
    """Test _get_user_id_from_battery_settings method."""

    TODAY_PAT = _url_pattern("/pv/systems/12345/today")
    APPDATA_PAT = _url_pattern("/app-api/12345/data.json")

    async def test_no_site_id(self, api_no_ids):
        assert await api_no_ids._get_user_id_from_battery_settings() is None

    async def test_user_id_in_top_level(self, api):
        with aioresponses() as m:
            m.get(self.TODAY_PAT, payload={"user_id": 42})
            assert await api._get_user_id_from_battery_settings() == 42

    async def test_user_id_in_nested_dict(self, api):
        with aioresponses() as m:
            m.get(self.TODAY_PAT, payload={"data": {"info": {"user_id": 555}}})
            assert await api._get_user_id_from_battery_settings() == 555

    async def test_user_id_in_nested_list(self, api):
        with aioresponses() as m:
            m.get(self.TODAY_PAT, payload={"items": [{"user_id": 777}]})
            assert await api._get_user_id_from_battery_settings() == 777

    async def test_user_id_from_second_endpoint(self, api):
        with aioresponses() as m:
            m.get(self.TODAY_PAT, payload={"no_user": True})
            m.get(self.APPDATA_PAT, payload={"user_id": 888})
            assert await api._get_user_id_from_battery_settings() == 888

    async def test_user_id_not_found(self, api):
        with aioresponses() as m:
            m.get(self.TODAY_PAT, payload={"no_user": True})
            m.get(self.APPDATA_PAT, payload={"also_no": True})
            assert await api._get_user_id_from_battery_settings() is None

    async def test_exception_on_endpoints(self, api):
        with aioresponses() as m:
            m.get(self.TODAY_PAT, exception=aiohttp.ClientConnectionError("err"))
            m.get(self.APPDATA_PAT, exception=aiohttp.ClientConnectionError("err"))
            assert await api._get_user_id_from_battery_settings() is None

    async def test_non_200_status(self, api):
        with aioresponses() as m:
            m.get(self.TODAY_PAT, status=500)
            m.get(self.APPDATA_PAT, status=404)
            assert await api._get_user_id_from_battery_settings() is None

    async def test_deep_recursion_limited(self, api):
        """Recursion beyond depth 5 does not find user_id."""
        data = {"user_id": 999}
        for _ in range(7):
            data = {"nested": data}
        with aioresponses() as m:
            m.get(self.TODAY_PAT, payload=data)
            m.get(self.APPDATA_PAT, payload={})
            assert await api._get_user_id_from_battery_settings() is None


# ===========================================================================
# _get_user_sites
# ===========================================================================


class TestGetUserSites:
    """Test _get_user_sites method.

    Since _get_user_sites involves complex redirect handling and multiple
    fallback methods, we mock at the session level and use response.url
    simulation via patching where needed.
    """

    async def test_method1_list_response(self, api):
        """Method 1: search_sites returns a list."""
        with aioresponses() as m:
            m.get(SEARCH_SITES_PAT, payload=[{"system_id": 100, "user_id": 200}])
            site_id, user_id = await api._get_user_sites()
        assert site_id == 100
        assert user_id == 200

    async def test_method1_dict_with_systems_key(self, api):
        with aioresponses() as m:
            m.get(SEARCH_SITES_PAT, payload={"systems": [{"system_id": 300, "user_id": 400}]})
            site_id, user_id = await api._get_user_sites()
        assert site_id == 300
        assert user_id == 400

    async def test_method1_dict_with_sites_key(self, api):
        with aioresponses() as m:
            m.get(SEARCH_SITES_PAT, payload={"sites": [{"site_id": 301, "owner_id": 401}]})
            site_id, user_id = await api._get_user_sites()
        assert site_id == 301
        assert user_id == 401

    async def test_method1_dict_with_data_key(self, api):
        with aioresponses() as m:
            m.get(SEARCH_SITES_PAT, payload={"data": [{"id": 302, "user_id": 402}]})
            site_id, user_id = await api._get_user_sites()
        assert site_id == 302
        assert user_id == 402

    async def test_method1_dict_with_result_key(self, api):
        with aioresponses() as m:
            m.get(SEARCH_SITES_PAT, payload={"result": [{"system_id": 303, "user_id": 403}]})
            site_id, user_id = await api._get_user_sites()
        assert site_id == 303
        assert user_id == 403

    async def test_method1_dict_with_response_key(self, api):
        with aioresponses() as m:
            m.get(SEARCH_SITES_PAT, payload={"response": [{"system_id": 304, "user_id": 404}]})
            site_id, user_id = await api._get_user_sites()
        assert site_id == 304
        assert user_id == 404

    async def test_method1_empty_list_falls_through_to_method2(self, api):
        """Method 1 returns empty list; method 2 finds site_id+user_id via redirect."""
        with patch.object(api, "_get_user_sites", wraps=api._get_user_sites):
            # We need to mock at the session level for redirect URL to work
            # Simplest: mock the whole method and test the individual methods separately
            pass
        # Use a more targeted approach: mock session.get for the two calls
        mock_response_search = AsyncMock()
        mock_response_search.status = 200
        mock_response_search.json = AsyncMock(return_value=[])
        mock_response_search.__aenter__ = AsyncMock(return_value=mock_response_search)
        mock_response_search.__aexit__ = AsyncMock(return_value=False)

        mock_response_redirect = AsyncMock()
        mock_response_redirect.status = 200
        mock_response_redirect.url = URL(f"{API_BASE_URL}/web/77777?v=3.4.0")
        mock_response_redirect.__aenter__ = AsyncMock(return_value=mock_response_redirect)
        mock_response_redirect.__aexit__ = AsyncMock(return_value=False)

        mock_response_settings = AsyncMock()
        mock_response_settings.status = 200
        mock_response_settings.json = AsyncMock(return_value={"userId": 88888})
        mock_response_settings.__aenter__ = AsyncMock(return_value=mock_response_settings)
        mock_response_settings.__aexit__ = AsyncMock(return_value=False)

        call_count = 0
        original_get = api._session.get

        def fake_get(url, **kwargs):
            nonlocal call_count
            call_count += 1
            url_str = str(url)
            if "search_sites" in url_str:
                return mock_response_search
            if url_str == f"{API_BASE_URL}/pv/systems":
                return mock_response_redirect
            if "batterySettings" in url_str:
                return mock_response_settings
            # fallback
            return original_get(url, **kwargs)

        with patch.object(api._session, "get", side_effect=fake_get):
            site_id, user_id = await api._get_user_sites()
        assert site_id == 77777
        assert user_id == 88888

    async def test_method1_list_missing_user_id_falls_through(self, api):
        """Method 1 list has system_id but no user_id."""
        mock_search = AsyncMock()
        mock_search.status = 200
        mock_search.json = AsyncMock(return_value=[{"system_id": 100}])
        mock_search.__aenter__ = AsyncMock(return_value=mock_search)
        mock_search.__aexit__ = AsyncMock(return_value=False)

        mock_redirect = AsyncMock()
        mock_redirect.status = 200
        mock_redirect.url = URL(f"{API_BASE_URL}/web/12121?v=3")
        mock_redirect.__aenter__ = AsyncMock(return_value=mock_redirect)
        mock_redirect.__aexit__ = AsyncMock(return_value=False)

        mock_settings = AsyncMock()
        mock_settings.status = 200
        mock_settings.json = AsyncMock(return_value={"userId": 34343})
        mock_settings.__aenter__ = AsyncMock(return_value=mock_settings)
        mock_settings.__aexit__ = AsyncMock(return_value=False)

        def fake_get(url, **kwargs):
            url_str = str(url)
            if "search_sites" in url_str:
                return mock_search
            if url_str == f"{API_BASE_URL}/pv/systems":
                return mock_redirect
            if "batterySettings" in url_str:
                return mock_settings
            raise AssertionError(f"Unexpected GET to {url_str}")

        with patch.object(api._session, "get", side_effect=fake_get):
            site_id, user_id = await api._get_user_sites()
        assert site_id == 12121
        assert user_id == 34343

    async def test_method1_dict_systems_missing_ids(self, api):
        """Method 1 dict with systems but no usable IDs."""
        mock_search = AsyncMock()
        mock_search.status = 200
        mock_search.json = AsyncMock(return_value={"systems": [{"name": "my site"}]})
        mock_search.__aenter__ = AsyncMock(return_value=mock_search)
        mock_search.__aexit__ = AsyncMock(return_value=False)

        mock_redirect = AsyncMock()
        mock_redirect.status = 200
        mock_redirect.url = URL(f"{API_BASE_URL}/dashboard")  # No /web/digits match
        mock_redirect.__aenter__ = AsyncMock(return_value=mock_redirect)
        mock_redirect.__aexit__ = AsyncMock(return_value=False)

        def fake_get(url, **kwargs):
            url_str = str(url)
            if "search_sites" in url_str:
                return mock_search
            if url_str == f"{API_BASE_URL}/pv/systems":
                return mock_redirect
            raise AssertionError(f"Unexpected GET to {url_str}")

        with (
            patch.object(api._session, "get", side_effect=fake_get),
            pytest.raises(EnphaseBatteryAuthError, match="Could not determine site_id"),
        ):
            await api._get_user_sites()

    async def test_method1_dict_empty_systems_list(self, api):
        """Method 1 dict with empty systems list falls through."""
        mock_search = AsyncMock()
        mock_search.status = 200
        mock_search.json = AsyncMock(return_value={"systems": []})
        mock_search.__aenter__ = AsyncMock(return_value=mock_search)
        mock_search.__aexit__ = AsyncMock(return_value=False)

        def fake_get(url, **kwargs):
            url_str = str(url)
            if "search_sites" in url_str:
                return mock_search
            # Method 2 fails
            raise aiohttp.ClientConnectionError("fail")

        with (
            patch.object(api._session, "get", side_effect=fake_get),
            pytest.raises(EnphaseBatteryAuthError, match="Could not determine site_id"),
        ):
            await api._get_user_sites()

    async def test_method1_json_parse_error(self, api):
        """Method 1 JSON parse failure falls through."""
        mock_search = AsyncMock()
        mock_search.status = 200
        mock_search.json = AsyncMock(side_effect=ValueError("bad json"))
        mock_search.__aenter__ = AsyncMock(return_value=mock_search)
        mock_search.__aexit__ = AsyncMock(return_value=False)

        def fake_get(url, **kwargs):
            url_str = str(url)
            if "search_sites" in url_str:
                return mock_search
            raise aiohttp.ClientConnectionError("fail")

        with patch.object(api._session, "get", side_effect=fake_get), pytest.raises(EnphaseBatteryAuthError):
            await api._get_user_sites()

    async def test_method2_redirect_with_settings_userId(self, api):
        """Method 2: redirect gives site_id, batterySettings gives userId."""
        mock_search = AsyncMock()
        mock_search.status = 500  # Non-200 skips method 1
        mock_search.__aenter__ = AsyncMock(return_value=mock_search)
        mock_search.__aexit__ = AsyncMock(return_value=False)

        mock_redirect = AsyncMock()
        mock_redirect.status = 200
        mock_redirect.url = URL(f"{API_BASE_URL}/web/55555?v=3.4.0")
        mock_redirect.__aenter__ = AsyncMock(return_value=mock_redirect)
        mock_redirect.__aexit__ = AsyncMock(return_value=False)

        mock_settings = AsyncMock()
        mock_settings.status = 200
        mock_settings.json = AsyncMock(return_value={"userId": 66666})
        mock_settings.__aenter__ = AsyncMock(return_value=mock_settings)
        mock_settings.__aexit__ = AsyncMock(return_value=False)

        def fake_get(url, **kwargs):
            url_str = str(url)
            if "search_sites" in url_str:
                return mock_search
            if url_str == f"{API_BASE_URL}/pv/systems":
                return mock_redirect
            if "batterySettings" in url_str:
                return mock_settings
            raise AssertionError(f"Unexpected GET to {url_str}")

        with patch.object(api._session, "get", side_effect=fake_get):
            site_id, user_id = await api._get_user_sites()
        assert site_id == 55555
        assert user_id == 66666

    async def test_method2_redirect_with_user_id_key(self, api):
        """Method 2: batterySettings returns user_id key."""
        mock_search = AsyncMock()
        mock_search.status = 500
        mock_search.__aenter__ = AsyncMock(return_value=mock_search)
        mock_search.__aexit__ = AsyncMock(return_value=False)

        mock_redirect = AsyncMock()
        mock_redirect.status = 200
        mock_redirect.url = URL(f"{API_BASE_URL}/web/55555")
        mock_redirect.__aenter__ = AsyncMock(return_value=mock_redirect)
        mock_redirect.__aexit__ = AsyncMock(return_value=False)

        mock_settings = AsyncMock()
        mock_settings.status = 200
        mock_settings.json = AsyncMock(return_value={"user_id": 77777})
        mock_settings.__aenter__ = AsyncMock(return_value=mock_settings)
        mock_settings.__aexit__ = AsyncMock(return_value=False)

        def fake_get(url, **kwargs):
            url_str = str(url)
            if "search_sites" in url_str:
                return mock_search
            if url_str == f"{API_BASE_URL}/pv/systems":
                return mock_redirect
            if "batterySettings" in url_str:
                return mock_settings
            raise AssertionError(f"Unexpected GET to {url_str}")

        with patch.object(api._session, "get", side_effect=fake_get):
            site_id, user_id = await api._get_user_sites()
        assert site_id == 55555
        assert user_id == 77777

    async def test_method2_summary_endpoint(self, api):
        """Method 2: batterySettings empty, summary returns user_id."""
        mock_search = AsyncMock()
        mock_search.status = 500
        mock_search.__aenter__ = AsyncMock(return_value=mock_search)
        mock_search.__aexit__ = AsyncMock(return_value=False)

        mock_redirect = AsyncMock()
        mock_redirect.status = 200
        mock_redirect.url = URL(f"{API_BASE_URL}/web/55555")
        mock_redirect.__aenter__ = AsyncMock(return_value=mock_redirect)
        mock_redirect.__aexit__ = AsyncMock(return_value=False)

        mock_settings = AsyncMock()
        mock_settings.status = 200
        mock_settings.json = AsyncMock(return_value={})  # No user_id
        mock_settings.__aenter__ = AsyncMock(return_value=mock_settings)
        mock_settings.__aexit__ = AsyncMock(return_value=False)

        mock_summary = AsyncMock()
        mock_summary.status = 200
        mock_summary.json = AsyncMock(return_value={"user_id": 88888})
        mock_summary.__aenter__ = AsyncMock(return_value=mock_summary)
        mock_summary.__aexit__ = AsyncMock(return_value=False)

        def fake_get(url, **kwargs):
            url_str = str(url)
            if "search_sites" in url_str:
                return mock_search
            if url_str == f"{API_BASE_URL}/pv/systems":
                return mock_redirect
            if "batterySettings" in url_str:
                return mock_settings
            if "summary" in url_str:
                return mock_summary
            raise AssertionError(f"Unexpected GET to {url_str}")

        with patch.object(api._session, "get", side_effect=fake_get):
            site_id, user_id = await api._get_user_sites()
        assert site_id == 55555
        assert user_id == 88888

    async def test_method2_summary_with_owner_id(self, api):
        """Method 2: summary returns owner_id."""
        mock_search = AsyncMock()
        mock_search.status = 500
        mock_search.__aenter__ = AsyncMock(return_value=mock_search)
        mock_search.__aexit__ = AsyncMock(return_value=False)

        mock_redirect = AsyncMock()
        mock_redirect.status = 200
        mock_redirect.url = URL(f"{API_BASE_URL}/web/55555")
        mock_redirect.__aenter__ = AsyncMock(return_value=mock_redirect)
        mock_redirect.__aexit__ = AsyncMock(return_value=False)

        mock_settings = AsyncMock()
        mock_settings.status = 200
        mock_settings.json = AsyncMock(return_value={})
        mock_settings.__aenter__ = AsyncMock(return_value=mock_settings)
        mock_settings.__aexit__ = AsyncMock(return_value=False)

        mock_summary = AsyncMock()
        mock_summary.status = 200
        mock_summary.json = AsyncMock(return_value={"owner_id": 99999})
        mock_summary.__aenter__ = AsyncMock(return_value=mock_summary)
        mock_summary.__aexit__ = AsyncMock(return_value=False)

        def fake_get(url, **kwargs):
            url_str = str(url)
            if "search_sites" in url_str:
                return mock_search
            if url_str == f"{API_BASE_URL}/pv/systems":
                return mock_redirect
            if "batterySettings" in url_str:
                return mock_settings
            if "summary" in url_str:
                return mock_summary
            raise AssertionError(f"Unexpected GET to {url_str}")

        with patch.object(api._session, "get", side_effect=fake_get):
            site_id, user_id = await api._get_user_sites()
        assert site_id == 55555
        assert user_id == 99999

    async def test_method2_no_redirect_match(self, api):
        """Method 2: URL does not match /web/digits."""
        mock_search = AsyncMock()
        mock_search.status = 500
        mock_search.__aenter__ = AsyncMock(return_value=mock_search)
        mock_search.__aexit__ = AsyncMock(return_value=False)

        mock_redirect = AsyncMock()
        mock_redirect.status = 200
        mock_redirect.url = URL(f"{API_BASE_URL}/dashboard")
        mock_redirect.__aenter__ = AsyncMock(return_value=mock_redirect)
        mock_redirect.__aexit__ = AsyncMock(return_value=False)

        def fake_get(url, **kwargs):
            url_str = str(url)
            if "search_sites" in url_str:
                return mock_search
            if url_str == f"{API_BASE_URL}/pv/systems":
                return mock_redirect
            raise aiohttp.ClientConnectionError("fail")

        with (
            patch.object(api._session, "get", side_effect=fake_get),
            pytest.raises(EnphaseBatteryAuthError, match="Could not determine site_id"),
        ):
            await api._get_user_sites()

    async def test_method2_settings_and_summary_exceptions(self, api):
        """Method 2: both settings and summary fail."""
        mock_search = AsyncMock()
        mock_search.status = 500
        mock_search.__aenter__ = AsyncMock(return_value=mock_search)
        mock_search.__aexit__ = AsyncMock(return_value=False)

        mock_redirect = AsyncMock()
        mock_redirect.status = 200
        mock_redirect.url = URL(f"{API_BASE_URL}/web/55555")
        mock_redirect.__aenter__ = AsyncMock(return_value=mock_redirect)
        mock_redirect.__aexit__ = AsyncMock(return_value=False)

        mock_settings = AsyncMock()
        mock_settings.__aenter__ = AsyncMock(side_effect=aiohttp.ClientConnectionError("err"))
        mock_settings.__aexit__ = AsyncMock(return_value=False)

        mock_summary = AsyncMock()
        mock_summary.__aenter__ = AsyncMock(side_effect=aiohttp.ClientConnectionError("err"))
        mock_summary.__aexit__ = AsyncMock(return_value=False)

        def fake_get(url, **kwargs):
            url_str = str(url)
            if "search_sites" in url_str:
                return mock_search
            if url_str == f"{API_BASE_URL}/pv/systems":
                return mock_redirect
            if "batterySettings" in url_str:
                return mock_settings
            if "summary" in url_str:
                return mock_summary
            raise AssertionError(f"Unexpected GET to {url_str}")

        with patch.object(api._session, "get", side_effect=fake_get):
            # site_id found but not user_id -> returns (site_id, 0)
            site_id, user_id = await api._get_user_sites()
        assert site_id == 55555
        assert user_id == 0

    async def test_method3_jwt_cookie(self, api, session):
        """Method 3: extract user_id from JWT token cookie."""
        jwt_payload = {"data": {"user_id": 44444}}
        jwt_token = _make_jwt(jwt_payload)
        _set_session_cookie(session, "enlighten_manager_token_production", jwt_token)

        mock_search = AsyncMock()
        mock_search.status = 500
        mock_search.__aenter__ = AsyncMock(return_value=mock_search)
        mock_search.__aexit__ = AsyncMock(return_value=False)

        mock_redirect = AsyncMock()
        mock_redirect.status = 200
        mock_redirect.url = URL(f"{API_BASE_URL}/web/55555")
        mock_redirect.__aenter__ = AsyncMock(return_value=mock_redirect)
        mock_redirect.__aexit__ = AsyncMock(return_value=False)

        mock_settings = AsyncMock()
        mock_settings.status = 200
        mock_settings.json = AsyncMock(return_value={})
        mock_settings.__aenter__ = AsyncMock(return_value=mock_settings)
        mock_settings.__aexit__ = AsyncMock(return_value=False)

        mock_summary = AsyncMock()
        mock_summary.status = 200
        mock_summary.json = AsyncMock(return_value={})
        mock_summary.__aenter__ = AsyncMock(return_value=mock_summary)
        mock_summary.__aexit__ = AsyncMock(return_value=False)

        def fake_get(url, **kwargs):
            url_str = str(url)
            if "search_sites" in url_str:
                return mock_search
            if url_str == f"{API_BASE_URL}/pv/systems":
                return mock_redirect
            if "batterySettings" in url_str:
                return mock_settings
            if "summary" in url_str:
                return mock_summary
            raise AssertionError(f"Unexpected GET to {url_str}")

        with patch.object(api._session, "get", side_effect=fake_get):
            site_id, user_id = await api._get_user_sites()
        assert site_id == 55555
        assert user_id == 44444

    async def test_method3_jwt_cookie_no_user_id(self, api, session):
        """JWT cookie present but no user_id field."""
        jwt_payload = {"data": {"email": "test@test.com"}}
        jwt_token = _make_jwt(jwt_payload)
        _set_session_cookie(session, "enlighten_manager_token_production", jwt_token)

        mock_search = AsyncMock()
        mock_search.status = 500
        mock_search.__aenter__ = AsyncMock(return_value=mock_search)
        mock_search.__aexit__ = AsyncMock(return_value=False)

        mock_redirect = AsyncMock()
        mock_redirect.status = 200
        mock_redirect.url = URL(f"{API_BASE_URL}/web/55555")
        mock_redirect.__aenter__ = AsyncMock(return_value=mock_redirect)
        mock_redirect.__aexit__ = AsyncMock(return_value=False)

        mock_settings = AsyncMock()
        mock_settings.status = 200
        mock_settings.json = AsyncMock(return_value={})
        mock_settings.__aenter__ = AsyncMock(return_value=mock_settings)
        mock_settings.__aexit__ = AsyncMock(return_value=False)

        mock_summary = AsyncMock()
        mock_summary.status = 200
        mock_summary.json = AsyncMock(return_value={})
        mock_summary.__aenter__ = AsyncMock(return_value=mock_summary)
        mock_summary.__aexit__ = AsyncMock(return_value=False)

        def fake_get(url, **kwargs):
            url_str = str(url)
            if "search_sites" in url_str:
                return mock_search
            if url_str == f"{API_BASE_URL}/pv/systems":
                return mock_redirect
            if "batterySettings" in url_str:
                return mock_settings
            if "summary" in url_str:
                return mock_summary
            raise AssertionError(f"Unexpected GET to {url_str}")

        with patch.object(api._session, "get", side_effect=fake_get):
            site_id, user_id = await api._get_user_sites()
        assert site_id == 55555
        assert user_id == 0

    async def test_all_methods_fail(self, api):
        """All three methods fail raises auth error."""

        def fake_get(url, **kwargs):
            raise aiohttp.ClientConnectionError("fail")

        with (
            patch.object(api._session, "get", side_effect=fake_get),
            pytest.raises(EnphaseBatteryAuthError, match="Could not determine site_id"),
        ):
            await api._get_user_sites()

    async def test_only_user_id_found_raises(self, api, session):
        """Only user_id found (no site_id) raises auth error."""
        jwt_payload = {"data": {"user_id": 99999}}
        jwt_token = _make_jwt(jwt_payload)
        _set_session_cookie(session, "enlighten_manager_token_production", jwt_token)

        mock_search = AsyncMock()
        mock_search.status = 500
        mock_search.__aenter__ = AsyncMock(return_value=mock_search)
        mock_search.__aexit__ = AsyncMock(return_value=False)

        mock_redirect = AsyncMock()
        mock_redirect.status = 200
        mock_redirect.url = URL(f"{API_BASE_URL}/unknown")  # No /web/digits
        mock_redirect.__aenter__ = AsyncMock(return_value=mock_redirect)
        mock_redirect.__aexit__ = AsyncMock(return_value=False)

        def fake_get(url, **kwargs):
            url_str = str(url)
            if "search_sites" in url_str:
                return mock_search
            if url_str == f"{API_BASE_URL}/pv/systems":
                return mock_redirect
            raise aiohttp.ClientConnectionError("fail")

        with (
            patch.object(api._session, "get", side_effect=fake_get),
            pytest.raises(EnphaseBatteryAuthError, match="Could not determine site_id"),
        ):
            await api._get_user_sites()

    async def test_method2_settings_not_dict(self, api):
        """Method 2: settings returns non-dict."""
        mock_search = AsyncMock()
        mock_search.status = 500
        mock_search.__aenter__ = AsyncMock(return_value=mock_search)
        mock_search.__aexit__ = AsyncMock(return_value=False)

        mock_redirect = AsyncMock()
        mock_redirect.status = 200
        mock_redirect.url = URL(f"{API_BASE_URL}/web/55555")
        mock_redirect.__aenter__ = AsyncMock(return_value=mock_redirect)
        mock_redirect.__aexit__ = AsyncMock(return_value=False)

        mock_settings = AsyncMock()
        mock_settings.status = 200
        mock_settings.json = AsyncMock(return_value=[{"not": "dict"}])
        mock_settings.__aenter__ = AsyncMock(return_value=mock_settings)
        mock_settings.__aexit__ = AsyncMock(return_value=False)

        mock_summary = AsyncMock()
        mock_summary.status = 200
        mock_summary.json = AsyncMock(return_value=[{"also": "not dict"}])
        mock_summary.__aenter__ = AsyncMock(return_value=mock_summary)
        mock_summary.__aexit__ = AsyncMock(return_value=False)

        def fake_get(url, **kwargs):
            url_str = str(url)
            if "search_sites" in url_str:
                return mock_search
            if url_str == f"{API_BASE_URL}/pv/systems":
                return mock_redirect
            if "batterySettings" in url_str:
                return mock_settings
            if "summary" in url_str:
                return mock_summary
            raise AssertionError(f"Unexpected GET to {url_str}")

        with patch.object(api._session, "get", side_effect=fake_get):
            site_id, user_id = await api._get_user_sites()
        assert site_id == 55555
        assert user_id == 0

    async def test_method2_settings_non_200(self, api):
        """Method 2: batterySettings returns non-200, falls to summary."""
        mock_search = AsyncMock()
        mock_search.status = 500
        mock_search.__aenter__ = AsyncMock(return_value=mock_search)
        mock_search.__aexit__ = AsyncMock(return_value=False)

        mock_redirect = AsyncMock()
        mock_redirect.status = 200
        mock_redirect.url = URL(f"{API_BASE_URL}/web/55555")
        mock_redirect.__aenter__ = AsyncMock(return_value=mock_redirect)
        mock_redirect.__aexit__ = AsyncMock(return_value=False)

        mock_settings = AsyncMock()
        mock_settings.status = 500
        mock_settings.__aenter__ = AsyncMock(return_value=mock_settings)
        mock_settings.__aexit__ = AsyncMock(return_value=False)

        mock_summary = AsyncMock()
        mock_summary.status = 200
        mock_summary.json = AsyncMock(return_value={"userId": 11111})
        mock_summary.__aenter__ = AsyncMock(return_value=mock_summary)
        mock_summary.__aexit__ = AsyncMock(return_value=False)

        def fake_get(url, **kwargs):
            url_str = str(url)
            if "search_sites" in url_str:
                return mock_search
            if url_str == f"{API_BASE_URL}/pv/systems":
                return mock_redirect
            if "batterySettings" in url_str:
                return mock_settings
            if "summary" in url_str:
                return mock_summary
            raise AssertionError(f"Unexpected GET to {url_str}")

        with patch.object(api._session, "get", side_effect=fake_get):
            site_id, user_id = await api._get_user_sites()
        assert site_id == 55555
        assert user_id == 11111

    async def test_method1_non_200(self, api):
        """Method 1: non-200 status falls through."""

        def fake_get(url, **kwargs):
            raise aiohttp.ClientConnectionError("fail")

        with patch.object(api._session, "get", side_effect=fake_get), pytest.raises(EnphaseBatteryAuthError):
            await api._get_user_sites()

    async def test_method3_invalid_jwt(self, api, session):
        """Method 3: invalid JWT is silently skipped."""
        _set_session_cookie(session, "enlighten_manager_token_production", "not.avalid.jwt")

        mock_search = AsyncMock()
        mock_search.status = 500
        mock_search.__aenter__ = AsyncMock(return_value=mock_search)
        mock_search.__aexit__ = AsyncMock(return_value=False)

        mock_redirect = AsyncMock()
        mock_redirect.status = 200
        mock_redirect.url = URL(f"{API_BASE_URL}/web/55555")
        mock_redirect.__aenter__ = AsyncMock(return_value=mock_redirect)
        mock_redirect.__aexit__ = AsyncMock(return_value=False)

        mock_settings = AsyncMock()
        mock_settings.status = 200
        mock_settings.json = AsyncMock(return_value={})
        mock_settings.__aenter__ = AsyncMock(return_value=mock_settings)
        mock_settings.__aexit__ = AsyncMock(return_value=False)

        mock_summary = AsyncMock()
        mock_summary.status = 200
        mock_summary.json = AsyncMock(return_value={})
        mock_summary.__aenter__ = AsyncMock(return_value=mock_summary)
        mock_summary.__aexit__ = AsyncMock(return_value=False)

        def fake_get(url, **kwargs):
            url_str = str(url)
            if "search_sites" in url_str:
                return mock_search
            if url_str == f"{API_BASE_URL}/pv/systems":
                return mock_redirect
            if "batterySettings" in url_str:
                return mock_settings
            if "summary" in url_str:
                return mock_summary
            raise AssertionError(f"Unexpected GET to {url_str}")

        with patch.object(api._session, "get", side_effect=fake_get):
            site_id, user_id = await api._get_user_sites()
        assert site_id == 55555
        assert user_id == 0

    async def test_method3_jwt_single_part(self, api, session):
        """Method 3: JWT with <2 parts is silently skipped."""
        _set_session_cookie(session, "enlighten_manager_token_production", "singlepart")

        mock_search = AsyncMock()
        mock_search.status = 500
        mock_search.__aenter__ = AsyncMock(return_value=mock_search)
        mock_search.__aexit__ = AsyncMock(return_value=False)

        mock_redirect = AsyncMock()
        mock_redirect.status = 200
        mock_redirect.url = URL(f"{API_BASE_URL}/web/55555")
        mock_redirect.__aenter__ = AsyncMock(return_value=mock_redirect)
        mock_redirect.__aexit__ = AsyncMock(return_value=False)

        mock_settings = AsyncMock()
        mock_settings.status = 200
        mock_settings.json = AsyncMock(return_value={})
        mock_settings.__aenter__ = AsyncMock(return_value=mock_settings)
        mock_settings.__aexit__ = AsyncMock(return_value=False)

        mock_summary = AsyncMock()
        mock_summary.status = 200
        mock_summary.json = AsyncMock(return_value={})
        mock_summary.__aenter__ = AsyncMock(return_value=mock_summary)
        mock_summary.__aexit__ = AsyncMock(return_value=False)

        def fake_get(url, **kwargs):
            url_str = str(url)
            if "search_sites" in url_str:
                return mock_search
            if url_str == f"{API_BASE_URL}/pv/systems":
                return mock_redirect
            if "batterySettings" in url_str:
                return mock_settings
            if "summary" in url_str:
                return mock_summary
            raise AssertionError(f"Unexpected GET to {url_str}")

        with patch.object(api._session, "get", side_effect=fake_get):
            site_id, user_id = await api._get_user_sites()
        assert site_id == 55555
        assert user_id == 0

    async def test_method3_cookie_jar_exception(self, api):
        """Method 3: outer exception on cookie_jar.filter_cookies() (lines 566-567).

        We need filter_cookies to work during _get_headers() calls (methods 1 & 2)
        but fail during the method 3 cookie reading code. We use a counter to only
        fail on the call that happens after all method 2 HTTP calls are done.
        """
        mock_search = AsyncMock()
        mock_search.status = 500
        mock_search.__aenter__ = AsyncMock(return_value=mock_search)
        mock_search.__aexit__ = AsyncMock(return_value=False)

        mock_redirect = AsyncMock()
        mock_redirect.status = 200
        mock_redirect.url = URL(f"{API_BASE_URL}/web/55555")
        mock_redirect.__aenter__ = AsyncMock(return_value=mock_redirect)
        mock_redirect.__aexit__ = AsyncMock(return_value=False)

        mock_settings = AsyncMock()
        mock_settings.status = 200
        mock_settings.json = AsyncMock(return_value={})
        mock_settings.__aenter__ = AsyncMock(return_value=mock_settings)
        mock_settings.__aexit__ = AsyncMock(return_value=False)

        mock_summary = AsyncMock()
        mock_summary.status = 200
        mock_summary.json = AsyncMock(return_value={})
        mock_summary.__aenter__ = AsyncMock(return_value=mock_summary)
        mock_summary.__aexit__ = AsyncMock(return_value=False)

        def fake_get(url, **kwargs):
            url_str = str(url)
            if "search_sites" in url_str:
                return mock_search
            if url_str == f"{API_BASE_URL}/pv/systems":
                return mock_redirect
            if "batterySettings" in url_str:
                return mock_settings
            if "summary" in url_str:
                return mock_summary
            raise AssertionError(f"Unexpected GET to {url_str}")

        original_filter = api._session.cookie_jar.filter_cookies
        call_count = 0

        def failing_filter_cookies(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            # _get_headers() is called for each HTTP request in methods 1 & 2 (4 calls)
            # Method 3 makes the 5th call to filter_cookies on line 541
            if call_count >= 5:
                raise RuntimeError("cookie jar error")
            return original_filter(*args, **kwargs)

        with (
            patch.object(api._session, "get", side_effect=fake_get),
            patch.object(
                api._session.cookie_jar,
                "filter_cookies",
                side_effect=failing_filter_cookies,
            ),
        ):
            site_id, user_id = await api._get_user_sites()
        assert site_id == 55555
        assert user_id == 0


# ===========================================================================
# get_battery_data
# ===========================================================================


class TestGetBatteryData:
    """Test get_battery_data method."""

    async def test_no_site_id(self, api_no_ids):
        with pytest.raises(EnphaseBatteryAuthError, match="site_id missing"):
            await api_no_ids.get_battery_data()

    async def test_success(self, api):
        """Successful battery data fetch."""
        today_data = {
            "battery_details": {
                "aggregate_soc": 75,
                "last_24h_consumption": 5000,
                "estimated_time": 180,
            },
            "batteryConfig": {},
            "stats": [
                {
                    "soc": [50, 60, 75],
                    "charge": [100, None, 200],
                    "discharge": [None, 300, None],
                    "totals": {"charge": 5000, "discharge": 3000},
                }
            ],
            "siteStatus": "normal",
        }
        settings_data = {
            "profile": "self-consumption",
            "batteryBackupPercentage": 30,
            "chargeFromGrid": True,
            "dtgControl": {"enabled": True},
            "rbdControl": {"enabled": False},
            "powerMatchControl": {"enabled": True},
            "veryLowSoc": 10,
        }

        with aioresponses() as m:
            m.get(TODAY_12345_PAT, payload=today_data)
            m.get(SETTINGS_12345_PAT, payload={"data": settings_data})
            result = await api.get_battery_data()

        assert result["soc"] == 75
        assert result["mode"] == "self-consumption"
        assert result["backup_reserve"] == 30
        assert result["charge_from_grid"] is True
        assert result["discharge_to_grid"] is True
        assert result["reserve_battery_discharge"] is False
        assert result["power_match"] is True
        assert result["very_low_soc"] == 10
        assert result["status"] == "normal"
        assert result["energy_charged_today"] == 5.0
        assert result["energy_discharged_today"] == 3.0
        assert result["charge_power"] == 200
        assert result["discharge_power"] == 300

    async def test_success_without_settings(self, api):
        """Battery data when get_battery_settings fails (returns None)."""
        today_data = {
            "battery_details": {"aggregate_soc": 50},
            "batteryConfig": {
                "usage": "cost_savings",
                "battery_backup_percentage": 20,
                "charge_from_grid": False,
                "very_low_soc": 5,
            },
            "stats": [{"soc": [], "charge": [], "discharge": [], "totals": {"charge": 0, "discharge": 0}}],
            "siteStatus": "normal",
        }

        with aioresponses() as m:
            m.get(TODAY_12345_PAT, payload=today_data)
            m.get(SETTINGS_12345_PAT, exception=aiohttp.ClientConnectionError("err"))
            result = await api.get_battery_data()

        assert result["soc"] == 50
        assert result["mode"] == "cost_savings"
        assert result["backup_reserve"] == 20
        assert result["charge_from_grid"] is False

    async def test_connection_error(self, api):
        """Connection error on today endpoint raises EnphaseBatteryConnectionError."""
        with aioresponses() as m:
            m.get(TODAY_12345_PAT, exception=aiohttp.ClientConnectionError("down"))
            m.get(SETTINGS_12345_PAT, payload={"data": {}})
            with pytest.raises(EnphaseBatteryConnectionError, match="Failed to get battery data"):
                await api.get_battery_data()


# ===========================================================================
# _parse_battery_data
# ===========================================================================


class TestParseBatteryData:
    """Test _parse_battery_data method."""

    def _minimal_data(self, **overrides):
        data = {
            "battery_details": {},
            "batteryConfig": {},
            "stats": [{"soc": [], "charge": [], "discharge": [], "totals": {"charge": 0, "discharge": 0}}],
            "siteStatus": "unknown",
        }
        data.update(overrides)
        return data

    def test_with_settings(self, api):
        data = self._minimal_data()
        settings = {
            "profile": "self-consumption",
            "batteryBackupPercentage": 30,
            "chargeFromGrid": True,
            "dtgControl": {"enabled": True},
            "rbdControl": {"enabled": True},
            "powerMatchControl": {"enabled": False},
            "veryLowSoc": 15,
        }
        result = api._parse_battery_data(data, settings)
        assert result["mode"] == "self-consumption"
        assert result["backup_reserve"] == 30
        assert result["charge_from_grid"] is True
        assert result["discharge_to_grid"] is True
        assert result["reserve_battery_discharge"] is True
        assert result["power_match"] is False
        assert result["very_low_soc"] == 15

    def test_without_settings(self, api):
        data = self._minimal_data(
            batteryConfig={
                "usage": "backup_only",
                "battery_backup_percentage": 50,
                "charge_from_grid": False,
                "very_low_soc": 10,
            }
        )
        result = api._parse_battery_data(data, None)
        assert result["mode"] == "backup_only"
        assert result["backup_reserve"] == 50
        assert result["charge_from_grid"] is False

    def test_dtg_control_not_dict(self, api):
        data = self._minimal_data()
        result = api._parse_battery_data(data, {"dtgControl": "some_string"})
        assert result["discharge_to_grid"] is False

    def test_rbd_control_not_dict(self, api):
        data = self._minimal_data()
        result = api._parse_battery_data(data, {"rbdControl": True})
        assert result["reserve_battery_discharge"] is False

    def test_power_match_control_not_dict(self, api):
        data = self._minimal_data()
        result = api._parse_battery_data(data, {"powerMatchControl": 42})
        assert result["power_match"] is False

    def test_missing_battery_details_uses_latest_soc(self, api):
        data = {
            "battery_details": {},
            "batteryConfig": {},
            "stats": [{"soc": [40, 50, 60], "charge": [], "discharge": [], "totals": {"charge": 0, "discharge": 0}}],
            "siteStatus": "normal",
        }
        result = api._parse_battery_data(data, None)
        assert result["soc"] == 60

    def test_aggregate_soc_preferred(self, api):
        data = {
            "battery_details": {"aggregate_soc": 80},
            "batteryConfig": {},
            "stats": [{"soc": [40, 50, 60], "charge": [], "discharge": [], "totals": {"charge": 0, "discharge": 0}}],
            "siteStatus": "normal",
        }
        result = api._parse_battery_data(data, None)
        assert result["soc"] == 80

    def test_empty_stats(self, api):
        data = {"battery_details": {}, "batteryConfig": {}, "stats": [{}], "siteStatus": "unknown"}
        result = api._parse_battery_data(data, None)
        assert result["soc"] is None
        assert result["power"] == 0
        assert result["charge_power"] == 0
        assert result["discharge_power"] == 0

    def test_consumption_and_backup_time(self, api):
        data = {
            "battery_details": {"last_24h_consumption": 12000, "estimated_time": 360},
            "batteryConfig": {},
            "stats": [{"soc": [], "charge": [], "discharge": [], "totals": {"charge": 0, "discharge": 0}}],
            "siteStatus": "normal",
        }
        result = api._parse_battery_data(data, None)
        assert result["consumption_24h"] == 12000
        assert result["estimated_backup_time"] == 360

    def test_last_update_present(self, api):
        data = self._minimal_data()
        result = api._parse_battery_data(data, None)
        assert "last_update" in result

    def test_mode_fallback_to_batteryConfig_usage(self, api):
        data = self._minimal_data(batteryConfig={"usage": "expert"})
        result = api._parse_battery_data(data, {})
        assert result["mode"] == "expert"

    def test_dtg_control_missing(self, api):
        result = api._parse_battery_data(self._minimal_data(), {})
        assert result["discharge_to_grid"] is False

    def test_rbd_control_missing(self, api):
        result = api._parse_battery_data(self._minimal_data(), {})
        assert result["reserve_battery_discharge"] is False

    def test_power_match_control_missing(self, api):
        result = api._parse_battery_data(self._minimal_data(), {})
        assert result["power_match"] is False


# ===========================================================================
# _get_latest_value
# ===========================================================================


class TestGetLatestValue:
    def test_with_values(self, api):
        assert api._get_latest_value([10, 20, 30]) == 30

    def test_with_trailing_nulls(self, api):
        assert api._get_latest_value([10, 20, None, None]) == 20

    def test_all_none(self, api):
        assert api._get_latest_value([None, None, None]) is None

    def test_empty_list(self, api):
        assert api._get_latest_value([]) is None

    def test_single_value(self, api):
        assert api._get_latest_value([42]) == 42

    def test_single_none(self, api):
        assert api._get_latest_value([None]) is None

    def test_zero_is_valid(self, api):
        assert api._get_latest_value([None, 0]) == 0

    def test_mixed_values(self, api):
        assert api._get_latest_value([None, 10, None, 20, None]) == 20


# ===========================================================================
# _calculate_battery_power
# ===========================================================================


class TestCalculateBatteryPower:
    def test_both_values(self, api):
        assert api._calculate_battery_power(100, 300) == 200

    def test_charge_only(self, api):
        assert api._calculate_battery_power(500, 0) == -500

    def test_discharge_only(self, api):
        assert api._calculate_battery_power(0, 700) == 700

    def test_charge_none(self, api):
        assert api._calculate_battery_power(None, 400) == 400

    def test_discharge_none(self, api):
        assert api._calculate_battery_power(300, None) == -300

    def test_both_none(self, api):
        assert api._calculate_battery_power(None, None) == 0

    def test_equal_values(self, api):
        assert api._calculate_battery_power(200, 200) == 0


# ===========================================================================
# get_battery_settings
# ===========================================================================


class TestGetBatterySettings:
    async def test_no_site_id(self, api_no_ids):
        with pytest.raises(EnphaseBatteryAuthError, match="Not authenticated"):
            await api_no_ids.get_battery_settings()

    async def test_no_user_id(self, api_site_only):
        with pytest.raises(EnphaseBatteryAuthError, match="Not authenticated"):
            await api_site_only.get_battery_settings()

    async def test_success(self, api):
        with aioresponses() as m:
            m.get(SETTINGS_12345_PAT, payload={"data": {"profile": "self-consumption"}})
            result = await api.get_battery_settings()
        assert result == {"profile": "self-consumption"}

    async def test_success_empty_data(self, api):
        with aioresponses() as m:
            m.get(SETTINGS_12345_PAT, payload={"other": "value"})
            result = await api.get_battery_settings()
        assert result == {}

    async def test_auth_error_propagated(self, api):
        with (
            patch.object(api, "_request_with_reauth", side_effect=EnphaseBatteryAuthError("auth fail")),
            pytest.raises(EnphaseBatteryAuthError),
        ):
            await api.get_battery_settings()

    async def test_connection_error_propagated(self, api):
        with (
            patch.object(api, "_request_with_reauth", side_effect=EnphaseBatteryConnectionError("conn fail")),
            pytest.raises(EnphaseBatteryConnectionError),
        ):
            await api.get_battery_settings()

    async def test_unexpected_error_wrapped(self, api):
        with (
            patch.object(api, "_request_with_reauth", side_effect=RuntimeError("boom")),
            pytest.raises(EnphaseBatteryConnectionError, match="Failed to get battery settings"),
        ):
            await api.get_battery_settings()


# ===========================================================================
# _update_battery_settings
# ===========================================================================


class TestUpdateBatterySettings:
    async def test_success(self, api):
        with aioresponses() as m:
            m.put(SETTINGS_12345_PAT, payload={"message": "success"})
            result = await api._update_battery_settings({"profile": "backup_only"})
        assert result is True

    async def test_failure_message(self, api):
        with aioresponses() as m:
            m.put(SETTINGS_12345_PAT, payload={"message": "error"})
            result = await api._update_battery_settings({"profile": "backup_only"})
        assert result is False

    async def test_result_none(self, api):
        with patch.object(api, "_request_with_reauth", return_value=None):
            result = await api._update_battery_settings({"profile": "backup_only"})
        assert result is False

    async def test_auth_error_propagated(self, api):
        with (
            patch.object(api, "_request_with_reauth", side_effect=EnphaseBatteryAuthError("auth")),
            pytest.raises(EnphaseBatteryAuthError),
        ):
            await api._update_battery_settings({})

    async def test_connection_error_propagated(self, api):
        with (
            patch.object(api, "_request_with_reauth", side_effect=EnphaseBatteryConnectionError("conn")),
            pytest.raises(EnphaseBatteryConnectionError),
        ):
            await api._update_battery_settings({})

    async def test_unexpected_error_wrapped(self, api):
        with (
            patch.object(api, "_request_with_reauth", side_effect=RuntimeError("boom")),
            pytest.raises(EnphaseBatteryConnectionError, match="Failed to update battery settings"),
        ):
            await api._update_battery_settings({})


# ===========================================================================
# get_battery_profile
# ===========================================================================


class TestGetBatteryProfile:
    async def test_no_ids(self, api_no_ids):
        with pytest.raises(EnphaseBatteryAuthError, match="Not authenticated"):
            await api_no_ids.get_battery_profile()

    async def test_no_user_id(self, api_site_only):
        with pytest.raises(EnphaseBatteryAuthError, match="Not authenticated"):
            await api_site_only.get_battery_profile()

    async def test_success(self, api):
        with aioresponses() as m:
            m.get(PROFILE_12345_PAT, payload={"data": {"name": "My Profile"}})
            result = await api.get_battery_profile()
        assert result == {"name": "My Profile"}

    async def test_connection_error(self, api):
        with aioresponses() as m:
            m.get(PROFILE_12345_PAT, exception=aiohttp.ClientConnectionError("err"))
            with pytest.raises(EnphaseBatteryConnectionError, match="Failed to get battery profile"):
                await api.get_battery_profile()


# ===========================================================================
# get_battery_schedules
# ===========================================================================


class TestGetBatterySchedules:
    async def test_no_site_id(self, api_no_ids):
        with pytest.raises(EnphaseBatteryAuthError, match="Not authenticated"):
            await api_no_ids.get_battery_schedules()

    async def test_success(self, api):
        with aioresponses() as m:
            m.get(SCHEDULES_12345_PAT, payload={"schedules": [{"id": 1}]})
            result = await api.get_battery_schedules()
        assert result == {"schedules": [{"id": 1}]}

    async def test_connection_error(self, api):
        with aioresponses() as m:
            m.get(SCHEDULES_12345_PAT, exception=aiohttp.ClientConnectionError("err"))
            with pytest.raises(EnphaseBatteryConnectionError, match="Failed to get schedules"):
                await api.get_battery_schedules()


# ===========================================================================
# set_battery_mode
# ===========================================================================


class TestSetBatteryMode:
    async def test_no_ids(self, api_no_ids):
        with pytest.raises(EnphaseBatteryAuthError, match="Not authenticated"):
            await api_no_ids.set_battery_mode("self-consumption")

    async def test_no_user_id(self, api_site_only):
        with pytest.raises(EnphaseBatteryAuthError, match="Not authenticated"):
            await api_site_only.set_battery_mode("self-consumption")

    async def test_success(self, api):
        with (
            patch.object(api, "get_battery_settings", return_value={"profile": "cost_savings", "other": "keep"}),
            patch.object(api, "_update_battery_settings", return_value=True) as mock_update,
        ):
            result = await api.set_battery_mode("self-consumption")
        assert result is True
        data_sent = mock_update.call_args[0][0]
        assert data_sent["profile"] == "self-consumption"
        assert data_sent["other"] == "keep"

    async def test_auth_error(self, api):
        with (
            patch.object(api, "get_battery_settings", side_effect=EnphaseBatteryAuthError("err")),
            pytest.raises(EnphaseBatteryAuthError),
        ):
            await api.set_battery_mode("backup_only")


# ===========================================================================
# set_backup_reserve
# ===========================================================================


class TestSetBackupReserve:
    async def test_no_ids(self, api_no_ids):
        with pytest.raises(EnphaseBatteryAuthError):
            await api_no_ids.set_backup_reserve(50)

    async def test_success(self, api):
        with (
            patch.object(api, "get_battery_settings", return_value={"batteryBackupPercentage": 30}),
            patch.object(api, "_update_battery_settings", return_value=True) as mock_update,
        ):
            result = await api.set_backup_reserve(50)
        assert result is True
        assert mock_update.call_args[0][0]["batteryBackupPercentage"] == 50


# ===========================================================================
# set_very_low_soc
# ===========================================================================


class TestSetVeryLowSoc:
    async def test_no_ids(self, api_no_ids):
        with pytest.raises(EnphaseBatteryAuthError):
            await api_no_ids.set_very_low_soc(10)

    async def test_success(self, api):
        with (
            patch.object(api, "get_battery_settings", return_value={"veryLowSoc": 5}),
            patch.object(api, "_update_battery_settings", return_value=True) as mock_update,
        ):
            result = await api.set_very_low_soc(15)
        assert result is True
        assert mock_update.call_args[0][0]["veryLowSoc"] == 15


# ===========================================================================
# set_charge_from_grid
# ===========================================================================


class TestSetChargeFromGrid:
    async def test_no_ids(self, api_no_ids):
        with pytest.raises(EnphaseBatteryAuthError):
            await api_no_ids.set_charge_from_grid(True)

    async def test_enable(self, api):
        with (
            patch.object(api, "get_battery_settings", return_value={"chargeFromGrid": False}),
            patch.object(api, "_update_battery_settings", return_value=True) as mock_update,
        ):
            result = await api.set_charge_from_grid(True)
        assert result is True
        assert mock_update.call_args[0][0]["chargeFromGrid"] is True

    async def test_disable(self, api):
        with (
            patch.object(api, "get_battery_settings", return_value={"chargeFromGrid": True}),
            patch.object(api, "_update_battery_settings", return_value=True) as mock_update,
        ):
            result = await api.set_charge_from_grid(False)
        assert result is True
        assert mock_update.call_args[0][0]["chargeFromGrid"] is False


# ===========================================================================
# set_limit_discharge
# ===========================================================================


class TestSetLimitDischarge:
    async def test_no_ids(self, api_no_ids):
        with pytest.raises(EnphaseBatteryAuthError):
            await api_no_ids.set_limit_discharge(True)

    async def test_enable_with_existing_dtg_control(self, api):
        existing = {"dtgControl": {"show": True, "enabled": False, "locked": False}}
        with (
            patch.object(api, "get_battery_settings", return_value=existing),
            patch.object(api, "_update_battery_settings", return_value=True) as mock_update,
        ):
            result = await api.set_limit_discharge(True)
        assert result is True
        assert mock_update.call_args[0][0]["dtgControl"]["enabled"] is True

    async def test_enable_without_dtg_control(self, api):
        with (
            patch.object(api, "get_battery_settings", return_value={}),
            patch.object(api, "_update_battery_settings", return_value=True) as mock_update,
        ):
            result = await api.set_limit_discharge(True)
        assert result is True
        data_sent = mock_update.call_args[0][0]
        assert data_sent["dtgControl"]["enabled"] is True
        assert data_sent["dtgControl"]["show"] is True

    async def test_disable(self, api):
        existing = {"dtgControl": {"show": True, "enabled": True, "locked": False}}
        with (
            patch.object(api, "get_battery_settings", return_value=existing),
            patch.object(api, "_update_battery_settings", return_value=True) as mock_update,
        ):
            result = await api.set_limit_discharge(False)
        assert result is True
        assert mock_update.call_args[0][0]["dtgControl"]["enabled"] is False


# ===========================================================================
# set_reserve_battery_discharge
# ===========================================================================


class TestSetReserveBatteryDischarge:
    async def test_no_ids(self, api_no_ids):
        with pytest.raises(EnphaseBatteryAuthError):
            await api_no_ids.set_reserve_battery_discharge(True)

    async def test_enable_with_existing_rbd_control(self, api):
        existing = {"rbdControl": {"show": True, "enabled": False, "locked": False}}
        with (
            patch.object(api, "get_battery_settings", return_value=existing),
            patch.object(api, "_update_battery_settings", return_value=True) as mock_update,
        ):
            result = await api.set_reserve_battery_discharge(True)
        assert result is True
        assert mock_update.call_args[0][0]["rbdControl"]["enabled"] is True

    async def test_enable_without_rbd_control(self, api):
        with (
            patch.object(api, "get_battery_settings", return_value={}),
            patch.object(api, "_update_battery_settings", return_value=True) as mock_update,
        ):
            result = await api.set_reserve_battery_discharge(True)
        assert result is True
        data_sent = mock_update.call_args[0][0]
        assert data_sent["rbdControl"]["enabled"] is True
        assert data_sent["rbdControl"]["show"] is True

    async def test_disable(self, api):
        existing = {"rbdControl": {"show": True, "enabled": True, "locked": False}}
        with (
            patch.object(api, "get_battery_settings", return_value=existing),
            patch.object(api, "_update_battery_settings", return_value=True) as mock_update,
        ):
            result = await api.set_reserve_battery_discharge(False)
        assert result is True
        assert mock_update.call_args[0][0]["rbdControl"]["enabled"] is False


# ===========================================================================
# set_power_match
# ===========================================================================


class TestSetPowerMatch:
    async def test_no_ids(self, api_no_ids):
        with pytest.raises(EnphaseBatteryAuthError):
            await api_no_ids.set_power_match(True)

    async def test_enable_with_existing_power_match_control(self, api):
        existing = {"powerMatchControl": {"show": True, "enabled": False}}
        with (
            patch.object(api, "get_battery_settings", return_value=existing),
            patch.object(api, "_update_battery_settings", return_value=True) as mock_update,
        ):
            result = await api.set_power_match(True)
        assert result is True
        assert mock_update.call_args[0][0]["powerMatchControl"]["enabled"] is True

    async def test_enable_without_power_match_control(self, api):
        with (
            patch.object(api, "get_battery_settings", return_value={}),
            patch.object(api, "_update_battery_settings", return_value=True) as mock_update,
        ):
            result = await api.set_power_match(True)
        assert result is True
        data_sent = mock_update.call_args[0][0]
        assert data_sent["powerMatchControl"]["enabled"] is True
        assert data_sent["powerMatchControl"]["show"] is True

    async def test_disable(self, api):
        existing = {"powerMatchControl": {"show": True, "enabled": True}}
        with (
            patch.object(api, "get_battery_settings", return_value=existing),
            patch.object(api, "_update_battery_settings", return_value=True) as mock_update,
        ):
            result = await api.set_power_match(False)
        assert result is True
        assert mock_update.call_args[0][0]["powerMatchControl"]["enabled"] is False


# ===========================================================================
# Constants
# ===========================================================================


class TestConstants:
    def test_api_base_url(self):
        assert API_BASE_URL == "https://enlighten.enphaseenergy.com"

    def test_api_timeout(self):
        assert API_TIMEOUT == 30

    def test_api_timeout_discovery(self):
        assert API_TIMEOUT_DISCOVERY == 5

    def test_max_retries(self):
        assert MAX_RETRIES == 3

    def test_retryable_status_codes(self):
        assert {429, 500, 502, 503, 504} == RETRYABLE_STATUS_CODES
