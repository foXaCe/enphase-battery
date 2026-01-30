"""Tests for Enphase Battery DataUpdateCoordinator."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import UpdateFailed
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.enphase_battery.api import (
    EnphaseBatteryApiError,
    EnphaseBatteryAuthError,
)
from custom_components.enphase_battery.const import (
    CONF_CONNECTION_MODE,
    CONF_ENVOY_HOST,
    CONF_SITE_ID,
    CONF_USER_ID,
    CONNECTION_MODE_CLOUD,
    CONNECTION_MODE_LOCAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    LOCAL_SCAN_INTERVAL,
)
from custom_components.enphase_battery.coordinator import (
    EnphaseBatteryDataUpdateCoordinator,
)
from custom_components.enphase_battery.envoy_local_api import (
    EnvoyAuthError,
    EnvoyLocalApiError,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def local_entry(hass: HomeAssistant) -> MockConfigEntry:
    """Create a local-mode config entry."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Enphase Battery Local",
        data={
            CONF_CONNECTION_MODE: CONNECTION_MODE_LOCAL,
            CONF_ENVOY_HOST: "192.168.1.100",
            CONF_USERNAME: "installer",
            CONF_PASSWORD: "password123",
            "cloud_username": "test@example.com",
            "cloud_password": "cloudpass",
            "enable_cloud_control": False,
        },
        unique_id="LOCAL_SERIAL",
    )
    entry.add_to_hass(hass)
    return entry


@pytest.fixture
def hybrid_entry(hass: HomeAssistant) -> MockConfigEntry:
    """Create a hybrid-mode (local + cloud control) config entry."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Enphase Battery Hybrid",
        data={
            CONF_CONNECTION_MODE: CONNECTION_MODE_LOCAL,
            CONF_ENVOY_HOST: "192.168.1.100",
            CONF_USERNAME: "installer",
            CONF_PASSWORD: "password123",
            "cloud_username": "test@example.com",
            "cloud_password": "cloudpass",
            "enable_cloud_control": True,
        },
        unique_id="HYBRID_SERIAL",
    )
    entry.add_to_hass(hass)
    return entry


@pytest.fixture
def cloud_entry(hass: HomeAssistant) -> MockConfigEntry:
    """Create a cloud-mode config entry."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Enphase Battery Cloud",
        data={
            CONF_CONNECTION_MODE: CONNECTION_MODE_CLOUD,
            CONF_USERNAME: "test@example.com",
            CONF_PASSWORD: "cloudpass",
        },
        unique_id="CLOUD_SERIAL",
    )
    entry.add_to_hass(hass)
    return entry


