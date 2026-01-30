"""Tests for Enphase Battery integration setup."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED
from homeassistant.core import HomeAssistant
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


async def test_deferred_setup_exception_caught(
    hass: HomeAssistant,
    mock_local_config_entry: MockConfigEntry,
) -> None:
    """Test that exception in deferred setup is caught and logged."""
    mock_local_config_entry.add_to_hass(hass)

    with (
        patch("custom_components.enphase_battery.EnphaseBatteryDataUpdateCoordinator") as mock_coord_class,
    ):
        mock_coord = MagicMock()
        mock_coord._async_setup = AsyncMock(side_effect=Exception("Auth failed"))
        mock_coord.async_refresh = AsyncMock()
        mock_coord.async_config_entry_first_refresh = AsyncMock()
        mock_coord.async_shutdown = AsyncMock()
        mock_coord.data = {"soc": 50}
        mock_coord.last_update_success = True
        mock_coord_class.return_value = mock_coord

        await hass.config_entries.async_setup(mock_local_config_entry.entry_id)
        await hass.async_block_till_done()

    # Entry is loaded despite deferred setup failure (exception was caught)
    assert mock_local_config_entry.state == ConfigEntryState.LOADED
    mock_coord._async_setup.assert_called_once()
    # async_refresh should NOT be called since _async_setup raised
    mock_coord.async_refresh.assert_not_called()


async def test_setup_entry_ha_not_started(
    hass: HomeAssistant,
    mock_local_config_entry: MockConfigEntry,
) -> None:
    """Test setup when HA hasn't started yet - deferred via event listener."""
    mock_local_config_entry.add_to_hass(hass)

    with (
        patch("custom_components.enphase_battery.EnphaseBatteryDataUpdateCoordinator") as mock_coord_class,
        patch.object(hass.config_entries, "async_forward_entry_setups", new=AsyncMock()),
    ):
        mock_coord = MagicMock()
        mock_coord._async_setup = AsyncMock()
        mock_coord.async_refresh = AsyncMock()
        mock_coord.async_shutdown = AsyncMock()
        mock_coord.data = {"soc": 50}
        mock_coord.last_update_success = True
        mock_coord_class.return_value = mock_coord

        # Call async_setup_entry directly with hass.is_running patched to False
        from custom_components.enphase_battery import async_setup_entry

        with patch.object(type(hass), "is_running", new_callable=PropertyMock, return_value=False):
            result = await async_setup_entry(hass, mock_local_config_entry)

        assert result is True
        # Deferred setup not called yet (waiting for HA_STARTED event)
        mock_coord._async_setup.assert_not_called()

        # Fire HA started event to trigger deferred setup
        hass.bus.async_fire(EVENT_HOMEASSISTANT_STARTED)
        await hass.async_block_till_done()

        # Now deferred setup should have run
        mock_coord._async_setup.assert_called_once()
        mock_coord.async_refresh.assert_called_once()


async def test_reload_entry(
    hass: HomeAssistant,
    mock_local_config_entry: MockConfigEntry,
) -> None:
    """Test async_reload_entry reloads the config entry."""
    from custom_components.enphase_battery import async_reload_entry

    with patch.object(hass.config_entries, "async_reload", new=AsyncMock()) as mock_reload:
        await async_reload_entry(hass, mock_local_config_entry)
        mock_reload.assert_called_once_with(mock_local_config_entry.entry_id)
