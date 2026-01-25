"""Fixtures for Enphase Battery tests."""

from __future__ import annotations

from collections.abc import Generator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.enphase_battery.const import (
    CONF_CONNECTION_MODE,
    CONF_ENVOY_HOST,
    CONNECTION_MODE_CLOUD,
    CONNECTION_MODE_LOCAL,
    DOMAIN,
)


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable custom integrations for all tests."""
    yield


@pytest.fixture
def mock_setup_entry() -> Generator[AsyncMock, None, None]:
    """Override async_setup_entry."""
    with patch(
        "custom_components.enphase_battery.async_setup_entry",
        return_value=True,
    ) as mock_setup:
        yield mock_setup


@pytest.fixture
def mock_local_api() -> Generator[MagicMock, None, None]:
    """Mock EnphaseEnvoyLocalAPI."""
    with patch("custom_components.enphase_battery.config_flow.EnphaseEnvoyLocalAPI") as mock_api_class:
        mock_api = MagicMock()
        mock_api.authenticate = AsyncMock()
        mock_api._get_info = AsyncMock(
            return_value={
                "device": {"sn": "TEST123456"},
                "software": {"current_version": "8.0.0"},
            }
        )
        mock_api._firmware_version = "8.0.0"
        mock_api._serial_number = "TEST123456"
        mock_api_class.return_value = mock_api
        yield mock_api


@pytest.fixture
def mock_cloud_api() -> Generator[MagicMock, None, None]:
    """Mock EnphaseBatteryAPI."""
    with patch("custom_components.enphase_battery.coordinator.EnphaseBatteryAPI") as mock_api_class:
        mock_api = MagicMock()
        mock_api.authenticate = AsyncMock()
        mock_api.get_battery_data = AsyncMock(return_value={"soc": 50})
        mock_api_class.return_value = mock_api
        yield mock_api


@pytest.fixture
def local_config_entry_data() -> dict[str, Any]:
    """Return local mode config entry data."""
    return {
        CONF_CONNECTION_MODE: CONNECTION_MODE_LOCAL,
        CONF_ENVOY_HOST: "192.168.1.100",
        "cloud_username": "test@example.com",
        "cloud_password": "testpassword",
        "enable_cloud_control": False,
    }


@pytest.fixture
def cloud_config_entry_data() -> dict[str, Any]:
    """Return cloud mode config entry data."""
    return {
        CONF_CONNECTION_MODE: CONNECTION_MODE_CLOUD,
        CONF_USERNAME: "test@example.com",
        CONF_PASSWORD: "testpassword",
    }


@pytest.fixture
def mock_coordinator() -> Generator[MagicMock, None, None]:
    """Mock EnphaseBatteryDataUpdateCoordinator."""
    with patch("custom_components.enphase_battery.EnphaseBatteryDataUpdateCoordinator") as mock_coord_class:
        mock_coord = MagicMock()
        mock_coord._async_setup = AsyncMock()
        mock_coord.async_refresh = AsyncMock()
        mock_coord.async_shutdown = AsyncMock()
        mock_coord.data = {"soc": 50, "power": 1000}
        mock_coord.last_update_success = True
        mock_coord_class.return_value = mock_coord
        yield mock_coord
