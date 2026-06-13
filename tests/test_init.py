"""Tests for Enphase Battery integration setup."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.enphase_battery.const import (
    CONF_CONNECTION_MODE,
    CONF_ENVOY_HOST,
    CONNECTION_MODE_CLOUD,
    CONNECTION_MODE_LOCAL,
    DOMAIN,
)


@pytest.fixture
def mock_local_config_entry() -> MockConfigEntry:
    """Create a mock local config entry."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="Enphase Battery Local",
        data={
            CONF_CONNECTION_MODE: CONNECTION_MODE_LOCAL,
            CONF_ENVOY_HOST: "192.168.1.100",
            "cloud_username": "test@example.com",
            "cloud_password": "testpassword",
            "enable_cloud_control": False,
        },
        unique_id="TEST123456",
    )


@pytest.fixture
def mock_cloud_config_entry() -> MockConfigEntry:
    """Create a mock cloud config entry."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="Enphase Battery Cloud",
        data={
            CONF_CONNECTION_MODE: CONNECTION_MODE_CLOUD,
            "username": "test@example.com",
            "password": "testpassword",
        },
        unique_id="CLOUD123456",
    )


async def test_setup_entry_local(
    hass: HomeAssistant,
    mock_local_config_entry: MockConfigEntry,
) -> None:
    """Test successful setup of local config entry."""
    mock_local_config_entry.add_to_hass(hass)

    with (
        patch("custom_components.enphase_battery.EnphaseBatteryDataUpdateCoordinator") as mock_coord_class,
    ):
        mock_coord = MagicMock()
        mock_coord._async_setup = AsyncMock()
        mock_coord.async_refresh = AsyncMock()
        mock_coord.async_config_entry_first_refresh = AsyncMock()
        mock_coord.async_shutdown = AsyncMock()
        mock_coord.data = {"soc": 50}
        mock_coord.last_update_success = True
        mock_coord_class.return_value = mock_coord

        await hass.config_entries.async_setup(mock_local_config_entry.entry_id)
        await hass.async_block_till_done()

    assert mock_local_config_entry.state == ConfigEntryState.LOADED


async def test_unload_entry(
    hass: HomeAssistant,
    mock_local_config_entry: MockConfigEntry,
) -> None:
    """Test successful unload of config entry."""
    mock_local_config_entry.add_to_hass(hass)

    with (
        patch("custom_components.enphase_battery.EnphaseBatteryDataUpdateCoordinator") as mock_coord_class,
    ):
        mock_coord = MagicMock()
        mock_coord._async_setup = AsyncMock()
        mock_coord.async_refresh = AsyncMock()
        mock_coord.async_config_entry_first_refresh = AsyncMock()
        mock_coord.async_shutdown = AsyncMock()
        mock_coord.data = {"soc": 50}
        mock_coord.last_update_success = True
        mock_coord_class.return_value = mock_coord

        await hass.config_entries.async_setup(mock_local_config_entry.entry_id)
        await hass.async_block_till_done()

        assert mock_local_config_entry.state == ConfigEntryState.LOADED

        await hass.config_entries.async_unload(mock_local_config_entry.entry_id)
        await hass.async_block_till_done()

    assert mock_local_config_entry.state == ConfigEntryState.NOT_LOADED


async def test_migrate_entry_adds_connection_mode(
    hass: HomeAssistant,
) -> None:
    """Test migration adds connection_mode to old entries."""
    # Create an old-style entry without connection_mode
    old_entry = MockConfigEntry(
        domain=DOMAIN,
        title="Old Enphase Battery",
        data={
            "username": "test@example.com",
            "password": "testpassword",
        },
        unique_id="OLD123456",
    )
    old_entry.add_to_hass(hass)

    with (
        patch("custom_components.enphase_battery.EnphaseBatteryDataUpdateCoordinator") as mock_coord_class,
    ):
        mock_coord = MagicMock()
        mock_coord._async_setup = AsyncMock()
        mock_coord.async_refresh = AsyncMock()
        mock_coord.async_config_entry_first_refresh = AsyncMock()
        mock_coord.async_shutdown = AsyncMock()
        mock_coord.data = {"soc": 50}
        mock_coord.last_update_success = True
        mock_coord_class.return_value = mock_coord

        await hass.config_entries.async_setup(old_entry.entry_id)
        await hass.async_block_till_done()

    # Verify migration added connection_mode
    assert CONF_CONNECTION_MODE in old_entry.data
    assert old_entry.data[CONF_CONNECTION_MODE] == CONNECTION_MODE_CLOUD


async def test_setup_entry_not_ready_on_connection_failure(
    hass: HomeAssistant,
    mock_local_config_entry: MockConfigEntry,
) -> None:
    """Test a connection failure during first refresh raises ConfigEntryNotReady."""
    mock_local_config_entry.add_to_hass(hass)

    with (
        patch("custom_components.enphase_battery.EnphaseBatteryDataUpdateCoordinator") as mock_coord_class,
    ):
        mock_coord = MagicMock()
        mock_coord.async_config_entry_first_refresh = AsyncMock(side_effect=ConfigEntryNotReady("Envoy unreachable"))
        mock_coord.async_shutdown = AsyncMock()
        mock_coord_class.return_value = mock_coord

        await hass.config_entries.async_setup(mock_local_config_entry.entry_id)
        await hass.async_block_till_done()

    # Entry is retried (not loaded) when the first refresh fails to connect.
    assert mock_local_config_entry.state == ConfigEntryState.SETUP_RETRY
    mock_coord.async_config_entry_first_refresh.assert_awaited_once()


async def test_setup_entry_auth_failed_triggers_reauth(
    hass: HomeAssistant,
    mock_local_config_entry: MockConfigEntry,
) -> None:
    """Test an auth failure during first refresh raises ConfigEntryAuthFailed."""
    mock_local_config_entry.add_to_hass(hass)

    with (
        patch("custom_components.enphase_battery.EnphaseBatteryDataUpdateCoordinator") as mock_coord_class,
    ):
        mock_coord = MagicMock()
        mock_coord.async_config_entry_first_refresh = AsyncMock(
            side_effect=ConfigEntryAuthFailed("Invalid credentials")
        )
        mock_coord.async_shutdown = AsyncMock()
        mock_coord_class.return_value = mock_coord

        await hass.config_entries.async_setup(mock_local_config_entry.entry_id)
        await hass.async_block_till_done()

    # Auth failure puts the entry in error state and starts a reauth flow.
    assert mock_local_config_entry.state == ConfigEntryState.SETUP_ERROR
    flows = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert any(flow["context"].get("source") == "reauth" for flow in flows)


async def test_reload_entry(
    hass: HomeAssistant,
    mock_local_config_entry: MockConfigEntry,
) -> None:
    """Test async_reload_entry reloads the config entry."""
    from custom_components.enphase_battery import async_reload_entry

    with patch.object(hass.config_entries, "async_reload", new=AsyncMock()) as mock_reload:
        await async_reload_entry(hass, mock_local_config_entry)
        mock_reload.assert_called_once_with(mock_local_config_entry.entry_id)
