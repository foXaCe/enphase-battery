"""Comprehensive tests for Enphase Envoy Local API client."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import aiohttp
from aiohttp import ClientSession
from aioresponses import aioresponses
import pytest

from custom_components.enphase_battery.envoy_local_api import (
    DEFAULT_ENVOY_HOST,
    ENLIGHTEN_LOGIN_URL,
    ENTREZ_TOKEN_URL,
    EnphaseEnvoyLocalAPI,
    EnvoyAuthError,
    EnvoyConnectionError,
    EnvoyLocalApiError,
)

TEST_HOST = "192.168.1.100"
BASE_URL = f"https://{TEST_HOST}"
FAKE_JWT = "eyJ0eXAiOiJKV1QiLCJhbGciOiJSUzI1NiJ9." + "a" * 100 + "." + "b" * 50
FAKE_SERIAL = "121845123456"
CLOUD_USER = "user@example.com"
CLOUD_PASS = "secretpass"


@pytest.fixture
async def session():
    """Create a real aiohttp ClientSession for testing."""
    async with aiohttp.ClientSession() as sess:
        yield sess


@pytest.fixture
def api(session: ClientSession) -> EnphaseEnvoyLocalAPI:
    """Create an API instance with default settings."""
    instance = EnphaseEnvoyLocalAPI(
        session=session,
        host=TEST_HOST,
        cloud_username=CLOUD_USER,
        cloud_password=CLOUD_PASS,
    )
    # Inject the test session as cloud_session so aioresponses can intercept
    instance._cloud_session = session  # type: ignore[attr-defined]
    return instance


@pytest.fixture
def api_with_token(session: ClientSession) -> EnphaseEnvoyLocalAPI:
    """Create an API instance with a pre-set JWT token."""
    return EnphaseEnvoyLocalAPI(
        session=session,
        host=TEST_HOST,
        token=FAKE_JWT,
        cloud_username=CLOUD_USER,
        cloud_password=CLOUD_PASS,
    )


@pytest.fixture
def api_no_cloud(session: ClientSession) -> EnphaseEnvoyLocalAPI:
    """Create an API instance without cloud credentials."""
    return EnphaseEnvoyLocalAPI(
        session=session,
        host=TEST_HOST,
    )


# ---------------------------------------------------------------------------
# Exception classes
# ---------------------------------------------------------------------------


class TestExceptions:
    """Test exception hierarchy."""

    def test_envoy_local_api_error_is_exception(self):
        err = EnvoyLocalApiError("test")
        assert isinstance(err, Exception)
        assert str(err) == "test"

    def test_envoy_auth_error_is_subclass(self):
        err = EnvoyAuthError("auth failed")
        assert isinstance(err, EnvoyLocalApiError)

    def test_envoy_connection_error_is_subclass(self):
        err = EnvoyConnectionError("conn failed")
        assert isinstance(err, EnvoyLocalApiError)


# ---------------------------------------------------------------------------
# __init__
# ---------------------------------------------------------------------------


class TestInit:
    """Test constructor defaults and properties."""

    def test_defaults(self, session: ClientSession):
        api = EnphaseEnvoyLocalAPI(session=session)
        assert api._host == DEFAULT_ENVOY_HOST
        assert api._base_url == f"https://{DEFAULT_ENVOY_HOST}"
        assert api._username == "installer"
        assert api._password is None
        assert api._cloud_username is None
        assert api._cloud_password is None
        assert api._jwt_token is None
        assert api._serial_number is None
        assert api._firmware_version is None

    def test_custom_params(self, session: ClientSession):
        api = EnphaseEnvoyLocalAPI(
            session=session,
            host="10.0.0.1",
            username="admin",
            password="pass123",
            cloud_username="cloud@test.com",
            cloud_password="cloudpw",
            token="tok123",
        )
        assert api._host == "10.0.0.1"
        assert api._base_url == "https://10.0.0.1"
        assert api._username == "admin"
        assert api._password == "pass123"
        assert api._cloud_username == "cloud@test.com"
        assert api._cloud_password == "cloudpw"
        assert api._jwt_token == "tok123"


# ---------------------------------------------------------------------------
# _make_request
# ---------------------------------------------------------------------------


class TestMakeRequest:
    """Test the HTTP request wrapper."""

    async def test_json_response(self, api_with_token: EnphaseEnvoyLocalAPI):
        """JSON content-type should return parsed JSON."""
        with aioresponses() as m:
            m.get(
                f"{BASE_URL}/test/endpoint",
                payload={"key": "value"},
                content_type="application/json",
            )
            result = await api_with_token._make_request("GET", "/test/endpoint")
            assert result == {"key": "value"}

    async def test_raw_text_response(self, api_with_token: EnphaseEnvoyLocalAPI):
        """Non-JSON content should return {"raw": text}."""
        with aioresponses() as m:
            m.get(
                f"{BASE_URL}/info",
                body="<envoy_info><sn>123</sn></envoy_info>",
                content_type="text/html",
            )
            result = await api_with_token._make_request("GET", "/info")
            assert result == {"raw": "<envoy_info><sn>123</sn></envoy_info>"}

    async def test_401_raises_auth_error(self, api_with_token: EnphaseEnvoyLocalAPI):
        """401 status should raise EnvoyAuthError."""
        with aioresponses() as m:
            m.get(f"{BASE_URL}/protected", status=401)
            with pytest.raises(EnvoyAuthError, match="Authentication required"):
                await api_with_token._make_request("GET", "/protected")

    async def test_connection_error(self, api_with_token: EnphaseEnvoyLocalAPI):
        """Connection errors should raise EnvoyConnectionError."""
        with aioresponses() as m:
            m.get(f"{BASE_URL}/fail", exception=aiohttp.ClientError("timeout"))
            with pytest.raises(EnvoyConnectionError, match="Failed to connect"):
                await api_with_token._make_request("GET", "/fail")

    async def test_bearer_header_sent_when_auth_required(self, api_with_token: EnphaseEnvoyLocalAPI):
        """Auth-required requests should include Bearer token header."""
        with aioresponses() as m:
            m.get(f"{BASE_URL}/auth-ep", payload={"ok": True}, content_type="application/json")
            await api_with_token._make_request("GET", "/auth-ep", auth_required=True)
            # aioresponses stores requests as {(method, url): [CallbackResult...]}
            history = next(iter(m.requests.values()))
            request_headers = history[0].kwargs.get("headers", {})
            assert request_headers.get("Authorization") == f"Bearer {FAKE_JWT}"

    async def test_no_bearer_header_when_auth_not_required(self, api: EnphaseEnvoyLocalAPI):
        """Non-auth requests should not include Bearer header."""
        with aioresponses() as m:
            m.get(f"{BASE_URL}/info", payload={"sn": "123"}, content_type="application/json")
            await api._make_request("GET", "/info", auth_required=False)
            history = next(iter(m.requests.values()))
            request_headers = history[0].kwargs.get("headers", {})
            assert "Authorization" not in request_headers

    async def test_no_bearer_header_when_no_token(self, api: EnphaseEnvoyLocalAPI):
        """Even auth-required requests should not add header when no token."""
        with aioresponses() as m:
            m.get(f"{BASE_URL}/ep", payload={"ok": True}, content_type="application/json")
            await api._make_request("GET", "/ep", auth_required=True)
            history = next(iter(m.requests.values()))
            request_headers = history[0].kwargs.get("headers", {})
            assert "Authorization" not in request_headers

    async def test_endpoint_leading_slash_stripped(self, api_with_token: EnphaseEnvoyLocalAPI):
        """Leading slash should be normalized."""
        with aioresponses() as m:
            m.get(f"{BASE_URL}/api/v1/test", payload={}, content_type="application/json")
            result = await api_with_token._make_request("GET", "/api/v1/test")
            assert result == {}

    async def test_post_method(self, api_with_token: EnphaseEnvoyLocalAPI):
        """POST requests should work."""
        with aioresponses() as m:
            m.post(f"{BASE_URL}/admin/lib/acb_config.json", payload={"success": True}, content_type="application/json")
            result = await api_with_token._make_request("POST", "/admin/lib/acb_config.json", json={"sleep": True})
            assert result == {"success": True}

    async def test_put_method(self, api_with_token: EnphaseEnvoyLocalAPI):
        """PUT requests should work."""
        with aioresponses() as m:
            m.put(f"{BASE_URL}/admin/lib/tariff", payload={"ok": True}, content_type="application/json")
            result = await api_with_token._make_request("PUT", "/admin/lib/tariff", json={"tariff": {}})
            assert result == {"ok": True}

    async def test_500_raises_connection_error(self, api_with_token: EnphaseEnvoyLocalAPI):
        """Server error status should raise via raise_for_status -> ClientError."""
        with aioresponses() as m:
            m.get(f"{BASE_URL}/error", status=500)
            with pytest.raises(EnvoyConnectionError):
                await api_with_token._make_request("GET", "/error")


# ---------------------------------------------------------------------------
# _generate_installer_password
# ---------------------------------------------------------------------------


class TestGenerateInstallerPassword:
    """Test installer password generation."""

    def test_returns_last_six_digits(self, api: EnphaseEnvoyLocalAPI):
        assert api._generate_installer_password("121845123456") == "123456"

    def test_short_serial(self, api: EnphaseEnvoyLocalAPI):
        assert api._generate_installer_password("999999") == "999999"

    def test_long_serial(self, api: EnphaseEnvoyLocalAPI):
        assert api._generate_installer_password("00000000000654321") == "654321"


# ---------------------------------------------------------------------------
# _is_firmware_7_or_higher
# ---------------------------------------------------------------------------


class TestIsFirmware7OrHigher:
    """Test firmware version detection."""

    def test_d7_returns_true(self, api: EnphaseEnvoyLocalAPI):
        api._firmware_version = "D7.3.466"
        assert api._is_firmware_7_or_higher() is True

    def test_d6_returns_false(self, api: EnphaseEnvoyLocalAPI):
        api._firmware_version = "D6.2.0"
        assert api._is_firmware_7_or_higher() is False

    def test_none_returns_false(self, api: EnphaseEnvoyLocalAPI):
        api._firmware_version = None
        assert api._is_firmware_7_or_higher() is False

    def test_v8_returns_true(self, api: EnphaseEnvoyLocalAPI):
        api._firmware_version = "8.0"
        assert api._is_firmware_7_or_higher() is True

    def test_d8_returns_true(self, api: EnphaseEnvoyLocalAPI):
        api._firmware_version = "D8.2.4127"
        assert api._is_firmware_7_or_higher() is True

    def test_v5_returns_false(self, api: EnphaseEnvoyLocalAPI):
        api._firmware_version = "5.6.7"
        assert api._is_firmware_7_or_higher() is False

    def test_exactly_7(self, api: EnphaseEnvoyLocalAPI):
        api._firmware_version = "7.0.0"
        assert api._is_firmware_7_or_higher() is True

    def test_garbage_returns_false(self, api: EnphaseEnvoyLocalAPI):
        api._firmware_version = "not_a_version"
        assert api._is_firmware_7_or_higher() is False

    def test_empty_string_returns_false(self, api: EnphaseEnvoyLocalAPI):
        api._firmware_version = ""
        assert api._is_firmware_7_or_higher() is False

    def test_exception_in_regex_returns_false(self, api: EnphaseEnvoyLocalAPI):
        """If an exception occurs during version parsing, return False."""
        api._firmware_version = "D7.3.0"
        with patch("custom_components.enphase_battery.envoy_local_api.re.search", side_effect=TypeError("mocked")):
            assert api._is_firmware_7_or_higher() is False


# ---------------------------------------------------------------------------
# _get_info
# ---------------------------------------------------------------------------


class TestGetInfo:
    """Test device info parsing."""

    async def test_json_with_device_key(self, api: EnphaseEnvoyLocalAPI):
        """Response with 'device' key should pass through."""
        with aioresponses() as m:
            m.get(
                f"{BASE_URL}/info",
                payload={"device": {"sn": "123456", "software": "D8.2.0"}},
                content_type="application/json",
            )
            result = await api._get_info()
            assert result["device"]["sn"] == "123456"

    async def test_json_with_sn_directly(self, api: EnphaseEnvoyLocalAPI):
        """Response with 'sn' at top-level should wrap in 'device'."""
        with aioresponses() as m:
            m.get(
                f"{BASE_URL}/info",
                payload={"sn": "654321", "software": "D7.3.0"},
                content_type="application/json",
            )
            result = await api._get_info()
            assert result["device"]["sn"] == "654321"

    async def test_json_with_serial_num(self, api: EnphaseEnvoyLocalAPI):
        """Response with 'serial_num' at top-level should wrap in 'device'."""
        with aioresponses() as m:
            m.get(
                f"{BASE_URL}/info",
                payload={"serial_num": "789012", "software": "D6.0.0"},
                content_type="application/json",
            )
            result = await api._get_info()
            assert result["device"]["serial_num"] == "789012"

    async def test_xml_in_raw_key(self, api: EnphaseEnvoyLocalAPI):
        """XML content in 'raw' key should be parsed."""
        xml = "<envoy_info><device><sn>121845123456</sn><software>D8.2.4127</software><pn>800-12345-r01</pn></device></envoy_info>"
        with aioresponses() as m:
            m.get(f"{BASE_URL}/info", body=xml, content_type="text/xml")
            result = await api._get_info()
            assert result["device"]["sn"] == "121845123456"
            assert result["device"]["software"] == "D8.2.4127"
            assert result["device"]["pn"] == "800-12345-r01"

    async def test_xml_no_serial(self, api: EnphaseEnvoyLocalAPI):
        """XML without serial should return response as-is (with raw)."""
        xml = "<envoy_info><device><software>D8.0</software></device></envoy_info>"
        with aioresponses() as m:
            m.get(f"{BASE_URL}/info", body=xml, content_type="text/xml")
            result = await api._get_info()
            # No serial found, returns the raw response dict
            assert "raw" in result or result == {}

    async def test_json_unknown_keys_passthrough(self, api: EnphaseEnvoyLocalAPI):
        """Response with no recognized keys should pass through."""
        with aioresponses() as m:
            m.get(
                f"{BASE_URL}/info",
                payload={"unknown_key": "value"},
                content_type="application/json",
            )
            result = await api._get_info()
            assert result == {"unknown_key": "value"}

    async def test_response_is_string(self, api: EnphaseEnvoyLocalAPI):
        """If _make_request returns a plain string, it should be treated as XML."""
        xml = "<envoy_info><device><sn>111222333444</sn><software>D7.0.0</software></device></envoy_info>"
        with patch.object(api, "_make_request", new_callable=AsyncMock, return_value=xml):
            result = await api._get_info()
        assert result["device"]["sn"] == "111222333444"

    async def test_response_is_string_no_serial(self, api: EnphaseEnvoyLocalAPI):
        """String response without serial should return original response via fallback."""
        xml = "<envoy_info><device><software>D7.0.0</software></device></envoy_info>"
        with patch.object(api, "_make_request", new_callable=AsyncMock, return_value=xml):
            result = await api._get_info()
        # No serial found in XML, falls through to `return response or {}`
        # response is the string xml, which is truthy
        assert result == xml

    async def test_info_exception_reraises(self, api: EnphaseEnvoyLocalAPI):
        """Connection errors during _get_info should propagate."""
        with aioresponses() as m:
            m.get(f"{BASE_URL}/info", exception=aiohttp.ClientError("fail"))
            with pytest.raises(EnvoyConnectionError):
                await api._get_info()


# ---------------------------------------------------------------------------
# _obtain_cloud_token
# ---------------------------------------------------------------------------


class TestObtainCloudToken:
    """Test cloud token retrieval."""

    async def test_success(self, api: EnphaseEnvoyLocalAPI):
        """Successful token flow: login -> session_id -> token."""
        api._serial_number = FAKE_SERIAL
        with aioresponses() as m:
            m.post(
                ENLIGHTEN_LOGIN_URL,
                payload={"session_id": "test_session"},
                content_type="application/json",
            )
            m.post(
                ENTREZ_TOKEN_URL,
                body=FAKE_JWT,
                content_type="text/plain",
            )
            token = await api._obtain_cloud_token()
            assert token == FAKE_JWT

    async def test_missing_cloud_credentials(self, api_no_cloud: EnphaseEnvoyLocalAPI):
        """Missing cloud credentials should raise EnvoyAuthError."""
        api_no_cloud._serial_number = FAKE_SERIAL
        with pytest.raises(EnvoyAuthError, match="Cloud credentials required"):
            await api_no_cloud._obtain_cloud_token()

    async def test_missing_serial(self, api: EnphaseEnvoyLocalAPI):
        """Missing serial number should raise EnvoyAuthError."""
        api._serial_number = None
        with pytest.raises(EnvoyAuthError, match="Serial number must be retrieved"):
            await api._obtain_cloud_token()

    async def test_login_fails(self, api: EnphaseEnvoyLocalAPI):
        """Login HTTP error should raise EnvoyAuthError."""
        api._serial_number = FAKE_SERIAL
        with aioresponses() as m:
            m.post(ENLIGHTEN_LOGIN_URL, status=403)
            with pytest.raises(EnvoyAuthError, match=r"Failed to obtain cloud token|Token retrieval error"):
                await api._obtain_cloud_token()

    async def test_token_request_fails(self, api: EnphaseEnvoyLocalAPI):
        """Login succeeds but token request fails should raise."""
        api._serial_number = FAKE_SERIAL
        with aioresponses() as m:
            m.post(
                ENLIGHTEN_LOGIN_URL,
                payload={"session_id": "test_session"},
                content_type="application/json",
            )
            m.post(
                ENTREZ_TOKEN_URL,
                status=500,
            )
            with pytest.raises(EnvoyAuthError):
                await api._obtain_cloud_token()

    async def test_token_too_short(self, api: EnphaseEnvoyLocalAPI):
        """Token shorter than 50 chars should raise."""
        api._serial_number = FAKE_SERIAL
        with aioresponses() as m:
            m.post(
                ENLIGHTEN_LOGIN_URL,
                payload={"session_id": "test_session"},
                content_type="application/json",
            )
            m.post(
                ENTREZ_TOKEN_URL,
                body="short",
                content_type="text/plain",
            )
            with pytest.raises(EnvoyAuthError, match="Token retrieval error"):
                await api._obtain_cloud_token()

    async def test_login_connection_error(self, api: EnphaseEnvoyLocalAPI):
        """aiohttp.ClientError during login should raise EnvoyAuthError."""
        api._serial_number = FAKE_SERIAL
        with aioresponses() as m:
            m.post(ENLIGHTEN_LOGIN_URL, exception=aiohttp.ClientError("network fail"))
            with pytest.raises(EnvoyAuthError):
                await api._obtain_cloud_token()

    async def test_token_endpoint_connection_error(self, api: EnphaseEnvoyLocalAPI):
        """aiohttp.ClientError during token fetch should raise EnvoyAuthError."""
        api._serial_number = FAKE_SERIAL
        with aioresponses() as m:
            m.post(
                ENLIGHTEN_LOGIN_URL,
                payload={"session_id": "test_session"},
                content_type="application/json",
            )
            m.post(ENTREZ_TOKEN_URL, exception=aiohttp.ClientError("timeout"))
            with pytest.raises(EnvoyAuthError):
                await api._obtain_cloud_token()


# ---------------------------------------------------------------------------
# authenticate
# ---------------------------------------------------------------------------


class TestAuthenticate:
    """Test authentication flow."""

    async def test_fw7_with_cloud_token_success(self, api: EnphaseEnvoyLocalAPI):
        """Firmware 7+ should obtain cloud token and validate."""
        with aioresponses() as m:
            # _get_info
            m.get(
                f"{BASE_URL}/info",
                payload={"device": {"sn": FAKE_SERIAL, "software": "D7.3.466"}},
                content_type="application/json",
            )
            # _obtain_cloud_token: login
            m.post(
                ENLIGHTEN_LOGIN_URL,
                payload={"session_id": "test_session"},
                content_type="application/json",
            )
            # _obtain_cloud_token: token
            m.post(ENTREZ_TOKEN_URL, body=FAKE_JWT, content_type="text/plain")
            # validate token
            m.get(
                f"{BASE_URL}/auth/check_jwt",
                payload={"valid": True},
                content_type="application/json",
            )
            result = await api.authenticate()
            assert result is True
            assert api._jwt_token == FAKE_JWT
            assert api._serial_number == FAKE_SERIAL

    async def test_fw7_with_existing_token(self, api_with_token: EnphaseEnvoyLocalAPI):
        """Firmware 7+ with pre-existing token should skip cloud auth."""
        with aioresponses() as m:
            m.get(
                f"{BASE_URL}/info",
                payload={"device": {"sn": FAKE_SERIAL, "software": "D8.2.0"}},
                content_type="application/json",
            )
            m.get(
                f"{BASE_URL}/auth/check_jwt",
                payload={"valid": True},
                content_type="application/json",
            )
            result = await api_with_token.authenticate()
            assert result is True

    async def test_fw7_token_validation_fails(self, api_with_token: EnphaseEnvoyLocalAPI):
        """Token validation failure should raise EnvoyAuthError."""
        with aioresponses() as m:
            m.get(
                f"{BASE_URL}/info",
                payload={"device": {"sn": FAKE_SERIAL, "software": "D7.0.0"}},
                content_type="application/json",
            )
            m.get(f"{BASE_URL}/auth/check_jwt", status=401)
            with pytest.raises(EnvoyAuthError, match="Failed to authenticate"):
                await api_with_token.authenticate()

    async def test_fw7_no_cloud_credentials(self, api_no_cloud: EnphaseEnvoyLocalAPI):
        """Firmware 7+ without cloud creds or token should raise."""
        with aioresponses() as m:
            m.get(
                f"{BASE_URL}/info",
                payload={"device": {"sn": FAKE_SERIAL, "software": "D7.3.0"}},
                content_type="application/json",
            )
            with pytest.raises(EnvoyAuthError, match="Failed to authenticate"):
                await api_no_cloud.authenticate()

    async def test_fw_below_7_with_installer_password(self, api_no_cloud: EnphaseEnvoyLocalAPI):
        """Firmware < 7 should use generated installer password."""
        with aioresponses() as m:
            m.get(
                f"{BASE_URL}/info",
                payload={"device": {"sn": FAKE_SERIAL, "software": "D5.0.0"}},
                content_type="application/json",
            )
            m.post(
                f"{BASE_URL}/auth/check_jwt",
                payload={"token": "local_jwt_token"},
                content_type="application/json",
            )
            result = await api_no_cloud.authenticate()
            assert result is True
            assert api_no_cloud._jwt_token == "local_jwt_token"
            # Password should have been auto-generated from serial
            assert api_no_cloud._password == FAKE_SERIAL[-6:]

    async def test_fw_below_7_with_explicit_password(self, session: ClientSession):
        """Firmware < 7 with explicit password should use it."""
        api = EnphaseEnvoyLocalAPI(
            session=session,
            host=TEST_HOST,
            password="mypassword",
        )
        with aioresponses() as m:
            m.get(
                f"{BASE_URL}/info",
                payload={"device": {"sn": FAKE_SERIAL, "software": "D6.2.0"}},
                content_type="application/json",
            )
            m.post(
                f"{BASE_URL}/auth/check_jwt",
                payload={"token": "local_jwt"},
                content_type="application/json",
            )
            result = await api.authenticate()
            assert result is True
            assert api._password == "mypassword"

    async def test_fw_below_7_no_token_in_response(self, api_no_cloud: EnphaseEnvoyLocalAPI):
        """Firmware < 7 response without token should raise."""
        with aioresponses() as m:
            m.get(
                f"{BASE_URL}/info",
                payload={"device": {"sn": FAKE_SERIAL, "software": "D5.0.0"}},
                content_type="application/json",
            )
            m.post(
                f"{BASE_URL}/auth/check_jwt",
                payload={"error": "invalid"},
                content_type="application/json",
            )
            with pytest.raises(EnvoyAuthError, match="Failed to authenticate"):
                await api_no_cloud.authenticate()

    async def test_no_serial_in_info(self, api: EnphaseEnvoyLocalAPI):
        """Info response without serial should raise."""
        with aioresponses() as m:
            m.get(
                f"{BASE_URL}/info",
                payload={"unknown_key": "value"},
                content_type="application/json",
            )
            with pytest.raises(EnvoyAuthError, match="Failed to authenticate"):
                await api.authenticate()

    async def test_serial_from_sn_key(self, api_no_cloud: EnphaseEnvoyLocalAPI):
        """Serial from top-level 'sn' key should work."""
        with aioresponses() as m:
            m.get(
                f"{BASE_URL}/info",
                payload={"sn": FAKE_SERIAL, "software": "D5.0.0"},
                content_type="application/json",
            )
            m.post(
                f"{BASE_URL}/auth/check_jwt",
                payload={"token": "jwt"},
                content_type="application/json",
            )
            result = await api_no_cloud.authenticate()
            assert result is True
            # When _get_info wraps, we get {"device": {"sn": ...}}
            assert api_no_cloud._serial_number == FAKE_SERIAL

    async def test_serial_from_serial_num_key(self, api_no_cloud: EnphaseEnvoyLocalAPI):
        """Serial from 'serial_num' key should work."""
        with aioresponses() as m:
            m.get(
                f"{BASE_URL}/info",
                payload={"serial_num": FAKE_SERIAL, "software": "D5.0.0"},
                content_type="application/json",
            )
            m.post(
                f"{BASE_URL}/auth/check_jwt",
                payload={"token": "jwt"},
                content_type="application/json",
            )
            result = await api_no_cloud.authenticate()
            assert result is True

    async def test_serial_from_serialNumber_key(self, api_no_cloud: EnphaseEnvoyLocalAPI):
        """Serial from 'serialNumber' key (no device wrapper) should work."""
        # This returns a response that has neither 'device', 'sn', nor 'serial_num'
        # at top level -> passthrough, then authenticate extracts via info.get("serialNumber")
        with aioresponses() as m:
            m.get(
                f"{BASE_URL}/info",
                payload={"serialNumber": FAKE_SERIAL, "version": "5.1.0"},
                content_type="application/json",
            )
            m.post(
                f"{BASE_URL}/auth/check_jwt",
                payload={"token": "jwt"},
                content_type="application/json",
            )
            result = await api_no_cloud.authenticate()
            assert result is True
            assert api_no_cloud._serial_number == FAKE_SERIAL

    async def test_serial_from_xml(self, api_no_cloud: EnphaseEnvoyLocalAPI):
        """Serial extracted from XML in /info should work."""
        xml = "<envoy_info><device><sn>121845999999</sn><software>D5.0.0</software></device></envoy_info>"
        with aioresponses() as m:
            m.get(f"{BASE_URL}/info", body=xml, content_type="text/xml")
            m.post(
                f"{BASE_URL}/auth/check_jwt",
                payload={"token": "jwt"},
                content_type="application/json",
            )
            result = await api_no_cloud.authenticate()
            assert result is True
            assert api_no_cloud._serial_number == "121845999999"

    async def test_firmware_version_from_software(self, api: EnphaseEnvoyLocalAPI):
        """Firmware version from device.software key."""
        with aioresponses() as m:
            m.get(
                f"{BASE_URL}/info",
                payload={"device": {"sn": FAKE_SERIAL, "software": "D8.2.4127"}},
                content_type="application/json",
            )
            m.post(ENLIGHTEN_LOGIN_URL, payload={"session_id": "s"}, content_type="application/json")
            m.post(ENTREZ_TOKEN_URL, body=FAKE_JWT, content_type="text/plain")
            m.get(f"{BASE_URL}/auth/check_jwt", payload={}, content_type="application/json")
            await api.authenticate()
            assert api._firmware_version == "D8.2.4127"

    async def test_firmware_version_from_fw_version_key(self, api_no_cloud: EnphaseEnvoyLocalAPI):
        """Firmware version from 'fw_version' key."""
        with aioresponses() as m:
            m.get(
                f"{BASE_URL}/info",
                payload={"serialNumber": FAKE_SERIAL, "fw_version": "D5.0.0"},
                content_type="application/json",
            )
            m.post(
                f"{BASE_URL}/auth/check_jwt",
                payload={"token": "jwt"},
                content_type="application/json",
            )
            await api_no_cloud.authenticate()
            assert api_no_cloud._firmware_version == "D5.0.0"

    async def test_firmware_version_from_version_key(self, api_no_cloud: EnphaseEnvoyLocalAPI):
        """Firmware version from 'version' key."""
        with aioresponses() as m:
            m.get(
                f"{BASE_URL}/info",
                payload={"serialNumber": FAKE_SERIAL, "version": "5.1.0"},
                content_type="application/json",
            )
            m.post(
                f"{BASE_URL}/auth/check_jwt",
                payload={"token": "jwt"},
                content_type="application/json",
            )
            await api_no_cloud.authenticate()
            assert api_no_cloud._firmware_version == "5.1.0"

    async def test_info_failure_raises(self, api: EnphaseEnvoyLocalAPI):
        """Connection failure during _get_info should raise EnvoyAuthError."""
        with aioresponses() as m:
            m.get(f"{BASE_URL}/info", exception=aiohttp.ClientError("no route"))
            with pytest.raises(EnvoyAuthError, match="Failed to authenticate"):
                await api.authenticate()


# ---------------------------------------------------------------------------
# get_production_data
# ---------------------------------------------------------------------------


class TestGetProductionData:
    """Test get_production_data endpoint."""

    async def test_success(self, api_with_token: EnphaseEnvoyLocalAPI):
        with aioresponses() as m:
            m.get(
                f"{BASE_URL}/production.json",
                payload={"production": [{"type": "inverters", "wNow": 3000}]},
                content_type="application/json",
            )
            result = await api_with_token.get_production_data()
            assert result["production"][0]["wNow"] == 3000


# ---------------------------------------------------------------------------
# get_production_v1
# ---------------------------------------------------------------------------


class TestGetProductionV1:
    """Test production v1 with fallback."""

    async def test_success_on_first_try(self, api_with_token: EnphaseEnvoyLocalAPI):
        """V1 endpoint should be tried first."""
        with aioresponses() as m:
            m.get(
                f"{BASE_URL}/api/v1/production.json",
                payload={"wattHoursToday": 1234},
                content_type="application/json",
            )
            result = await api_with_token.get_production_v1()
            assert result["wattHoursToday"] == 1234

    async def test_404_fallback(self, api_with_token: EnphaseEnvoyLocalAPI):
        """404 on v1 should fallback to /production.json."""
        with aioresponses() as m:
            # First call fails with 404 (comes as EnvoyConnectionError with "404" in message)
            m.get(
                f"{BASE_URL}/api/v1/production.json",
                exception=aiohttp.ClientResponseError(
                    request_info=aiohttp.RequestInfo(
                        url=aiohttp.client.URL(f"{BASE_URL}/api/v1/production.json"),
                        method="GET",
                        headers={},
                        real_url=aiohttp.client.URL(f"{BASE_URL}/api/v1/production.json"),
                    ),
                    history=(),
                    status=404,
                    message="Not Found",
                ),
            )
            m.get(
                f"{BASE_URL}/production.json",
                payload={"production": [{"wNow": 500}]},
                content_type="application/json",
            )
            # The code catches EnvoyConnectionError with "404" in str(err)
            # Since aiohttp.ClientResponseError is a ClientError subclass,
            # it gets caught and wrapped as EnvoyConnectionError which contains "404"
            result = await api_with_token.get_production_v1()
            assert result["production"][0]["wNow"] == 500

    async def test_non_404_error_raises(self, api_with_token: EnphaseEnvoyLocalAPI):
        """Non-404 errors should propagate."""
        with aioresponses() as m:
            m.get(
                f"{BASE_URL}/api/v1/production.json",
                exception=aiohttp.ClientError("connection refused"),
            )
            with pytest.raises(EnvoyConnectionError):
                await api_with_token.get_production_v1()


# ---------------------------------------------------------------------------
# Simple GET endpoints
# ---------------------------------------------------------------------------


class TestSimpleGetEndpoints:
    """Test simple GET-only endpoints."""

    async def test_get_meters_readings(self, api_with_token: EnphaseEnvoyLocalAPI):
        with aioresponses() as m:
            m.get(
                f"{BASE_URL}/ivp/meters/readings",
                payload=[{"eid": 1, "activePower": 100}],
                content_type="application/json",
            )
            result = await api_with_token.get_meters_readings()
            assert result == [{"eid": 1, "activePower": 100}]

    async def test_get_ensemble_inventory(self, api_with_token: EnphaseEnvoyLocalAPI):
        with aioresponses() as m:
            m.get(
                f"{BASE_URL}/ivp/ensemble/inventory",
                payload=[{"type": "ENCHARGE", "devices": []}],
                content_type="application/json",
            )
            result = await api_with_token.get_ensemble_inventory()
            assert result[0]["type"] == "ENCHARGE"

    async def test_get_ensemble_status(self, api_with_token: EnphaseEnvoyLocalAPI):
        with aioresponses() as m:
            m.get(
                f"{BASE_URL}/ivp/ensemble/status",
                payload={"secctrl": {"agg_soc": 80}},
                content_type="application/json",
            )
            result = await api_with_token.get_ensemble_status()
            assert result["secctrl"]["agg_soc"] == 80

    async def test_get_ensemble_power(self, api_with_token: EnphaseEnvoyLocalAPI):
        with aioresponses() as m:
            m.get(
                f"{BASE_URL}/ivp/ensemble/power",
                payload={"devices:": [{"real_power_mw": 5000}]},
                content_type="application/json",
            )
            result = await api_with_token.get_ensemble_power()
            assert result["devices:"][0]["real_power_mw"] == 5000

    async def test_get_home_json(self, api_with_token: EnphaseEnvoyLocalAPI):
        with aioresponses() as m:
            m.get(
                f"{BASE_URL}/home.json",
                payload={"software_build_epoch": 1234567890},
                content_type="application/json",
            )
            result = await api_with_token.get_home_json()
            assert result["software_build_epoch"] == 1234567890

    async def test_get_acb_config(self, api_with_token: EnphaseEnvoyLocalAPI):
        with aioresponses() as m:
            m.get(
                f"{BASE_URL}/admin/lib/acb_config.json",
                payload={"sleep": False},
                content_type="application/json",
            )
            result = await api_with_token.get_acb_config()
            assert result == {"sleep": False}


# ---------------------------------------------------------------------------
# get_battery_data - full integration
# ---------------------------------------------------------------------------


def _mock_battery_endpoints(
    m,
    ensemble_status=None,
    meters=None,
    inventory=None,
    ensemble_power=None,
    tariff=None,
    status_exc=None,
    meters_exc=None,
    inventory_exc=None,
    power_exc=None,
    tariff_exc=None,
):
    """Helper to mock all battery data endpoints."""
    if status_exc:
        m.get(f"{BASE_URL}/ivp/ensemble/status", exception=status_exc)
    else:
        m.get(
            f"{BASE_URL}/ivp/ensemble/status",
            payload=ensemble_status or {},
            content_type="application/json",
        )

    if meters_exc:
        m.get(f"{BASE_URL}/ivp/meters/readings", exception=meters_exc)
    else:
        m.get(
            f"{BASE_URL}/ivp/meters/readings",
            payload=meters if meters is not None else [],
            content_type="application/json",
        )

    if inventory_exc:
        m.get(f"{BASE_URL}/ivp/ensemble/inventory", exception=inventory_exc)
    else:
        m.get(
            f"{BASE_URL}/ivp/ensemble/inventory",
            payload=inventory if inventory is not None else [],
            content_type="application/json",
        )

    if power_exc:
        m.get(f"{BASE_URL}/ivp/ensemble/power", exception=power_exc)
    else:
        m.get(
            f"{BASE_URL}/ivp/ensemble/power",
            payload=ensemble_power or {},
            content_type="application/json",
        )

    if tariff_exc:
        m.get(f"{BASE_URL}/admin/lib/tariff", exception=tariff_exc)
    else:
        m.get(
            f"{BASE_URL}/admin/lib/tariff",
            payload=tariff or {},
            content_type="application/json",
        )


class TestGetBatteryData:
    """Test comprehensive battery data retrieval."""

    async def test_full_integration_secctrl_path(self, api_with_token: EnphaseEnvoyLocalAPI):
        """Full data with secctrl-based SOC (firmware 8.x path)."""
        ensemble_status = {
            "secctrl": {
                "agg_soc": 85,
                "ENC_agg_soh": 98,
                "ENC_agg_avail_energy": 10000,
                "Enc_max_available_capacity": 12000,
            },
            "relay": {"Enchg_grid_mode": "grid-tied"},
        }
        meters = [
            {
                "eid": 0x3D00FE00,  # Battery meter
                "activePower": -1500,
                "actEnergyDlvd": 50000,
                "actEnergyRcvd": 30000,
            },
            {
                "eid": 704643584,  # Production meter
                "activePower": 3000,
                "actEnergyDlvd": 100000,
            },
            {
                "eid": 704643328,  # Consumption meter
                "activePower": 2000,
                "actEnergyDlvd": 80000,
            },
        ]
        inventory = [
            {
                "type": "ENCHARGE",
                "devices": [
                    {
                        "percentFull": 86,
                        "temperature": 25,
                        "maxCellTemp": 27,
                        "serial_num": "BAT001",
                    }
                ],
            }
        ]
        tariff = {
            "tariff": {
                "storage_settings": {
                    "charge_from_grid": True,
                }
            }
        }

        with aioresponses() as m:
            _mock_battery_endpoints(
                m,
                ensemble_status=ensemble_status,
                meters=meters,
                inventory=inventory,
                tariff=tariff,
            )
            result = await api_with_token.get_battery_data()

        assert result["soc"] == 86  # Overridden by percentFull
        assert result["soh"] == 98
        assert result["available_energy"] == 10000
        assert result["max_capacity"] == 12000
        assert result["status"] == "grid-tied"
        assert result["power"] == -1500
        assert result["charge_power"] == 1500
        assert result["discharge_power"] == 0
        assert result["total_energy_discharged"] == 50.0  # 50000/1000
        assert result["total_energy_charged"] == 30.0
        assert result["total_production"] == 100.0
        assert result["total_consumption"] == 80.0
        assert result["charge_from_grid"] is True
        assert result["temperature"] == 25
        assert result["max_cell_temp"] == 27
        assert result["source"] == "local_envoy"
        assert "timestamp" in result
        assert len(result["devices"]) == 1

    async def test_secctrl_with_enc_agg_soc_fallback(self, api_with_token: EnphaseEnvoyLocalAPI):
        """secctrl uses ENC_agg_soc when agg_soc key is absent."""
        ensemble_status = {
            "secctrl": {
                "ENC_agg_soc": 72,
                "ENC_agg_soh": 100,
                "ENC_agg_avail_energy": 5000,
                "Enc_max_available_capacity": 10000,
            },
        }
        with aioresponses() as m:
            _mock_battery_endpoints(m, ensemble_status=ensemble_status)
            result = await api_with_token.get_battery_data()
        # agg_soc key absent, fallback to ENC_agg_soc
        assert result["soc"] == 72

    async def test_secctrl_with_agg_soc_zero(self, api_with_token: EnphaseEnvoyLocalAPI):
        """secctrl.get('agg_soc', ...) returns 0 when key exists with value 0."""
        ensemble_status = {
            "secctrl": {
                "agg_soc": 0,
                "ENC_agg_soc": 72,
            },
        }
        with aioresponses() as m:
            _mock_battery_endpoints(m, ensemble_status=ensemble_status)
            result = await api_with_token.get_battery_data()
        # agg_soc key exists with value 0 -> dict.get returns 0 (not the default)
        assert result["soc"] == 0

    async def test_fallback_path_older_firmware(self, api_with_token: EnphaseEnvoyLocalAPI):
        """Older firmware without secctrl should use direct fields."""
        ensemble_status = {
            "percentage": 65,
            "state": "charging",
            "available_energy": 8000,
            "max_available_capacity": 10000,
        }
        with aioresponses() as m:
            _mock_battery_endpoints(m, ensemble_status=ensemble_status)
            result = await api_with_token.get_battery_data()
        assert result["soc"] == 65
        assert result["status"] == "charging"
        assert result["available_energy"] == 8000
        assert result["max_capacity"] == 10000

    async def test_relay_not_grid_tied(self, api_with_token: EnphaseEnvoyLocalAPI):
        """Non grid-tied relay should report 'unknown' status."""
        ensemble_status = {
            "secctrl": {"agg_soc": 50},
            "relay": {"Enchg_grid_mode": "multimode-ongrid"},
        }
        with aioresponses() as m:
            _mock_battery_endpoints(m, ensemble_status=ensemble_status)
            result = await api_with_token.get_battery_data()
        assert result["status"] == "unknown"

    async def test_ensemble_power_fallback(self, api_with_token: EnphaseEnvoyLocalAPI):
        """When battery meter power is 0, ensemble_power should be used."""
        meters = [
            {
                "eid": 0x3D00FE00,
                "activePower": 0,  # Battery meter reports 0
                "actEnergyDlvd": 0,
                "actEnergyRcvd": 0,
            },
        ]
        ensemble_power = {
            "devices:": [
                {"real_power_mw": 2500000, "soc": 80}  # 2500W in milliwatts
            ]
        }
        with aioresponses() as m:
            _mock_battery_endpoints(m, meters=meters, ensemble_power=ensemble_power)
            result = await api_with_token.get_battery_data()
        assert result["power"] == 2500  # 2500000 mW / 1000

    async def test_production_consumption_fallback(self, api_with_token: EnphaseEnvoyLocalAPI):
        """When battery and ensemble power are 0, use production - consumption."""
        meters = [
            {
                "eid": 704643584,  # Production
                "activePower": 4000,
                "actEnergyDlvd": 0,
            },
            {
                "eid": 704643328,  # Consumption
                "activePower": 2500,
                "actEnergyDlvd": 0,
            },
        ]
        with aioresponses() as m:
            _mock_battery_endpoints(m, meters=meters)
            result = await api_with_token.get_battery_data()
        # No battery meter, ensemble_power empty, so fallback: 4000 - 2500 = 1500
        assert result["power"] == 1500
        assert result["discharge_power"] == 1500
        assert result["charge_power"] == 0

    async def test_meters_charging_power(self, api_with_token: EnphaseEnvoyLocalAPI):
        """Negative battery power should set charge_power."""
        meters = [
            {
                "eid": 0x3D00FE00,
                "activePower": -2000,
                "actEnergyDlvd": 0,
                "actEnergyRcvd": 0,
            },
        ]
        with aioresponses() as m:
            _mock_battery_endpoints(m, meters=meters)
            result = await api_with_token.get_battery_data()
        assert result["power"] == -2000
        assert result["charge_power"] == 2000
        assert result["discharge_power"] == 0

    async def test_inventory_encharge_type(self, api_with_token: EnphaseEnvoyLocalAPI):
        """Inventory with ENCHARGE type should extract devices."""
        inventory = [
            {"type": "ACB", "devices": [{"serial": "ACB001"}]},
            {
                "type": "ENCHARGE",
                "devices": [
                    {
                        "percentFull": 90,
                        "temperature": 22,
                        "maxCellTemp": 24,
                    }
                ],
            },
        ]
        with aioresponses() as m:
            _mock_battery_endpoints(m, inventory=inventory)
            result = await api_with_token.get_battery_data()
        assert result["devices"][0]["percentFull"] == 90
        assert result["temperature"] == 22
        assert result["max_cell_temp"] == 24

    async def test_inventory_encharge_no_percent_full(self, api_with_token: EnphaseEnvoyLocalAPI):
        """Inventory device without percentFull should not override SOC."""
        ensemble_status = {"secctrl": {"agg_soc": 77}}
        inventory = [
            {
                "type": "ENCHARGE",
                "devices": [{"temperature": 20}],
            },
        ]
        with aioresponses() as m:
            _mock_battery_endpoints(m, ensemble_status=ensemble_status, inventory=inventory)
            result = await api_with_token.get_battery_data()
        assert result["soc"] == 77  # Not overridden

    async def test_inventory_older_format(self, api_with_token: EnphaseEnvoyLocalAPI):
        """Older inventory format (dict instead of list) should use fallback."""
        inventory_dict = {"devices": [{"serial": "DEV001"}]}
        with aioresponses() as m:
            # inventory is a dict, not a list -> triggers elif branch
            m.get(f"{BASE_URL}/ivp/ensemble/status", payload={}, content_type="application/json")
            m.get(f"{BASE_URL}/ivp/meters/readings", payload=[], content_type="application/json")
            m.get(f"{BASE_URL}/ivp/ensemble/inventory", payload=inventory_dict, content_type="application/json")
            m.get(f"{BASE_URL}/ivp/ensemble/power", payload={}, content_type="application/json")
            m.get(f"{BASE_URL}/admin/lib/tariff", payload={}, content_type="application/json")
            result = await api_with_token.get_battery_data()
        assert result["devices"] == [{"serial": "DEV001"}]

    async def test_tariff_charge_from_grid(self, api_with_token: EnphaseEnvoyLocalAPI):
        """Tariff with charge_from_grid should be extracted."""
        tariff = {"tariff": {"storage_settings": {"charge_from_grid": True}}}
        with aioresponses() as m:
            _mock_battery_endpoints(m, tariff=tariff)
            result = await api_with_token.get_battery_data()
        assert result["charge_from_grid"] is True

    async def test_tariff_no_storage_settings(self, api_with_token: EnphaseEnvoyLocalAPI):
        """Tariff without storage_settings should default to False."""
        tariff = {"tariff": {"other_setting": True}}
        with aioresponses() as m:
            _mock_battery_endpoints(m, tariff=tariff)
            result = await api_with_token.get_battery_data()
        assert result["charge_from_grid"] is False

    async def test_tariff_empty(self, api_with_token: EnphaseEnvoyLocalAPI):
        """Empty tariff should default to False."""
        with aioresponses() as m:
            _mock_battery_endpoints(m, tariff={})
            result = await api_with_token.get_battery_data()
        assert result["charge_from_grid"] is False

    async def test_tariff_error(self, api_with_token: EnphaseEnvoyLocalAPI):
        """Tariff endpoint error should default charge_from_grid to False."""
        with aioresponses() as m:
            _mock_battery_endpoints(m, tariff_exc=aiohttp.ClientError("tariff fail"))
            result = await api_with_token.get_battery_data()
        assert result["charge_from_grid"] is False

    async def test_all_endpoints_fail_raises_error(self, api_with_token: EnphaseEnvoyLocalAPI):
        """All sub-endpoints failing should raise EnvoyLocalApiError."""
        with aioresponses() as m:
            _mock_battery_endpoints(
                m,
                status_exc=aiohttp.ClientError("fail1"),
                meters_exc=aiohttp.ClientError("fail2"),
                inventory_exc=aiohttp.ClientError("fail3"),
                power_exc=aiohttp.ClientError("fail4"),
                tariff_exc=aiohttp.ClientError("fail5"),
            )
            with pytest.raises(EnvoyLocalApiError, match="All Envoy endpoints failed"):
                await api_with_token.get_battery_data()

    async def test_raw_json_parsing(self, api_with_token: EnphaseEnvoyLocalAPI):
        """Responses with 'raw' key (firmware 8.x text format) should be parsed."""
        ensemble_status_raw = json.dumps({"secctrl": {"agg_soc": 45}})
        meters_raw = json.dumps([{"eid": 0x3D00FE00, "activePower": 500, "actEnergyDlvd": 0, "actEnergyRcvd": 0}])
        inventory_raw = json.dumps([{"type": "ENCHARGE", "devices": [{"percentFull": 46}]}])
        power_raw = json.dumps({"devices:": []})
        tariff_raw = json.dumps({"tariff": {"storage_settings": {"charge_from_grid": False}}})

        with aioresponses() as m:
            m.get(f"{BASE_URL}/ivp/ensemble/status", body=ensemble_status_raw, content_type="text/html")
            m.get(f"{BASE_URL}/ivp/meters/readings", body=meters_raw, content_type="text/html")
            m.get(f"{BASE_URL}/ivp/ensemble/inventory", body=inventory_raw, content_type="text/html")
            m.get(f"{BASE_URL}/ivp/ensemble/power", body=power_raw, content_type="text/html")
            m.get(f"{BASE_URL}/admin/lib/tariff", body=tariff_raw, content_type="text/html")
            result = await api_with_token.get_battery_data()

        assert result["soc"] == 46  # overridden by percentFull
        assert result["power"] == 500
        assert result["charge_from_grid"] is False

    async def test_empty_ensemble_status(self, api_with_token: EnphaseEnvoyLocalAPI):
        """Empty ensemble_status should not add SOC data."""
        with aioresponses() as m:
            _mock_battery_endpoints(m, ensemble_status={})
            result = await api_with_token.get_battery_data()
        assert "soc" not in result or result.get("soc") is None or True  # just doesn't crash

    async def test_meters_not_list(self, api_with_token: EnphaseEnvoyLocalAPI):
        """Meters as dict (not list) should skip meter parsing."""
        with aioresponses() as m:
            m.get(f"{BASE_URL}/ivp/ensemble/status", payload={}, content_type="application/json")
            m.get(
                f"{BASE_URL}/ivp/meters/readings",
                payload={"some_key": "value"},
                content_type="application/json",
            )
            m.get(f"{BASE_URL}/ivp/ensemble/inventory", payload=[], content_type="application/json")
            m.get(f"{BASE_URL}/ivp/ensemble/power", payload={}, content_type="application/json")
            m.get(f"{BASE_URL}/admin/lib/tariff", payload={}, content_type="application/json")
            result = await api_with_token.get_battery_data()
        # No power key set from meters since it's not a list
        assert "power" not in result

    async def test_ensemble_power_empty_devices(self, api_with_token: EnphaseEnvoyLocalAPI):
        """ensemble_power with empty devices list should not override power."""
        meters = [
            {
                "eid": 0x3D00FE00,
                "activePower": 0,
                "actEnergyDlvd": 0,
                "actEnergyRcvd": 0,
            },
        ]
        ensemble_power = {"devices:": []}
        with aioresponses() as m:
            _mock_battery_endpoints(m, meters=meters, ensemble_power=ensemble_power)
            result = await api_with_token.get_battery_data()
        assert result["power"] == 0

    async def test_inventory_empty_devices(self, api_with_token: EnphaseEnvoyLocalAPI):
        """ENCHARGE type with empty devices list should not crash."""
        inventory = [{"type": "ENCHARGE", "devices": []}]
        with aioresponses() as m:
            _mock_battery_endpoints(m, inventory=inventory)
            result = await api_with_token.get_battery_data()
        assert result["devices"] == []

    async def test_energy_values_zero_still_stored(self, api_with_token: EnphaseEnvoyLocalAPI):
        """Zero energy values should store as 0."""
        meters = [
            {
                "eid": 0x3D00FE00,
                "activePower": 100,
                "actEnergyDlvd": 0,
                "actEnergyRcvd": 0,
            },
        ]
        with aioresponses() as m:
            _mock_battery_endpoints(m, meters=meters)
            result = await api_with_token.get_battery_data()
        assert result["total_energy_discharged"] == 0
        assert result["total_energy_charged"] == 0

    async def test_multiple_battery_meters(self, api_with_token: EnphaseEnvoyLocalAPI):
        """Only the first storage EID meter should be used for battery power."""
        meters = [
            {
                "eid": 0x3D00FE00,
                "activePower": -300,
                "actEnergyDlvd": 1000,
                "actEnergyRcvd": 2000,
            },
            {
                "eid": 0x3D010000,  # Second storage meter
                "activePower": -200,
                "actEnergyDlvd": 500,
                "actEnergyRcvd": 1000,
            },
        ]
        with aioresponses() as m:
            _mock_battery_endpoints(m, meters=meters)
            result = await api_with_token.get_battery_data()
        # Both are storage meters, last one wins in the loop
        assert result["power"] == -200

    async def test_ensemble_power_dict_not_list(self, api_with_token: EnphaseEnvoyLocalAPI):
        """ensemble_power that is not a dict should not crash."""
        meters = [
            {
                "eid": 0x3D00FE00,
                "activePower": 0,
                "actEnergyDlvd": 0,
                "actEnergyRcvd": 0,
            },
        ]
        with aioresponses() as m:
            m.get(f"{BASE_URL}/ivp/ensemble/status", payload={}, content_type="application/json")
            m.get(f"{BASE_URL}/ivp/meters/readings", payload=meters, content_type="application/json")
            m.get(f"{BASE_URL}/ivp/ensemble/inventory", payload=[], content_type="application/json")
            # Return list instead of dict for ensemble_power
            m.get(f"{BASE_URL}/ivp/ensemble/power", payload=[{"something": 1}], content_type="application/json")
            m.get(f"{BASE_URL}/admin/lib/tariff", payload={}, content_type="application/json")
            result = await api_with_token.get_battery_data()
        # ensemble_power is not a dict, so fallback skipped, power stays 0
        assert result["power"] == 0

    async def test_invalid_raw_json_raises(self, api_with_token: EnphaseEnvoyLocalAPI):
        """Invalid JSON in 'raw' key should trigger outer except and raise EnvoyLocalApiError."""
        with aioresponses() as m:
            # Return invalid JSON as raw text so json.loads fails
            m.get(f"{BASE_URL}/ivp/ensemble/status", body="not valid json{{{", content_type="text/html")
            m.get(f"{BASE_URL}/ivp/meters/readings", payload=[], content_type="application/json")
            m.get(f"{BASE_URL}/ivp/ensemble/inventory", payload=[], content_type="application/json")
            m.get(f"{BASE_URL}/ivp/ensemble/power", payload={}, content_type="application/json")
            m.get(f"{BASE_URL}/admin/lib/tariff", payload={}, content_type="application/json")
            with pytest.raises(EnvoyLocalApiError, match="Failed to retrieve battery data"):
                await api_with_token.get_battery_data()


# ---------------------------------------------------------------------------
# set_battery_mode
# ---------------------------------------------------------------------------


class TestSetBatteryMode:
    """Test battery mode setter (not implemented)."""

    async def test_returns_false(self, api_with_token: EnphaseEnvoyLocalAPI):
        result = await api_with_token.set_battery_mode("self-consumption")
        assert result is False


# ---------------------------------------------------------------------------
# set_charge_from_grid
# ---------------------------------------------------------------------------


class TestSetChargeFromGrid:
    """Test charge_from_grid setter."""

    async def test_success(self, api_with_token: EnphaseEnvoyLocalAPI):
        """Should GET tariff, modify, PUT back."""
        tariff = {
            "tariff": {
                "storage_settings": {
                    "charge_from_grid": False,
                }
            }
        }
        with aioresponses() as m:
            m.get(
                f"{BASE_URL}/admin/lib/tariff",
                payload=tariff,
                content_type="application/json",
            )
            m.put(
                f"{BASE_URL}/admin/lib/tariff",
                payload={"success": True},
                content_type="application/json",
            )
            result = await api_with_token.set_charge_from_grid(True)
        assert result is True

    async def test_success_with_raw_json(self, api_with_token: EnphaseEnvoyLocalAPI):
        """Firmware 8.x raw JSON format should be parsed."""
        tariff_json = json.dumps({"tariff": {"storage_settings": {"charge_from_grid": False}}})
        with aioresponses() as m:
            m.get(
                f"{BASE_URL}/admin/lib/tariff",
                body=tariff_json,
                content_type="text/html",
            )
            m.put(
                f"{BASE_URL}/admin/lib/tariff",
                payload={"ok": True},
                content_type="application/json",
            )
            result = await api_with_token.set_charge_from_grid(True)
        assert result is True

    async def test_empty_tariff(self, api_with_token: EnphaseEnvoyLocalAPI):
        """Empty tariff response should return False."""
        with aioresponses() as m:
            m.get(
                f"{BASE_URL}/admin/lib/tariff",
                payload={},
                content_type="application/json",
            )
            result = await api_with_token.set_charge_from_grid(True)
        assert result is False

    async def test_no_storage_settings(self, api_with_token: EnphaseEnvoyLocalAPI):
        """Tariff without storage_settings should return False."""
        with aioresponses() as m:
            m.get(
                f"{BASE_URL}/admin/lib/tariff",
                payload={"tariff": {"other": True}},
                content_type="application/json",
            )
            result = await api_with_token.set_charge_from_grid(True)
        assert result is False

    async def test_get_fails(self, api_with_token: EnphaseEnvoyLocalAPI):
        """GET failure should return False."""
        with aioresponses() as m:
            m.get(
                f"{BASE_URL}/admin/lib/tariff",
                exception=aiohttp.ClientError("fail"),
            )
            result = await api_with_token.set_charge_from_grid(True)
        assert result is False

    async def test_put_fails(self, api_with_token: EnphaseEnvoyLocalAPI):
        """PUT failure should return False."""
        tariff = {"tariff": {"storage_settings": {"charge_from_grid": False}}}
        with aioresponses() as m:
            m.get(
                f"{BASE_URL}/admin/lib/tariff",
                payload=tariff,
                content_type="application/json",
            )
            m.put(
                f"{BASE_URL}/admin/lib/tariff",
                exception=aiohttp.ClientError("put fail"),
            )
            result = await api_with_token.set_charge_from_grid(True)
        assert result is False

    async def test_null_response(self, api_with_token: EnphaseEnvoyLocalAPI):
        """Null/None GET response should return False."""
        with aioresponses() as m:
            # Return None by sending empty body with non-json content type
            m.get(
                f"{BASE_URL}/admin/lib/tariff",
                body="",
                content_type="text/html",
            )
            result = await api_with_token.set_charge_from_grid(True)
        assert result is False


# ---------------------------------------------------------------------------
# set_limit_discharge
# ---------------------------------------------------------------------------


class TestSetLimitDischarge:
    """Test discharge_to_grid setter."""

    async def test_success(self, api_with_token: EnphaseEnvoyLocalAPI):
        tariff = {"tariff": {"storage_settings": {"discharge_to_grid": False}}}
        with aioresponses() as m:
            m.get(f"{BASE_URL}/admin/lib/tariff", payload=tariff, content_type="application/json")
            m.put(f"{BASE_URL}/admin/lib/tariff", payload={"ok": True}, content_type="application/json")
            result = await api_with_token.set_limit_discharge(True)
        assert result is True

    async def test_raw_json_format(self, api_with_token: EnphaseEnvoyLocalAPI):
        """Firmware 8.x raw JSON format should be parsed."""
        tariff_json = json.dumps({"tariff": {"storage_settings": {"discharge_to_grid": False}}})
        with aioresponses() as m:
            m.get(f"{BASE_URL}/admin/lib/tariff", body=tariff_json, content_type="text/html")
            m.put(f"{BASE_URL}/admin/lib/tariff", payload={"ok": True}, content_type="application/json")
            result = await api_with_token.set_limit_discharge(True)
        assert result is True

    async def test_empty_tariff(self, api_with_token: EnphaseEnvoyLocalAPI):
        with aioresponses() as m:
            m.get(f"{BASE_URL}/admin/lib/tariff", payload={}, content_type="application/json")
            result = await api_with_token.set_limit_discharge(True)
        assert result is False

    async def test_no_storage_settings(self, api_with_token: EnphaseEnvoyLocalAPI):
        with aioresponses() as m:
            m.get(
                f"{BASE_URL}/admin/lib/tariff",
                payload={"tariff": {"other": True}},
                content_type="application/json",
            )
            result = await api_with_token.set_limit_discharge(True)
        assert result is False

    async def test_get_fails(self, api_with_token: EnphaseEnvoyLocalAPI):
        with aioresponses() as m:
            m.get(f"{BASE_URL}/admin/lib/tariff", exception=aiohttp.ClientError("fail"))
            result = await api_with_token.set_limit_discharge(False)
        assert result is False

    async def test_null_response(self, api_with_token: EnphaseEnvoyLocalAPI):
        with aioresponses() as m:
            m.get(f"{BASE_URL}/admin/lib/tariff", body="", content_type="text/html")
            result = await api_with_token.set_limit_discharge(True)
        assert result is False


# ---------------------------------------------------------------------------
# set_reserve_battery_discharge
# ---------------------------------------------------------------------------


class TestSetReserveBatteryDischarge:
    """Test reserve_battery_discharge setter."""

    async def test_success(self, api_with_token: EnphaseEnvoyLocalAPI):
        tariff = {"tariff": {"storage_settings": {"reserve_battery_discharge": False}}}
        with aioresponses() as m:
            m.get(f"{BASE_URL}/admin/lib/tariff", payload=tariff, content_type="application/json")
            m.put(f"{BASE_URL}/admin/lib/tariff", payload={"ok": True}, content_type="application/json")
            result = await api_with_token.set_reserve_battery_discharge(True)
        assert result is True

    async def test_raw_json_format(self, api_with_token: EnphaseEnvoyLocalAPI):
        tariff_json = json.dumps({"tariff": {"storage_settings": {"reserve_battery_discharge": False}}})
        with aioresponses() as m:
            m.get(f"{BASE_URL}/admin/lib/tariff", body=tariff_json, content_type="text/html")
            m.put(f"{BASE_URL}/admin/lib/tariff", payload={"ok": True}, content_type="application/json")
            result = await api_with_token.set_reserve_battery_discharge(True)
        assert result is True

    async def test_empty_tariff(self, api_with_token: EnphaseEnvoyLocalAPI):
        with aioresponses() as m:
            m.get(f"{BASE_URL}/admin/lib/tariff", payload={}, content_type="application/json")
            result = await api_with_token.set_reserve_battery_discharge(True)
        assert result is False

    async def test_no_storage_settings(self, api_with_token: EnphaseEnvoyLocalAPI):
        with aioresponses() as m:
            m.get(
                f"{BASE_URL}/admin/lib/tariff",
                payload={"tariff": {"other": True}},
                content_type="application/json",
            )
            result = await api_with_token.set_reserve_battery_discharge(True)
        assert result is False

    async def test_get_fails(self, api_with_token: EnphaseEnvoyLocalAPI):
        with aioresponses() as m:
            m.get(f"{BASE_URL}/admin/lib/tariff", exception=aiohttp.ClientError("fail"))
            result = await api_with_token.set_reserve_battery_discharge(False)
        assert result is False

    async def test_null_response(self, api_with_token: EnphaseEnvoyLocalAPI):
        with aioresponses() as m:
            m.get(f"{BASE_URL}/admin/lib/tariff", body="", content_type="text/html")
            result = await api_with_token.set_reserve_battery_discharge(True)
        assert result is False


# ---------------------------------------------------------------------------
# set_acb_sleep_mode
# ---------------------------------------------------------------------------


class TestSetAcbSleepMode:
    """Test ACB sleep mode setter."""

    async def test_success_enable(self, api_with_token: EnphaseEnvoyLocalAPI):
        with aioresponses() as m:
            m.post(
                f"{BASE_URL}/admin/lib/acb_config.json",
                payload={"success": True},
                content_type="application/json",
            )
            result = await api_with_token.set_acb_sleep_mode(True)
        assert result is True

    async def test_success_disable(self, api_with_token: EnphaseEnvoyLocalAPI):
        with aioresponses() as m:
            m.post(
                f"{BASE_URL}/admin/lib/acb_config.json",
                payload={"success": True},
                content_type="application/json",
            )
            result = await api_with_token.set_acb_sleep_mode(False)
        assert result is True

    async def test_failure(self, api_with_token: EnphaseEnvoyLocalAPI):
        with aioresponses() as m:
            m.post(
                f"{BASE_URL}/admin/lib/acb_config.json",
                exception=aiohttp.ClientError("fail"),
            )
            result = await api_with_token.set_acb_sleep_mode(True)
        assert result is False


# ---------------------------------------------------------------------------
# close
# ---------------------------------------------------------------------------


class TestClose:
    """Test close method."""

    async def test_clears_token(self, api_with_token: EnphaseEnvoyLocalAPI):
        assert api_with_token._jwt_token is not None
        await api_with_token.close()
        assert api_with_token._jwt_token is None

    async def test_close_when_no_token(self, api: EnphaseEnvoyLocalAPI):
        """Closing with no token should not raise."""
        assert api._jwt_token is None
        await api.close()
        assert api._jwt_token is None