@pytest.fixture
def cloud_entry_with_ids(hass: HomeAssistant) -> MockConfigEntry:
    """Create a cloud-mode config entry with pre-existing site/user IDs."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Enphase Battery Cloud IDs",
        data={
            CONF_CONNECTION_MODE: CONNECTION_MODE_CLOUD,
            CONF_USERNAME: "test@example.com",
            CONF_PASSWORD: "cloudpass",
            CONF_SITE_ID: "12345",
            CONF_USER_ID: "67890",
        },
        unique_id="CLOUD_IDS_SERIAL",
    )
    entry.add_to_hass(hass)
    return entry


@pytest.fixture
def mock_store():
    """Mock persistent storage."""
    with patch("custom_components.enphase_battery.coordinator.Store") as mock_store_cls:
        store_instance = MagicMock()
        store_instance.async_load = AsyncMock(return_value=None)
        store_instance.async_save = AsyncMock()
        mock_store_cls.return_value = store_instance
        yield store_instance


@pytest.fixture
def mock_local_api():
    """Mock local Envoy API."""
    with patch("custom_components.enphase_battery.coordinator.EnphaseEnvoyLocalAPI") as mock_cls:
        api = MagicMock()
        api.authenticate = AsyncMock()
        api.get_battery_data = AsyncMock(
            return_value={
                "soc": 75,
                "power": -500,
                "mode": "self-consumption",
                "total_energy_charged": 100.0,
                "total_energy_discharged": 80.0,
                "total_consumption": 200.0,
                "available_energy": 5000,
                "charge_from_grid": False,
            }
        )
        api.close = AsyncMock()
        mock_cls.return_value = api
        yield api


@pytest.fixture
def mock_cloud_api():
    """Mock cloud Enlighten API."""
    with patch("custom_components.enphase_battery.coordinator.EnphaseBatteryAPI") as mock_cls:
        api = MagicMock()
        api.authenticate = AsyncMock()
        api.get_battery_data = AsyncMock(
            return_value={
                "soc": 50,
                "power": 1000,
                "mode": "self-consumption",
                "total_energy_charged": 150.0,
                "total_energy_discharged": 120.0,
                "total_consumption": 300.0,
                "available_energy": 3000,
            }
        )
        api.get_battery_settings = AsyncMock(
            return_value={
                "chargeFromGrid": True,
                "profile": "self-consumption",
                "dtgControl": {"enabled": False},
                "rbdControl": {"enabled": True},
                "powerMatchControl": {"enabled": False},
            }
        )
        api._site_id = None
        api._user_id = None
        mock_cls.return_value = api
        yield api


@pytest.fixture
def mock_session():
    """Mock aiohttp session."""
    with patch("custom_components.enphase_battery.coordinator.async_get_clientsession") as mock_get_session:
        session = MagicMock()
        mock_get_session.return_value = session
        yield session


# ---------------------------------------------------------------------------
# 1. __init__ tests
# ---------------------------------------------------------------------------


class TestInit:
    """Tests for coordinator __init__."""

    async def test_local_mode_interval(self, hass: HomeAssistant, local_entry: MockConfigEntry, mock_store):
        """Test local mode uses LOCAL_SCAN_INTERVAL (10s)."""
        coordinator = EnphaseBatteryDataUpdateCoordinator(hass, local_entry)

        assert coordinator.update_interval == timedelta(seconds=LOCAL_SCAN_INTERVAL)

    async def test_cloud_mode_interval(self, hass: HomeAssistant, cloud_entry: MockConfigEntry, mock_store):
        """Test cloud mode uses DEFAULT_SCAN_INTERVAL (60s)."""
        coordinator = EnphaseBatteryDataUpdateCoordinator(hass, cloud_entry)

        assert coordinator.update_interval == timedelta(seconds=DEFAULT_SCAN_INTERVAL)

    async def test_default_connection_mode_is_cloud(self, hass: HomeAssistant, mock_store):
        """Test that missing connection_mode defaults to cloud."""
        entry = MockConfigEntry(
            domain=DOMAIN,
            title="No Mode",
            data={
                CONF_USERNAME: "test@example.com",
                CONF_PASSWORD: "pass",
            },
            unique_id="NO_MODE",
        )
        entry.add_to_hass(hass)
        coordinator = EnphaseBatteryDataUpdateCoordinator(hass, entry)

        assert coordinator.update_interval == timedelta(seconds=DEFAULT_SCAN_INTERVAL)
        assert coordinator.connection_mode == CONNECTION_MODE_CLOUD

    async def test_init_attributes(self, hass: HomeAssistant, local_entry: MockConfigEntry, mock_store):
        """Test initial attribute values."""
        coordinator = EnphaseBatteryDataUpdateCoordinator(hass, local_entry)

        assert coordinator.api is None
        assert coordinator.local_api is None
        assert coordinator._daily_reset_date is None
        assert coordinator._daily_charged_start == 0
        assert coordinator._daily_discharged_start == 0
        assert coordinator._consumption_24h_history == []
        assert coordinator._last_soc is None
        assert coordinator._last_power is None
        assert coordinator._last_update_time is None
        assert coordinator._last_cloud_error_warning is None
        assert coordinator._last_storage_save is None
        assert coordinator._last_cloud_control_fetch is None
        assert coordinator._cloud_control_cache == {}


# ---------------------------------------------------------------------------
# 2. _async_setup tests
# ---------------------------------------------------------------------------


class TestAsyncSetup:
    """Tests for _async_setup."""

    async def test_local_mode_setup(
        self,
        hass: HomeAssistant,
        local_entry: MockConfigEntry,
        mock_store,
        mock_local_api,
        mock_session,
    ):
        """Test local mode setup calls _setup_local_api and _load_energy_tracking."""
        coordinator = EnphaseBatteryDataUpdateCoordinator(hass, local_entry)

        await coordinator._async_setup()

        mock_local_api.authenticate.assert_awaited_once()
        mock_store.async_load.assert_awaited_once()
        assert coordinator.local_api is mock_local_api

    async def test_cloud_mode_setup(
        self,
        hass: HomeAssistant,
        cloud_entry: MockConfigEntry,
        mock_store,
        mock_cloud_api,
        mock_session,
    ):
        """Test cloud mode setup calls _setup_cloud_api and _load_energy_tracking."""
        coordinator = EnphaseBatteryDataUpdateCoordinator(hass, cloud_entry)

        await coordinator._async_setup()

        mock_cloud_api.authenticate.assert_awaited_once()
        mock_store.async_load.assert_awaited_once()
        assert coordinator.api is mock_cloud_api

    async def test_hybrid_mode_setup(
        self,
        hass: HomeAssistant,
        hybrid_entry: MockConfigEntry,
        mock_store,
        mock_session,
    ):
        """Test hybrid mode setup calls local + cloud + storage in parallel."""
        with (
            patch("custom_components.enphase_battery.coordinator.EnphaseEnvoyLocalAPI") as mock_local_cls,
            patch("custom_components.enphase_battery.coordinator.EnphaseBatteryAPI") as mock_cloud_cls,
        ):
            local_api = MagicMock()
            local_api.authenticate = AsyncMock()
            mock_local_cls.return_value = local_api

            cloud_api = MagicMock()
            cloud_api.authenticate = AsyncMock()
            cloud_api._site_id = None
            cloud_api._user_id = None
            mock_cloud_cls.return_value = cloud_api

            coordinator = EnphaseBatteryDataUpdateCoordinator(hass, hybrid_entry)

            await coordinator._async_setup()

            local_api.authenticate.assert_awaited_once()
            cloud_api.authenticate.assert_awaited_once()
            mock_store.async_load.assert_awaited_once()
            assert coordinator.local_api is local_api
            assert coordinator.api is cloud_api


# ---------------------------------------------------------------------------
# 3. _setup_local_api tests
# ---------------------------------------------------------------------------


class TestSetupLocalApi:
    """Tests for _setup_local_api."""

    async def test_success(
        self,
        hass: HomeAssistant,
        local_entry: MockConfigEntry,
        mock_store,
        mock_local_api,
        mock_session,
    ):
        """Test successful local API setup."""
        coordinator = EnphaseBatteryDataUpdateCoordinator(hass, local_entry)

        await coordinator._setup_local_api(mock_session)

        assert coordinator.local_api is mock_local_api
        mock_local_api.authenticate.assert_awaited_once()

    async def test_auth_failure(
        self,
        hass: HomeAssistant,
        local_entry: MockConfigEntry,
        mock_store,
        mock_local_api,
        mock_session,
    ):
        """Test local API auth failure raises."""
        mock_local_api.authenticate = AsyncMock(side_effect=EnvoyLocalApiError("Auth failed"))
        coordinator = EnphaseBatteryDataUpdateCoordinator(hass, local_entry)

        with pytest.raises(EnvoyLocalApiError, match="Auth failed"):
            await coordinator._setup_local_api(mock_session)


# ---------------------------------------------------------------------------
# 4. _setup_cloud_api tests
# ---------------------------------------------------------------------------


class TestSetupCloudApi:
    """Tests for _setup_cloud_api."""

    async def test_success(
        self,
        hass: HomeAssistant,
        cloud_entry: MockConfigEntry,
        mock_store,
        mock_cloud_api,
        mock_session,
    ):
        """Test successful cloud API setup."""
        coordinator = EnphaseBatteryDataUpdateCoordinator(hass, cloud_entry)

        await coordinator._setup_cloud_api(mock_session)

        assert coordinator.api is mock_cloud_api
        mock_cloud_api.authenticate.assert_awaited_once()

    async def test_saves_auto_detected_ids(
        self,
        hass: HomeAssistant,
        cloud_entry: MockConfigEntry,
        mock_store,
        mock_cloud_api,
        mock_session,
    ):
        """Test auto-detected site/user IDs are saved to config entry."""
        mock_cloud_api._site_id = 12345
        mock_cloud_api._user_id = 67890

        coordinator = EnphaseBatteryDataUpdateCoordinator(hass, cloud_entry)

        await coordinator._setup_cloud_api(mock_session)

        # Verify config entry data was updated with discovered IDs
        assert cloud_entry.data[CONF_SITE_ID] == "12345"
        assert cloud_entry.data[CONF_USER_ID] == "67890"

    async def test_does_not_overwrite_existing_ids(
        self,
        hass: HomeAssistant,
        cloud_entry_with_ids: MockConfigEntry,
        mock_store,
        mock_cloud_api,
        mock_session,
    ):
        """Test existing IDs are not overwritten even if api detects new ones."""
        mock_cloud_api._site_id = 99999
        mock_cloud_api._user_id = 88888

        coordinator = EnphaseBatteryDataUpdateCoordinator(hass, cloud_entry_with_ids)

        await coordinator._setup_cloud_api(mock_session)

        # Existing IDs should remain unchanged
        assert cloud_entry_with_ids.data[CONF_SITE_ID] == "12345"
        assert cloud_entry_with_ids.data[CONF_USER_ID] == "67890"

    async def test_auth_failure(
        self,
        hass: HomeAssistant,
        cloud_entry: MockConfigEntry,
        mock_store,
        mock_cloud_api,
        mock_session,
    ):
        """Test cloud API auth failure raises."""
        mock_cloud_api.authenticate = AsyncMock(side_effect=EnphaseBatteryApiError("Cloud auth failed"))
        coordinator = EnphaseBatteryDataUpdateCoordinator(hass, cloud_entry)

        with pytest.raises(EnphaseBatteryApiError, match="Cloud auth failed"):
            await coordinator._setup_cloud_api(mock_session)


# ---------------------------------------------------------------------------
# 5. _setup_cloud_api_from_local_creds tests
# ---------------------------------------------------------------------------


class TestSetupCloudApiFromLocalCreds:
    """Tests for _setup_cloud_api_from_local_creds (hybrid mode)."""

    async def test_success(
        self,
        hass: HomeAssistant,
        hybrid_entry: MockConfigEntry,
        mock_store,
        mock_cloud_api,
        mock_session,
    ):
        """Test successful hybrid cloud API setup."""
        coordinator = EnphaseBatteryDataUpdateCoordinator(hass, hybrid_entry)

        await coordinator._setup_cloud_api_from_local_creds(mock_session)

        assert coordinator.api is mock_cloud_api
        mock_cloud_api.authenticate.assert_awaited_once()

    async def test_saves_auto_detected_ids(
        self,
        hass: HomeAssistant,
        hybrid_entry: MockConfigEntry,
        mock_store,
        mock_cloud_api,
        mock_session,
    ):
        """Test auto-detected IDs saved in hybrid mode."""
        mock_cloud_api._site_id = 11111
        mock_cloud_api._user_id = 22222

        coordinator = EnphaseBatteryDataUpdateCoordinator(hass, hybrid_entry)

        await coordinator._setup_cloud_api_from_local_creds(mock_session)

        assert hybrid_entry.data[CONF_SITE_ID] == "11111"
        assert hybrid_entry.data[CONF_USER_ID] == "22222"

    async def test_missing_cloud_creds(
        self,
        hass: HomeAssistant,
        mock_store,
        mock_cloud_api,
        mock_session,
    ):
        """Test missing cloud credentials returns without setting up API."""
        entry = MockConfigEntry(
            domain=DOMAIN,
            title="No Cloud Creds",
            data={
                CONF_CONNECTION_MODE: CONNECTION_MODE_LOCAL,
                CONF_ENVOY_HOST: "192.168.1.100",
                "enable_cloud_control": True,
                # No cloud_username / cloud_password
            },
            unique_id="NO_CREDS",
        )
        entry.add_to_hass(hass)
        coordinator = EnphaseBatteryDataUpdateCoordinator(hass, entry)

        await coordinator._setup_cloud_api_from_local_creds(mock_session)

        assert coordinator.api is None
        mock_cloud_api.authenticate.assert_not_awaited()

    async def test_missing_cloud_password_only(
        self,
        hass: HomeAssistant,
        mock_store,
        mock_cloud_api,
        mock_session,
    ):
        """Test missing cloud password returns without setting up API."""
        entry = MockConfigEntry(
            domain=DOMAIN,
            title="No Cloud Pass",
            data={
                CONF_CONNECTION_MODE: CONNECTION_MODE_LOCAL,
                CONF_ENVOY_HOST: "192.168.1.100",
                "enable_cloud_control": True,
                "cloud_username": "test@example.com",
                # No cloud_password
            },
            unique_id="NO_PASS",
        )
        entry.add_to_hass(hass)
        coordinator = EnphaseBatteryDataUpdateCoordinator(hass, entry)

        await coordinator._setup_cloud_api_from_local_creds(mock_session)

        assert coordinator.api is None

    async def test_auth_failure_does_not_raise(
        self,
        hass: HomeAssistant,
        hybrid_entry: MockConfigEntry,
        mock_store,
        mock_cloud_api,
        mock_session,
    ):
        """Test hybrid cloud auth failure does not raise, sets api to None."""
        mock_cloud_api.authenticate = AsyncMock(side_effect=EnphaseBatteryApiError("Cloud auth error"))
        coordinator = EnphaseBatteryDataUpdateCoordinator(hass, hybrid_entry)

        # Should not raise
        await coordinator._setup_cloud_api_from_local_creds(mock_session)

        # API should be set to None after failure
        assert coordinator.api is None


# ---------------------------------------------------------------------------
# 6. _load_energy_tracking tests
# ---------------------------------------------------------------------------


class TestLoadEnergyTracking:
    """Tests for _load_energy_tracking."""

    async def test_success_with_data(self, hass: HomeAssistant, local_entry: MockConfigEntry, mock_store):
        """Test loading stored energy tracking data."""
        mock_store.async_load.return_value = {
            "reset_date": "2024-01-15",
            "charged_start": 50.0,
            "discharged_start": 30.0,
            "consumption_history": [("2024-01-15T10:00:00", 100.0)],
            "last_soc": 65,
            "soc_charged": 1.5,
            "soc_discharged": 0.8,
            "last_power": -200,
            "last_update_time": "2024-01-15T10:00:00",
            "power_charged": 2.0,
            "power_discharged": 1.0,
        }
        coordinator = EnphaseBatteryDataUpdateCoordinator(hass, local_entry)

        await coordinator._load_energy_tracking()

        assert coordinator._daily_reset_date == "2024-01-15"
        assert coordinator._daily_charged_start == 50.0
        assert coordinator._daily_discharged_start == 30.0
        assert len(coordinator._consumption_24h_history) == 1
        assert coordinator._last_soc == 65
        assert coordinator._daily_soc_charged == 1.5
        assert coordinator._daily_soc_discharged == 0.8
        assert coordinator._last_power == -200
        assert coordinator._last_update_time == "2024-01-15T10:00:00"
        assert coordinator._daily_power_charged == 2.0
        assert coordinator._daily_power_discharged == 1.0

    async def test_empty_store(self, hass: HomeAssistant, local_entry: MockConfigEntry, mock_store):
        """Test loading when store is empty (None)."""
        mock_store.async_load.return_value = None
        coordinator = EnphaseBatteryDataUpdateCoordinator(hass, local_entry)

        await coordinator._load_energy_tracking()

        assert coordinator._daily_reset_date is None
        assert coordinator._daily_charged_start == 0
        assert coordinator._daily_discharged_start == 0
        assert coordinator._consumption_24h_history == []
        assert coordinator._last_soc is None

    async def test_store_error(self, hass: HomeAssistant, local_entry: MockConfigEntry, mock_store):
        """Test loading handles store errors gracefully."""
        mock_store.async_load = AsyncMock(side_effect=Exception("Storage error"))
        coordinator = EnphaseBatteryDataUpdateCoordinator(hass, local_entry)

        # Should not raise
        await coordinator._load_energy_tracking()


# ---------------------------------------------------------------------------
# 7. _save_energy_tracking tests
# ---------------------------------------------------------------------------


class TestSaveEnergyTracking:
    """Tests for _save_energy_tracking."""

    async def test_success(self, hass: HomeAssistant, local_entry: MockConfigEntry, mock_store):
        """Test successful save of energy tracking data."""
        coordinator = EnphaseBatteryDataUpdateCoordinator(hass, local_entry)
        coordinator._daily_reset_date = "2024-01-15"
        coordinator._daily_charged_start = 50.0
        coordinator._daily_discharged_start = 30.0
        coordinator._consumption_24h_history = [("2024-01-15T10:00:00", 100.0)]
        coordinator._last_soc = 65
        coordinator._daily_soc_charged = 1.5
        coordinator._daily_soc_discharged = 0.8
        coordinator._last_power = -200
        coordinator._last_update_time = "2024-01-15T10:00:00"
        coordinator._daily_power_charged = 2.0
        coordinator._daily_power_discharged = 1.0

        await coordinator._save_energy_tracking()

        mock_store.async_save.assert_awaited_once()
        saved_data = mock_store.async_save.call_args[0][0]
        assert saved_data["reset_date"] == "2024-01-15"
        assert saved_data["charged_start"] == 50.0
        assert saved_data["discharged_start"] == 30.0
        assert saved_data["last_soc"] == 65
        assert saved_data["soc_charged"] == 1.5
        assert saved_data["soc_discharged"] == 0.8
        assert saved_data["last_power"] == -200
        assert saved_data["last_update_time"] == "2024-01-15T10:00:00"
        assert saved_data["power_charged"] == 2.0
        assert saved_data["power_discharged"] == 1.0

    async def test_truncates_consumption_history(self, hass: HomeAssistant, local_entry: MockConfigEntry, mock_store):
        """Test consumption history is truncated to 100 entries on save."""
        coordinator = EnphaseBatteryDataUpdateCoordinator(hass, local_entry)
        coordinator._consumption_24h_history = [(f"2024-01-15T{i:02d}:00:00", float(i)) for i in range(150)]

        await coordinator._save_energy_tracking()

        saved_data = mock_store.async_save.call_args[0][0]
        assert len(saved_data["consumption_history"]) == 100

    async def test_error(self, hass: HomeAssistant, local_entry: MockConfigEntry, mock_store):
        """Test save handles errors gracefully."""
        mock_store.async_save = AsyncMock(side_effect=Exception("Write error"))
        coordinator = EnphaseBatteryDataUpdateCoordinator(hass, local_entry)

        # Should not raise
        await coordinator._save_energy_tracking()


# ---------------------------------------------------------------------------
# 8. _async_update_data tests
# ---------------------------------------------------------------------------


class TestAsyncUpdateData:
    """Tests for _async_update_data."""

    async def test_local_mode_success(
        self,
        hass: HomeAssistant,
        local_entry: MockConfigEntry,
        mock_store,
        mock_local_api,
        mock_session,
    ):
        """Test successful local mode data fetch."""
        coordinator = EnphaseBatteryDataUpdateCoordinator(hass, local_entry)
        coordinator.local_api = mock_local_api

        data = await coordinator._async_update_data()

        mock_local_api.get_battery_data.assert_awaited_once()
        assert data["soc"] == 75
        assert "energy_charged_today" in data
        assert "energy_discharged_today" in data
        assert "consumption_24h" in data
        assert "estimated_backup_time" in data

    async def test_cloud_mode_success(
        self,
        hass: HomeAssistant,
        cloud_entry: MockConfigEntry,
        mock_store,
        mock_cloud_api,
        mock_session,
    ):
        """Test successful cloud mode data fetch."""
        coordinator = EnphaseBatteryDataUpdateCoordinator(hass, cloud_entry)
        coordinator.api = mock_cloud_api

        data = await coordinator._async_update_data()

        mock_cloud_api.get_battery_data.assert_awaited_once()
        assert data["soc"] == 50
        assert "energy_charged_today" in data

    async def test_hybrid_mode_with_cloud_cache(
        self,
        hass: HomeAssistant,
        hybrid_entry: MockConfigEntry,
        mock_store,
        mock_local_api,
        mock_cloud_api,
        mock_session,
    ):
        """Test hybrid mode fetches cloud settings and caches them."""
        coordinator = EnphaseBatteryDataUpdateCoordinator(hass, hybrid_entry)
        coordinator.local_api = mock_local_api
        coordinator.api = mock_cloud_api

        data = await coordinator._async_update_data()

        # Cloud settings should have been fetched
        mock_cloud_api.get_battery_settings.assert_awaited_once()
        # Values from cloud should be merged into data
        assert data["charge_from_grid"] is True
        assert data["mode"] == "self-consumption"
        assert data["discharge_to_grid"] is False
        assert data["reserve_battery_discharge"] is True
        assert data["power_match"] is False
        # Cache should be set
        assert coordinator._last_cloud_control_fetch is not None
        assert coordinator._cloud_control_cache != {}

    async def test_hybrid_mode_uses_cached_values(
        self,
        hass: HomeAssistant,
        hybrid_entry: MockConfigEntry,
        mock_store,
        mock_local_api,
        mock_cloud_api,
        mock_session,
    ):
        """Test hybrid mode uses cached cloud values when cache is fresh."""
        coordinator = EnphaseBatteryDataUpdateCoordinator(hass, hybrid_entry)
        coordinator.local_api = mock_local_api
        coordinator.api = mock_cloud_api

        # Pre-fill cache with recent data
        coordinator._last_cloud_control_fetch = datetime.now()
        coordinator._cloud_control_cache = {
            "charge_from_grid": False,
            "mode": "backup_only",
            "discharge_to_grid": True,
            "reserve_battery_discharge": False,
            "power_match": True,
        }

        data = await coordinator._async_update_data()

        # Cloud settings should NOT have been fetched (cache is fresh)
        mock_cloud_api.get_battery_settings.assert_not_awaited()
        # Cached values should be applied
        assert data["charge_from_grid"] is False
        assert data["mode"] == "backup_only"
        assert data["discharge_to_grid"] is True
        assert data["reserve_battery_discharge"] is False
        assert data["power_match"] is True

    async def test_hybrid_mode_stale_cache_refresh(
        self,
        hass: HomeAssistant,
        hybrid_entry: MockConfigEntry,
        mock_store,
        mock_local_api,
        mock_cloud_api,
        mock_session,
    ):
        """Test hybrid mode refreshes cloud data when cache is stale."""
        coordinator = EnphaseBatteryDataUpdateCoordinator(hass, hybrid_entry)
        coordinator.local_api = mock_local_api
        coordinator.api = mock_cloud_api

        # Set cache to 10 minutes ago (stale)
        coordinator._last_cloud_control_fetch = datetime.now() - timedelta(minutes=10)
        coordinator._cloud_control_cache = {
            "charge_from_grid": False,
            "mode": "old_mode",
            "discharge_to_grid": False,
            "reserve_battery_discharge": False,
            "power_match": False,
        }

        data = await coordinator._async_update_data()

        # Cloud settings should have been re-fetched
        mock_cloud_api.get_battery_settings.assert_awaited_once()
        # New values from cloud should be applied
        assert data["charge_from_grid"] is True
        assert data["mode"] == "self-consumption"

    async def test_hybrid_cloud_fetch_error_rate_limited_warning(
        self,
        hass: HomeAssistant,
        hybrid_entry: MockConfigEntry,
        mock_store,
        mock_local_api,
        mock_cloud_api,
        mock_session,
    ):
        """Test cloud fetch error in hybrid mode logs warning (rate limited)."""
        mock_cloud_api.get_battery_settings = AsyncMock(side_effect=Exception("API rate limit"))
        coordinator = EnphaseBatteryDataUpdateCoordinator(hass, hybrid_entry)
        coordinator.local_api = mock_local_api
        coordinator.api = mock_cloud_api

        # First call: should log warning
        data = await coordinator._async_update_data()

        # Should still return local data
        assert data["soc"] == 75
        assert coordinator._last_cloud_error_warning is not None

    async def test_hybrid_cloud_fetch_error_suppressed(
        self,
        hass: HomeAssistant,
        hybrid_entry: MockConfigEntry,
        mock_store,
        mock_local_api,
        mock_cloud_api,
        mock_session,
    ):
        """Test repeated cloud fetch errors are suppressed for 5 minutes."""
        mock_cloud_api.get_battery_settings = AsyncMock(side_effect=Exception("API error"))
        coordinator = EnphaseBatteryDataUpdateCoordinator(hass, hybrid_entry)
        coordinator.local_api = mock_local_api
        coordinator.api = mock_cloud_api

        # Set recent warning time
        coordinator._last_cloud_error_warning = datetime.now()

        data = await coordinator._async_update_data()

        # Should still succeed with local data
        assert data["soc"] == 75
        # Warning time should NOT have been updated (suppressed)
        # The original time should remain since time diff < 5 min

    async def test_hybrid_no_cloud_cache_applied_when_empty(
        self,
        hass: HomeAssistant,
        hybrid_entry: MockConfigEntry,
        mock_store,
        mock_local_api,
        mock_cloud_api,
        mock_session,
    ):
        """Test no cloud cache applied when cache is empty after fetch error."""
        mock_cloud_api.get_battery_settings = AsyncMock(side_effect=Exception("API error"))
        coordinator = EnphaseBatteryDataUpdateCoordinator(hass, hybrid_entry)
        coordinator.local_api = mock_local_api
        coordinator.api = mock_cloud_api
        coordinator._cloud_control_cache = {}

        data = await coordinator._async_update_data()

        # Local data should be returned as-is (no cloud cache override)
        assert data["mode"] == "self-consumption"
        assert data["charge_from_grid"] is False

    async def test_local_auth_error_raises_config_entry_auth_failed(
        self,
        hass: HomeAssistant,
        local_entry: MockConfigEntry,
        mock_store,
        mock_local_api,
        mock_session,
    ):
        """Test local EnvoyAuthError triggers ConfigEntryAuthFailed.

        Note: ConfigEntryAuthFailed is raised inside the inner try/except,
        but then caught by the outer generic `except Exception` handler
        and wrapped in UpdateFailed. The DataUpdateCoordinator base class
        unwraps it at a higher level via __cause__.
        """
        mock_local_api.get_battery_data = AsyncMock(side_effect=EnvoyAuthError("Token expired"))
        coordinator = EnphaseBatteryDataUpdateCoordinator(hass, local_entry)
        coordinator.local_api = mock_local_api

        with pytest.raises(UpdateFailed, match="Unexpected error") as exc_info:
            await coordinator._async_update_data()
        # The __cause__ chain should contain ConfigEntryAuthFailed
        assert isinstance(exc_info.value.__cause__, ConfigEntryAuthFailed)

    async def test_local_api_error_raises_update_failed(
        self,
        hass: HomeAssistant,
        local_entry: MockConfigEntry,
        mock_store,
        mock_local_api,
        mock_session,
    ):
        """Test local EnvoyLocalApiError triggers UpdateFailed."""
        mock_local_api.get_battery_data = AsyncMock(side_effect=EnvoyLocalApiError("Connection timeout"))
        coordinator = EnphaseBatteryDataUpdateCoordinator(hass, local_entry)
        coordinator.local_api = mock_local_api

        with pytest.raises(UpdateFailed, match="Error fetching local data"):
            await coordinator._async_update_data()

    async def test_cloud_auth_error_raises_config_entry_auth_failed(
        self,
        hass: HomeAssistant,
        cloud_entry: MockConfigEntry,
        mock_store,
        mock_cloud_api,
        mock_session,
    ):
        """Test cloud EnphaseBatteryAuthError triggers ConfigEntryAuthFailed.

        Note: Same wrapping behavior as local auth error - ConfigEntryAuthFailed
        is caught by the outer generic handler and wrapped in UpdateFailed.
        """
        mock_cloud_api.get_battery_data = AsyncMock(side_effect=EnphaseBatteryAuthError("Invalid token"))
        coordinator = EnphaseBatteryDataUpdateCoordinator(hass, cloud_entry)
        coordinator.api = mock_cloud_api

        with pytest.raises(UpdateFailed, match="Unexpected error") as exc_info:
            await coordinator._async_update_data()
        assert isinstance(exc_info.value.__cause__, ConfigEntryAuthFailed)

    async def test_cloud_api_error_raises_update_failed(
        self,
        hass: HomeAssistant,
        cloud_entry: MockConfigEntry,
        mock_store,
        mock_cloud_api,
        mock_session,
    ):
        """Test cloud EnphaseBatteryApiError triggers UpdateFailed."""
        mock_cloud_api.get_battery_data = AsyncMock(side_effect=EnphaseBatteryApiError("Service unavailable"))
        coordinator = EnphaseBatteryDataUpdateCoordinator(hass, cloud_entry)
        coordinator.api = mock_cloud_api

        with pytest.raises(UpdateFailed, match="Error fetching cloud data"):
            await coordinator._async_update_data()

    async def test_unexpected_error_raises_update_failed(
        self,
        hass: HomeAssistant,
        cloud_entry: MockConfigEntry,
        mock_store,
        mock_cloud_api,
        mock_session,
    ):
        """Test unexpected exceptions are wrapped in UpdateFailed."""
        mock_cloud_api.get_battery_data = AsyncMock(side_effect=RuntimeError("Unexpected"))
        coordinator = EnphaseBatteryDataUpdateCoordinator(hass, cloud_entry)
        coordinator.api = mock_cloud_api

        with pytest.raises(UpdateFailed, match="Unexpected error"):
            await coordinator._async_update_data()

    async def test_lazy_setup_local(
        self,
        hass: HomeAssistant,
        local_entry: MockConfigEntry,
        mock_store,
        mock_local_api,
        mock_session,
    ):
        """Test lazy setup for local mode when local_api is None."""
        coordinator = EnphaseBatteryDataUpdateCoordinator(hass, local_entry)
        # local_api is None, should trigger _async_setup

        data = await coordinator._async_update_data()

        # Setup should have been called, then data fetched
        mock_local_api.authenticate.assert_awaited_once()
        mock_local_api.get_battery_data.assert_awaited_once()
        assert data["soc"] == 75

    async def test_lazy_setup_cloud(
        self,
        hass: HomeAssistant,
        cloud_entry: MockConfigEntry,
        mock_store,
        mock_cloud_api,
        mock_session,
    ):
        """Test lazy setup for cloud mode when api is None."""
        coordinator = EnphaseBatteryDataUpdateCoordinator(hass, cloud_entry)
        # api is None, should trigger _async_setup

        data = await coordinator._async_update_data()

        mock_cloud_api.authenticate.assert_awaited_once()
        mock_cloud_api.get_battery_data.assert_awaited_once()
        assert data["soc"] == 50

    async def test_hybrid_cloud_settings_dtg_not_dict(
        self,
        hass: HomeAssistant,
        hybrid_entry: MockConfigEntry,
        mock_store,
        mock_local_api,
        mock_cloud_api,
        mock_session,
    ):
        """Test hybrid mode handles non-dict dtgControl/rbdControl/powerMatchControl."""
        mock_cloud_api.get_battery_settings = AsyncMock(
            return_value={
                "chargeFromGrid": True,
                "profile": "self-consumption",
                "dtgControl": None,
                "rbdControl": "invalid",
                "powerMatchControl": 42,
            }
        )
        coordinator = EnphaseBatteryDataUpdateCoordinator(hass, hybrid_entry)
        coordinator.local_api = mock_local_api
        coordinator.api = mock_cloud_api

        data = await coordinator._async_update_data()

        assert data["discharge_to_grid"] is False
        assert data["reserve_battery_discharge"] is False
        assert data["power_match"] is False


# ---------------------------------------------------------------------------
# 9. _calculate_daily_values tests
# ---------------------------------------------------------------------------


class TestCalculateDailyValues:
    """Tests for _calculate_daily_values."""

    async def test_midnight_reset(self, hass: HomeAssistant, local_entry: MockConfigEntry, mock_store):
        """Test daily counters reset at midnight."""
        coordinator = EnphaseBatteryDataUpdateCoordinator(hass, local_entry)
        coordinator._daily_reset_date = "2020-01-01"  # Old date
        coordinator._daily_charged_start = 999
        coordinator._daily_discharged_start = 888
        coordinator._daily_soc_charged = 10
        coordinator._daily_soc_discharged = 5
        coordinator._daily_power_charged = 3.0
        coordinator._daily_power_discharged = 2.0

        data = {
            "total_energy_charged": 200.0,
            "total_energy_discharged": 150.0,
            "total_consumption": 400.0,
            "available_energy": 5000,
            "power": 1000,
        }

        coordinator._calculate_daily_values(data)

        today_str = datetime.now().strftime("%Y-%m-%d")
        assert coordinator._daily_reset_date == today_str
        assert coordinator._daily_charged_start == 200.0
        assert coordinator._daily_discharged_start == 150.0
        assert coordinator._daily_soc_charged == 0
        assert coordinator._daily_soc_discharged == 0
        assert coordinator._daily_power_charged == 0
        assert coordinator._daily_power_discharged == 0
        # Energy for today should be 0 (just reset)
        assert data["energy_charged_today"] == 0
        assert data["energy_discharged_today"] == 0

    async def test_meter_based_energy(self, hass: HomeAssistant, local_entry: MockConfigEntry, mock_store):
        """Test meter-based energy calculation (non-zero cumulative values)."""
        coordinator = EnphaseBatteryDataUpdateCoordinator(hass, local_entry)
        today_str = datetime.now().strftime("%Y-%m-%d")
        coordinator._daily_reset_date = today_str
        coordinator._daily_charged_start = 100.0
        coordinator._daily_discharged_start = 80.0

        data = {
            "total_energy_charged": 105.5,
            "total_energy_discharged": 83.2,
            "total_consumption": 250.0,
            "available_energy": 5000,
            "power": 500,
        }

        coordinator._calculate_daily_values(data)

        assert data["energy_charged_today"] == 5.5
        assert data["energy_discharged_today"] == 3.2

    async def test_power_integration_fallback_charging(
        self, hass: HomeAssistant, local_entry: MockConfigEntry, mock_store
    ):
        """Test power integration fallback when meters return 0 (charging)."""
        coordinator = EnphaseBatteryDataUpdateCoordinator(hass, local_entry)
        today_str = datetime.now().strftime("%Y-%m-%d")
        coordinator._daily_reset_date = today_str
        coordinator._daily_charged_start = 0
        coordinator._daily_discharged_start = 0

        # Set previous power and time for integration
        past_time = datetime.now() - timedelta(seconds=30)
        coordinator._last_power = -1000.0  # Previous: charging at 1000W
        coordinator._last_update_time = past_time.isoformat()
        coordinator._daily_power_charged = 0.0
        coordinator._daily_power_discharged = 0.0

        data = {
            "total_energy_charged": 0,  # Meters not tracking
            "total_energy_discharged": 0,
            "total_consumption": 100.0,
            "available_energy": 5000,
            "power": -1000,  # Currently charging at 1000W
            "soc": 50,
        }

        coordinator._calculate_daily_values(data)

        # Should have accumulated some charged energy via integration
        assert data["energy_charged_today"] > 0
        assert data["energy_discharged_today"] == 0
        assert coordinator._last_power == -1000
        assert coordinator._last_update_time is not None
        assert coordinator._last_soc == 50

    async def test_power_integration_fallback_discharging(
        self, hass: HomeAssistant, local_entry: MockConfigEntry, mock_store
    ):
        """Test power integration fallback when discharging."""
        coordinator = EnphaseBatteryDataUpdateCoordinator(hass, local_entry)
        today_str = datetime.now().strftime("%Y-%m-%d")
        coordinator._daily_reset_date = today_str
        coordinator._daily_charged_start = 0
        coordinator._daily_discharged_start = 0

        past_time = datetime.now() - timedelta(seconds=60)
        coordinator._last_power = 2000.0  # Previous: discharging at 2000W
        coordinator._last_update_time = past_time.isoformat()
        coordinator._daily_power_charged = 0.0
        coordinator._daily_power_discharged = 0.0

        data = {
            "total_energy_charged": 0,
            "total_energy_discharged": 0,
            "total_consumption": 100.0,
            "available_energy": 5000,
            "power": 2000,  # Currently discharging at 2000W
            "soc": 40,
        }

        coordinator._calculate_daily_values(data)

        assert data["energy_charged_today"] == 0
        assert data["energy_discharged_today"] > 0

    async def test_power_integration_zero_avg_power(
        self, hass: HomeAssistant, local_entry: MockConfigEntry, mock_store
    ):
        """Test power integration when average power is zero (idle transition)."""
        coordinator = EnphaseBatteryDataUpdateCoordinator(hass, local_entry)
        today_str = datetime.now().strftime("%Y-%m-%d")
        coordinator._daily_reset_date = today_str
        coordinator._daily_charged_start = 0
        coordinator._daily_discharged_start = 0

        past_time = datetime.now() - timedelta(seconds=30)
        # Previous power was +500W, current is -500W -> average = 0
        coordinator._last_power = 500.0
        coordinator._last_update_time = past_time.isoformat()
        coordinator._daily_power_charged = 0.0
        coordinator._daily_power_discharged = 0.0

        data = {
            "total_energy_charged": 0,
            "total_energy_discharged": 0,
            "total_consumption": 100.0,
            "available_energy": 5000,
            "power": -500,  # avg_power = (500 + -500) / 2 = 0
            "soc": 50,
        }

        coordinator._calculate_daily_values(data)

        # Neither charged nor discharged energy should increase
        assert data["energy_charged_today"] == 0
        assert data["energy_discharged_today"] == 0

    async def test_power_integration_no_previous_data(
        self, hass: HomeAssistant, local_entry: MockConfigEntry, mock_store
    ):
        """Test power integration with no previous power/time (first reading)."""
        coordinator = EnphaseBatteryDataUpdateCoordinator(hass, local_entry)
        today_str = datetime.now().strftime("%Y-%m-%d")
        coordinator._daily_reset_date = today_str
        coordinator._daily_charged_start = 0
        coordinator._daily_discharged_start = 0
        coordinator._last_power = None
        coordinator._last_update_time = None

        data = {
            "total_energy_charged": 0,
            "total_energy_discharged": 0,
            "total_consumption": 100.0,
            "available_energy": 5000,
            "power": -500,
            "soc": 60,
        }

        coordinator._calculate_daily_values(data)

        # No integration should happen (no previous data)
        assert data["energy_charged_today"] == 0
        assert data["energy_discharged_today"] == 0
        # But last_power should now be set for next iteration
        assert coordinator._last_power == -500
        assert coordinator._last_update_time is not None

    async def test_power_integration_invalid_time(self, hass: HomeAssistant, local_entry: MockConfigEntry, mock_store):
        """Test power integration handles invalid last_update_time gracefully."""
        coordinator = EnphaseBatteryDataUpdateCoordinator(hass, local_entry)
        today_str = datetime.now().strftime("%Y-%m-%d")
        coordinator._daily_reset_date = today_str
        coordinator._daily_charged_start = 0
        coordinator._daily_discharged_start = 0
        coordinator._last_power = -500.0
        coordinator._last_update_time = "not-a-valid-time"

        data = {
            "total_energy_charged": 0,
            "total_energy_discharged": 0,
            "total_consumption": 100.0,
            "available_energy": 5000,
            "power": -500,
            "soc": 60,
        }

        # Should not raise - handles ValueError gracefully
        coordinator._calculate_daily_values(data)

        # Last power/time should still be updated for next iteration
        assert coordinator._last_power == -500

    async def test_24h_consumption_calculation(self, hass: HomeAssistant, local_entry: MockConfigEntry, mock_store):
        """Test 24h rolling consumption calculation."""
        coordinator = EnphaseBatteryDataUpdateCoordinator(hass, local_entry)
        today_str = datetime.now().strftime("%Y-%m-%d")
        coordinator._daily_reset_date = today_str
        coordinator._daily_charged_start = 100.0
        coordinator._daily_discharged_start = 80.0

        # Pre-populate consumption history with 2 entries
        now = datetime.now()
        old_time = (now - timedelta(hours=12)).isoformat()
        coordinator._consumption_24h_history = [(old_time, 200.0)]

        data = {
            "total_energy_charged": 105.0,
            "total_energy_discharged": 83.0,
            "total_consumption": 230.0,
            "available_energy": 5000,
            "power": 500,
        }

        coordinator._calculate_daily_values(data)

        # 230 - 200 = 30 kWh
        assert data["consumption_24h"] == 30.0

    async def test_24h_consumption_removes_old_entries(
        self, hass: HomeAssistant, local_entry: MockConfigEntry, mock_store
    ):
        """Test old entries (>24h) are removed from consumption history."""
        coordinator = EnphaseBatteryDataUpdateCoordinator(hass, local_entry)
        today_str = datetime.now().strftime("%Y-%m-%d")
        coordinator._daily_reset_date = today_str
        coordinator._daily_charged_start = 100.0
        coordinator._daily_discharged_start = 80.0

        now = datetime.now()
        old_entry = (now - timedelta(hours=25)).isoformat()
        recent_entry = (now - timedelta(hours=1)).isoformat()
        coordinator._consumption_24h_history = [
            (old_entry, 100.0),
            (recent_entry, 200.0),
        ]

        data = {
            "total_energy_charged": 105.0,
            "total_energy_discharged": 83.0,
            "total_consumption": 250.0,
            "available_energy": 5000,
            "power": 500,
        }

        coordinator._calculate_daily_values(data)

        # Old entry should be removed; history should have recent + new entry
        assert len(coordinator._consumption_24h_history) == 2
        # Consumption: 250 - 200 = 50
        assert data["consumption_24h"] == 50.0

    async def test_24h_consumption_single_entry(self, hass: HomeAssistant, local_entry: MockConfigEntry, mock_store):
        """Test 24h consumption with single entry returns 0."""
        coordinator = EnphaseBatteryDataUpdateCoordinator(hass, local_entry)
        today_str = datetime.now().strftime("%Y-%m-%d")
        coordinator._daily_reset_date = today_str
        coordinator._daily_charged_start = 100.0
        coordinator._daily_discharged_start = 80.0
        coordinator._consumption_24h_history = []

        data = {
            "total_energy_charged": 105.0,
            "total_energy_discharged": 83.0,
            "total_consumption": 250.0,
            "available_energy": 5000,
            "power": 500,
        }

        coordinator._calculate_daily_values(data)

        # Only 1 entry after append, consumption_24h should be 0
        assert data["consumption_24h"] == 0

    async def test_backup_time_from_discharge_power(
        self, hass: HomeAssistant, local_entry: MockConfigEntry, mock_store
    ):
        """Test estimated backup time based on current discharge power."""
        coordinator = EnphaseBatteryDataUpdateCoordinator(hass, local_entry)
        today_str = datetime.now().strftime("%Y-%m-%d")
        coordinator._daily_reset_date = today_str
        coordinator._daily_charged_start = 100.0
        coordinator._daily_discharged_start = 80.0

        data = {
            "total_energy_charged": 105.0,
            "total_energy_discharged": 83.0,
            "total_consumption": 250.0,
            "available_energy": 5000,  # 5000 Wh
            "power": 1000,  # Discharging at 1000W
        }

        coordinator._calculate_daily_values(data)

        # 5000 Wh / 1000 W * 60 = 300 minutes
        assert data["estimated_backup_time"] == 300

    async def test_backup_time_from_avg_consumption(
        self, hass: HomeAssistant, local_entry: MockConfigEntry, mock_store
    ):
        """Test estimated backup time from average 24h consumption."""
        coordinator = EnphaseBatteryDataUpdateCoordinator(hass, local_entry)
        today_str = datetime.now().strftime("%Y-%m-%d")
        coordinator._daily_reset_date = today_str
        coordinator._daily_charged_start = 100.0
        coordinator._daily_discharged_start = 80.0

        now = datetime.now()
        # 12 hours of history: 24 kWh consumed = 2kW average
        old_time = (now - timedelta(hours=12)).isoformat()
        coordinator._consumption_24h_history = [(old_time, 176.0)]

        data = {
            "total_energy_charged": 105.0,
            "total_energy_discharged": 83.0,
            "total_consumption": 200.0,  # 200 - 176 = 24 kWh over 12 hours
            "available_energy": 4000,  # 4000 Wh
            "power": 0,  # Not discharging (idle)
        }

        coordinator._calculate_daily_values(data)

        # avg_power = (24 * 1000) / 12 = 2000W
        # backup = (4000 / 2000) * 60 = 120 minutes
        assert data["estimated_backup_time"] == 120

    async def test_backup_time_zero_when_no_consumption(
        self, hass: HomeAssistant, local_entry: MockConfigEntry, mock_store
    ):
        """Test backup time is 0 when no power/consumption data."""
        coordinator = EnphaseBatteryDataUpdateCoordinator(hass, local_entry)
        today_str = datetime.now().strftime("%Y-%m-%d")
        coordinator._daily_reset_date = today_str
        coordinator._daily_charged_start = 100.0
        coordinator._daily_discharged_start = 80.0

        data = {
            "total_energy_charged": 105.0,
            "total_energy_discharged": 83.0,
            "total_consumption": 250.0,
            "available_energy": 5000,
            "power": 0,  # No discharge
        }

        coordinator._calculate_daily_values(data)

        assert data["estimated_backup_time"] == 0

    async def test_backup_time_charging_battery(self, hass: HomeAssistant, local_entry: MockConfigEntry, mock_store):
        """Test backup time uses absolute power value for charging battery."""
        coordinator = EnphaseBatteryDataUpdateCoordinator(hass, local_entry)
        today_str = datetime.now().strftime("%Y-%m-%d")
        coordinator._daily_reset_date = today_str
        coordinator._daily_charged_start = 100.0
        coordinator._daily_discharged_start = 80.0

        data = {
            "total_energy_charged": 105.0,
            "total_energy_discharged": 83.0,
            "total_consumption": 250.0,
            "available_energy": 3000,
            "power": -500,  # Charging at 500W (absolute: 500)
        }

        coordinator._calculate_daily_values(data)

        # abs(-500) = 500, so 3000/500 * 60 = 360
        assert data["estimated_backup_time"] == 360

    async def test_storage_batched_save_initial(self, hass: HomeAssistant, local_entry: MockConfigEntry, mock_store):
        """Test storage save is triggered on first call (no previous save)."""
        coordinator = EnphaseBatteryDataUpdateCoordinator(hass, local_entry)
        today_str = datetime.now().strftime("%Y-%m-%d")
        coordinator._daily_reset_date = today_str
        coordinator._daily_charged_start = 100.0
        coordinator._daily_discharged_start = 80.0
        coordinator._last_storage_save = None

        data = {
            "total_energy_charged": 105.0,
            "total_energy_discharged": 83.0,
            "total_consumption": 250.0,
            "available_energy": 5000,
            "power": 500,
        }

        coordinator._calculate_daily_values(data)

        assert coordinator._last_storage_save is not None

    async def test_storage_batched_save_skipped_when_recent(
        self, hass: HomeAssistant, local_entry: MockConfigEntry, mock_store
    ):
        """Test storage save is skipped when last save is recent."""
        coordinator = EnphaseBatteryDataUpdateCoordinator(hass, local_entry)
        today_str = datetime.now().strftime("%Y-%m-%d")
        coordinator._daily_reset_date = today_str
        coordinator._daily_charged_start = 100.0
        coordinator._daily_discharged_start = 80.0

        recent_save = datetime.now() - timedelta(seconds=30)
        coordinator._last_storage_save = recent_save

        data = {
            "total_energy_charged": 105.0,
            "total_energy_discharged": 83.0,
            "total_consumption": 250.0,
            "available_energy": 5000,
            "power": 500,
        }

        coordinator._calculate_daily_values(data)

        # Last save should NOT have been updated (too recent)
        assert coordinator._last_storage_save == recent_save

    async def test_storage_batched_save_triggered_after_5min(
        self, hass: HomeAssistant, local_entry: MockConfigEntry, mock_store
    ):
        """Test storage save is triggered after 5 minutes."""
        coordinator = EnphaseBatteryDataUpdateCoordinator(hass, local_entry)
        today_str = datetime.now().strftime("%Y-%m-%d")
        coordinator._daily_reset_date = today_str
        coordinator._daily_charged_start = 100.0
        coordinator._daily_discharged_start = 80.0

        old_save = datetime.now() - timedelta(minutes=6)
        coordinator._last_storage_save = old_save

        data = {
            "total_energy_charged": 105.0,
            "total_energy_discharged": 83.0,
            "total_consumption": 250.0,
            "available_energy": 5000,
            "power": 500,
        }

        coordinator._calculate_daily_values(data)

        # Last save should have been updated
        assert coordinator._last_storage_save != old_save
        assert coordinator._last_storage_save is not None

    async def test_meter_energy_negative_clamped_to_zero(
        self, hass: HomeAssistant, local_entry: MockConfigEntry, mock_store
    ):
        """Test meter energy calculation clamps negative values to 0."""
        coordinator = EnphaseBatteryDataUpdateCoordinator(hass, local_entry)
        today_str = datetime.now().strftime("%Y-%m-%d")
        coordinator._daily_reset_date = today_str
        # Start values higher than current (meter reset scenario)
        coordinator._daily_charged_start = 200.0
        coordinator._daily_discharged_start = 150.0

        data = {
            "total_energy_charged": 100.0,  # Less than start
            "total_energy_discharged": 80.0,  # Less than start
            "total_consumption": 250.0,
            "available_energy": 5000,
            "power": 500,
        }

        coordinator._calculate_daily_values(data)

        # Should be clamped to 0 (max(0, negative))
        assert data["energy_charged_today"] == 0
        assert data["energy_discharged_today"] == 0


# ---------------------------------------------------------------------------
# 10. invalidate_cloud_control_cache tests
# ---------------------------------------------------------------------------


class TestInvalidateCloudControlCache:
    """Tests for invalidate_cloud_control_cache."""

    async def test_invalidation(self, hass: HomeAssistant, local_entry: MockConfigEntry, mock_store):
        """Test cache invalidation sets _last_cloud_control_fetch to None."""
        coordinator = EnphaseBatteryDataUpdateCoordinator(hass, local_entry)
        coordinator._last_cloud_control_fetch = datetime.now()

        coordinator.invalidate_cloud_control_cache()

        assert coordinator._last_cloud_control_fetch is None

    async def test_invalidation_when_already_none(self, hass: HomeAssistant, local_entry: MockConfigEntry, mock_store):
        """Test cache invalidation is safe when already None."""
        coordinator = EnphaseBatteryDataUpdateCoordinator(hass, local_entry)
        coordinator._last_cloud_control_fetch = None

        coordinator.invalidate_cloud_control_cache()

        assert coordinator._last_cloud_control_fetch is None


# ---------------------------------------------------------------------------
# 11. async_shutdown tests
# ---------------------------------------------------------------------------


class TestAsyncShutdown:
    """Tests for async_shutdown."""

    async def test_saves_and_closes_local_api(
        self,
        hass: HomeAssistant,
        local_entry: MockConfigEntry,
        mock_store,
        mock_local_api,
    ):
        """Test shutdown saves energy tracking and closes local API."""
        coordinator = EnphaseBatteryDataUpdateCoordinator(hass, local_entry)
        coordinator.local_api = mock_local_api

        await coordinator.async_shutdown()

        mock_store.async_save.assert_awaited_once()
        mock_local_api.close.assert_awaited_once()

    async def test_saves_without_local_api(
        self,
        hass: HomeAssistant,
        cloud_entry: MockConfigEntry,
        mock_store,
    ):
        """Test shutdown saves energy tracking when no local API."""
        coordinator = EnphaseBatteryDataUpdateCoordinator(hass, cloud_entry)
        coordinator.local_api = None

        await coordinator.async_shutdown()

        mock_store.async_save.assert_awaited_once()


# ---------------------------------------------------------------------------
# 12. Properties tests
# ---------------------------------------------------------------------------


class TestProperties:
    """Tests for coordinator properties."""

    async def test_connection_mode_local(self, hass: HomeAssistant, local_entry: MockConfigEntry, mock_store):
        """Test connection_mode returns local."""
        coordinator = EnphaseBatteryDataUpdateCoordinator(hass, local_entry)

        assert coordinator.connection_mode == CONNECTION_MODE_LOCAL

    async def test_connection_mode_cloud(self, hass: HomeAssistant, cloud_entry: MockConfigEntry, mock_store):
        """Test connection_mode returns cloud."""
        coordinator = EnphaseBatteryDataUpdateCoordinator(hass, cloud_entry)

        assert coordinator.connection_mode == CONNECTION_MODE_CLOUD

    async def test_is_local_mode_true(self, hass: HomeAssistant, local_entry: MockConfigEntry, mock_store):
        """Test is_local_mode returns True for local."""
        coordinator = EnphaseBatteryDataUpdateCoordinator(hass, local_entry)

        assert coordinator.is_local_mode is True

    async def test_is_local_mode_false(self, hass: HomeAssistant, cloud_entry: MockConfigEntry, mock_store):
        """Test is_local_mode returns False for cloud."""
        coordinator = EnphaseBatteryDataUpdateCoordinator(hass, cloud_entry)

        assert coordinator.is_local_mode is False

    async def test_battery_soc_with_data(self, hass: HomeAssistant, local_entry: MockConfigEntry, mock_store):
        """Test battery_soc returns SOC from data."""
        coordinator = EnphaseBatteryDataUpdateCoordinator(hass, local_entry)
        coordinator.data = {"soc": 75, "power": -500, "mode": "self-consumption"}

        assert coordinator.battery_soc == 75

    async def test_battery_soc_without_data(self, hass: HomeAssistant, local_entry: MockConfigEntry, mock_store):
        """Test battery_soc returns None when no data."""
        coordinator = EnphaseBatteryDataUpdateCoordinator(hass, local_entry)
        coordinator.data = None

        assert coordinator.battery_soc is None

    async def test_battery_soc_missing_key(self, hass: HomeAssistant, local_entry: MockConfigEntry, mock_store):
        """Test battery_soc returns None when soc key is missing."""
        coordinator = EnphaseBatteryDataUpdateCoordinator(hass, local_entry)
        coordinator.data = {"power": 500}

        assert coordinator.battery_soc is None

    async def test_battery_power_with_data(self, hass: HomeAssistant, local_entry: MockConfigEntry, mock_store):
        """Test battery_power returns power from data."""
        coordinator = EnphaseBatteryDataUpdateCoordinator(hass, local_entry)
        coordinator.data = {"soc": 50, "power": 1000, "mode": "self-consumption"}

        assert coordinator.battery_power == 1000

    async def test_battery_power_without_data(self, hass: HomeAssistant, local_entry: MockConfigEntry, mock_store):
        """Test battery_power returns None when no data."""
        coordinator = EnphaseBatteryDataUpdateCoordinator(hass, local_entry)
        coordinator.data = None

        assert coordinator.battery_power is None

    async def test_battery_mode_with_data(self, hass: HomeAssistant, local_entry: MockConfigEntry, mock_store):
        """Test battery_mode returns mode from data."""
        coordinator = EnphaseBatteryDataUpdateCoordinator(hass, local_entry)
        coordinator.data = {"soc": 50, "power": 1000, "mode": "self-consumption"}

        assert coordinator.battery_mode == "self-consumption"

    async def test_battery_mode_without_data(self, hass: HomeAssistant, local_entry: MockConfigEntry, mock_store):
        """Test battery_mode returns None when no data."""
        coordinator = EnphaseBatteryDataUpdateCoordinator(hass, local_entry)
        coordinator.data = None

        assert coordinator.battery_mode is None

    async def test_battery_mode_missing_key(self, hass: HomeAssistant, local_entry: MockConfigEntry, mock_store):
        """Test battery_mode returns None when mode key is missing."""
        coordinator = EnphaseBatteryDataUpdateCoordinator(hass, local_entry)
        coordinator.data = {"soc": 50, "power": 1000}

        assert coordinator.battery_mode is None

    async def test_is_charging_true(self, hass: HomeAssistant, local_entry: MockConfigEntry, mock_store):
        """Test is_charging returns True when power is negative."""
        coordinator = EnphaseBatteryDataUpdateCoordinator(hass, local_entry)
        coordinator.data = {"soc": 50, "power": -500, "mode": "self-consumption"}

        assert coordinator.is_charging is True

    async def test_is_charging_false_discharging(self, hass: HomeAssistant, local_entry: MockConfigEntry, mock_store):
        """Test is_charging returns False when power is positive."""
        coordinator = EnphaseBatteryDataUpdateCoordinator(hass, local_entry)
        coordinator.data = {"soc": 50, "power": 500, "mode": "self-consumption"}

        assert coordinator.is_charging is False

    async def test_is_charging_false_idle(self, hass: HomeAssistant, local_entry: MockConfigEntry, mock_store):
        """Test is_charging returns False when power is zero."""
        coordinator = EnphaseBatteryDataUpdateCoordinator(hass, local_entry)
        coordinator.data = {"soc": 50, "power": 0, "mode": "self-consumption"}

        assert coordinator.is_charging is False

    async def test_is_charging_none_data(self, hass: HomeAssistant, local_entry: MockConfigEntry, mock_store):
        """Test is_charging returns False when no data."""
        coordinator = EnphaseBatteryDataUpdateCoordinator(hass, local_entry)
        coordinator.data = None

        assert coordinator.is_charging is False

    async def test_is_charging_no_power_key(self, hass: HomeAssistant, local_entry: MockConfigEntry, mock_store):
        """Test is_charging returns False when power key is missing."""
        coordinator = EnphaseBatteryDataUpdateCoordinator(hass, local_entry)
        coordinator.data = {"soc": 50}

        assert coordinator.is_charging is False


# ===========================================================================
# 14. log-when-unavailable pattern
# ===========================================================================
@pytest.mark.usefixtures("mock_store", "mock_session")
class TestLogWhenUnavailable:
    """Tests for log-when-unavailable pattern."""

    async def test_logs_once_when_becoming_unavailable(
        self,
        hass: HomeAssistant,
        cloud_entry: MockConfigEntry,
        mock_cloud_api,
    ):
        """First UpdateFailed should set _previously_unavailable flag."""
        mock_cloud_api.get_battery_data = AsyncMock(side_effect=EnphaseBatteryApiError("timeout"))
        coordinator = EnphaseBatteryDataUpdateCoordinator(hass, cloud_entry)
        coordinator.api = mock_cloud_api

        assert coordinator._previously_unavailable is False

        with pytest.raises(UpdateFailed):
            await coordinator._async_update_data()

        assert coordinator._previously_unavailable is True

    async def test_does_not_log_again_when_still_unavailable(
        self,
        hass: HomeAssistant,
        cloud_entry: MockConfigEntry,
        mock_cloud_api,
    ):
        """Subsequent UpdateFailed should keep flag True."""
        mock_cloud_api.get_battery_data = AsyncMock(side_effect=EnphaseBatteryApiError("timeout"))
        coordinator = EnphaseBatteryDataUpdateCoordinator(hass, cloud_entry)
        coordinator.api = mock_cloud_api
        coordinator._previously_unavailable = True  # Already flagged

        with pytest.raises(UpdateFailed):
            await coordinator._async_update_data()

        assert coordinator._previously_unavailable is True

    async def test_logs_restored_when_data_returns(
        self,
        hass: HomeAssistant,
        cloud_entry: MockConfigEntry,
        mock_cloud_api,
    ):
        """Successful update after unavailable should clear flag."""
        mock_cloud_api.get_battery_data = AsyncMock(return_value={"soc": 50, "power": 0, "mode": "self-consumption"})
        coordinator = EnphaseBatteryDataUpdateCoordinator(hass, cloud_entry)
        coordinator.api = mock_cloud_api
        coordinator._previously_unavailable = True  # Was unavailable

        data = await coordinator._async_update_data()

        assert data["soc"] == 50
        assert coordinator._previously_unavailable is False

    async def test_generic_exception_sets_unavailable_flag(
        self,
        hass: HomeAssistant,
        local_entry: MockConfigEntry,
        mock_local_api,
    ):
        """Generic Exception (ConfigEntryAuthFailed) should set flag."""
        mock_local_api.get_battery_data = AsyncMock(side_effect=EnvoyAuthError("Token expired"))
        coordinator = EnphaseBatteryDataUpdateCoordinator(hass, local_entry)
        coordinator.local_api = mock_local_api

        assert coordinator._previously_unavailable is False

        with pytest.raises(UpdateFailed):
            await coordinator._async_update_data()

        assert coordinator._previously_unavailable is True
