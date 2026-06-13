"""Tests for the Enphase Battery diagnostics platform."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import MagicMock

import pytest

from custom_components.enphase_battery import EnphaseBatteryRuntimeData
from custom_components.enphase_battery.const import DOMAIN
from custom_components.enphase_battery.coordinator import (
    EnphaseBatteryDataUpdateCoordinator,
)
from custom_components.enphase_battery.diagnostics import (
    TO_REDACT,
    async_get_config_entry_diagnostics,
)


# ---------------------------------------------------------------------------
# Helper: create a mock coordinator
# ---------------------------------------------------------------------------
def _mock_coordinator(data=None):
    """Create a mock coordinator with data."""
    coord = MagicMock(spec=EnphaseBatteryDataUpdateCoordinator)
    coord.data = data
    coord.is_local_mode = False
    coord.local_api = None
    coord.api = None
    coord.last_update_success = True
    coord.update_interval = timedelta(seconds=60)
    return coord


def _mock_entry(data=None, options=None):
    """Create a mock config entry."""
    entry = MagicMock()
    entry.entry_id = "test_entry_id"
    entry.version = 2
    entry.domain = DOMAIN
    entry.title = "Enphase Battery"
    entry.data = data or {
        "username": "test@example.com",
        "password": "secret123",
        "connection_mode": "cloud",
    }
    entry.options = options or {}
    return entry


# ===========================================================================
# async_get_config_entry_diagnostics
# ===========================================================================
class TestDiagnostics:
    """Tests for the async_get_config_entry_diagnostics function."""

    @pytest.mark.asyncio
    async def test_basic_diagnostics(self):
        """Test basic diagnostics output."""
        coord = _mock_coordinator({"soc": 50, "power": 1000})
        entry = _mock_entry()
        entry.runtime_data = EnphaseBatteryRuntimeData(coordinator=coord)

        result = await async_get_config_entry_diagnostics(MagicMock(), entry)

        assert "config_entry" in result
        assert "coordinator" in result
        assert "data" in result

        # Config entry info
        assert result["config_entry"]["entry_id"] == "test_entry_id"
        assert result["config_entry"]["version"] == 2
        assert result["config_entry"]["domain"] == DOMAIN
        assert result["config_entry"]["title"] == "Enphase Battery"

    @pytest.mark.asyncio
    async def test_redacted_config_data(self):
        """Test that sensitive config data is redacted."""
        coord = _mock_coordinator({"soc": 50})
        entry = _mock_entry(
            data={
                "username": "test@example.com",
                "password": "secret123",
                "cloud_username": "cloud@example.com",
                "cloud_password": "cloudpass",
                "connection_mode": "cloud",
                "token": "jwt-abc123",
            }
        )
        entry.runtime_data = EnphaseBatteryRuntimeData(coordinator=coord)

        result = await async_get_config_entry_diagnostics(MagicMock(), entry)

        config_data = result["config_entry"]["data"]
        assert config_data["username"] == "**REDACTED**"
        assert config_data["password"] == "**REDACTED**"
        assert config_data["cloud_username"] == "**REDACTED**"
        assert config_data["cloud_password"] == "**REDACTED**"
        assert config_data["token"] == "**REDACTED**"
        # Non-sensitive data should remain
        assert config_data["connection_mode"] == "cloud"

    @pytest.mark.asyncio
    async def test_coordinator_info(self):
        """Test coordinator info in diagnostics."""
        coord = _mock_coordinator({"soc": 50})
        coord.last_update_success = True
        coord.is_local_mode = False
        coord.update_interval = timedelta(seconds=60)

        entry = _mock_entry()
        entry.runtime_data = EnphaseBatteryRuntimeData(coordinator=coord)

        result = await async_get_config_entry_diagnostics(MagicMock(), entry)

        assert result["coordinator"]["last_update_success"] is True
        assert result["coordinator"]["is_local_mode"] is False
        assert result["coordinator"]["update_interval"] == str(timedelta(seconds=60))

    @pytest.mark.asyncio
    async def test_coordinator_data_redacted(self):
        """Test that coordinator data has sensitive keys redacted."""
        coord = _mock_coordinator(
            {
                "soc": 50,
                "serial": "ABC123",
                "serial_number": "DEF456",
                "token": "jwt-secret",
                "power": 1000,
            }
        )

        entry = _mock_entry()
        entry.runtime_data = EnphaseBatteryRuntimeData(coordinator=coord)

        result = await async_get_config_entry_diagnostics(MagicMock(), entry)

        redacted_data = result["data"]
        assert redacted_data["serial"] == "**REDACTED**"
        assert redacted_data["serial_number"] == "**REDACTED**"
        assert redacted_data["token"] == "**REDACTED**"
        # Non-sensitive data should remain
        assert redacted_data["soc"] == 50
        assert redacted_data["power"] == 1000

    @pytest.mark.asyncio
    async def test_coordinator_data_none(self):
        """Test diagnostics when coordinator has no data."""
        coord = _mock_coordinator(None)

        entry = _mock_entry()
        entry.runtime_data = EnphaseBatteryRuntimeData(coordinator=coord)

        result = await async_get_config_entry_diagnostics(MagicMock(), entry)

        assert result["data"] is None

    @pytest.mark.asyncio
    async def test_local_api_info(self):
        """Test diagnostics includes local_api info when available."""
        coord = _mock_coordinator({"soc": 50})
        coord.local_api = MagicMock()
        coord.local_api._host = "192.168.1.100"
        coord.local_api._firmware_version = "8.2.4225"
        coord.local_api._jwt_token = "some-jwt-token"

        entry = _mock_entry()
        entry.runtime_data = EnphaseBatteryRuntimeData(coordinator=coord)

        result = await async_get_config_entry_diagnostics(MagicMock(), entry)

        assert "local_api" in result
        assert result["local_api"]["host"] == "192.168.1.100"
        assert result["local_api"]["firmware_version"] == "8.2.4225"
        assert result["local_api"]["has_token"] is True

    @pytest.mark.asyncio
    async def test_local_api_no_token(self):
        """Test local_api info when jwt_token is None."""
        coord = _mock_coordinator({"soc": 50})
        coord.local_api = MagicMock()
        coord.local_api._host = "192.168.1.100"
        coord.local_api._firmware_version = "8.2.4225"
        coord.local_api._jwt_token = None

        entry = _mock_entry()
        entry.runtime_data = EnphaseBatteryRuntimeData(coordinator=coord)

        result = await async_get_config_entry_diagnostics(MagicMock(), entry)

        assert result["local_api"]["has_token"] is False

    @pytest.mark.asyncio
    async def test_no_local_api(self):
        """Test diagnostics without local_api."""
        coord = _mock_coordinator({"soc": 50})
        coord.local_api = None

        entry = _mock_entry()
        entry.runtime_data = EnphaseBatteryRuntimeData(coordinator=coord)

        result = await async_get_config_entry_diagnostics(MagicMock(), entry)

        assert "local_api" not in result

    @pytest.mark.asyncio
    async def test_cloud_api_info(self):
        """Test diagnostics includes cloud_api info when available."""
        coord = _mock_coordinator({"soc": 50})
        coord.api = MagicMock()
        coord.api._session_token = "session-abc"
        coord.api._site_id = 12345
        coord.api._user_id = 67890

        entry = _mock_entry()
        entry.runtime_data = EnphaseBatteryRuntimeData(coordinator=coord)

        result = await async_get_config_entry_diagnostics(MagicMock(), entry)

        assert "cloud_api" in result
        assert result["cloud_api"]["authenticated"] is True
        assert result["cloud_api"]["site_id"] == "**REDACTED**"
        assert result["cloud_api"]["user_id"] == "**REDACTED**"

    @pytest.mark.asyncio
    async def test_cloud_api_not_authenticated(self):
        """Test cloud_api info when not authenticated."""
        coord = _mock_coordinator({"soc": 50})
        coord.api = MagicMock()
        coord.api._session_token = None
        coord.api._site_id = None
        coord.api._user_id = None

        entry = _mock_entry()
        entry.runtime_data = EnphaseBatteryRuntimeData(coordinator=coord)

        result = await async_get_config_entry_diagnostics(MagicMock(), entry)

        assert result["cloud_api"]["authenticated"] is False
        assert result["cloud_api"]["site_id"] is None
        assert result["cloud_api"]["user_id"] is None

    @pytest.mark.asyncio
    async def test_no_cloud_api(self):
        """Test diagnostics without cloud_api."""
        coord = _mock_coordinator({"soc": 50})
        coord.api = None

        entry = _mock_entry()
        entry.runtime_data = EnphaseBatteryRuntimeData(coordinator=coord)

        result = await async_get_config_entry_diagnostics(MagicMock(), entry)

        assert "cloud_api" not in result

    @pytest.mark.asyncio
    async def test_both_apis(self):
        """Test diagnostics with both local and cloud APIs."""
        coord = _mock_coordinator({"soc": 50})
        coord.local_api = MagicMock()
        coord.local_api._host = "192.168.1.100"
        coord.local_api._firmware_version = "8.2.4225"
        coord.local_api._jwt_token = "jwt"
        coord.api = MagicMock()
        coord.api._session_token = "session"
        coord.api._site_id = 12345
        coord.api._user_id = 67890

        entry = _mock_entry()
        entry.runtime_data = EnphaseBatteryRuntimeData(coordinator=coord)

        result = await async_get_config_entry_diagnostics(MagicMock(), entry)

        assert "local_api" in result
        assert "cloud_api" in result

    @pytest.mark.asyncio
    async def test_options_redacted(self):
        """Test that options with sensitive data are also redacted."""
        coord = _mock_coordinator({"soc": 50})

        entry = _mock_entry(options={"token": "option-token", "scan_interval": 30})
        entry.runtime_data = EnphaseBatteryRuntimeData(coordinator=coord)

        result = await async_get_config_entry_diagnostics(MagicMock(), entry)

        options = result["config_entry"]["options"]
        assert options["token"] == "**REDACTED**"
        assert options["scan_interval"] == 30

    def test_to_redact_keys(self):
        """Verify the set of keys to redact."""
        assert "password" in TO_REDACT
        assert "username" in TO_REDACT
        assert "cloud_password" in TO_REDACT
        assert "cloud_username" in TO_REDACT
        assert "serial" in TO_REDACT
        assert "serial_number" in TO_REDACT
        assert "sn" in TO_REDACT
        assert "token" in TO_REDACT
        assert "jwt_token" in TO_REDACT
        assert "session_id" in TO_REDACT
        assert "site_id" in TO_REDACT
        assert "user_id" in TO_REDACT

    @pytest.mark.asyncio
    async def test_local_mode_coordinator(self):
        """Test coordinator info shows local mode."""
        coord = _mock_coordinator({"soc": 50})
        coord.is_local_mode = True
        coord.update_interval = timedelta(seconds=10)

        entry = _mock_entry()
        entry.runtime_data = EnphaseBatteryRuntimeData(coordinator=coord)

        result = await async_get_config_entry_diagnostics(MagicMock(), entry)

        assert result["coordinator"]["is_local_mode"] is True
        assert result["coordinator"]["update_interval"] == str(timedelta(seconds=10))
