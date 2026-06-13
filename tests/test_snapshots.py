"""End-to-end snapshot test: full setup with the real coordinator + platforms.

Only the API clients and persistent storage are mocked, so the real coordinator
fetch, energy tracking, platform wiring and entity creation all run, and the
resulting entities + states are captured as a snapshot.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry
from syrupy.assertion import SnapshotAssertion

from custom_components.enphase_battery.const import (
    CONF_CONNECTION_MODE,
    CONF_ENVOY_HOST,
    CONNECTION_MODE_LOCAL,
    DOMAIN,
)

# Realistic local Envoy payload (one ENCHARGE battery).
LOCAL_DATA = {
    "soc": 75,
    "soh": 98,
    "power": -450,
    "charge_power": 450,
    "discharge_power": 0,
    "available_energy": 4200,
    "max_capacity": 5000,
    "status": "grid-tied",
    "total_energy_charged": 12.5,
    "total_energy_discharged": 8.2,
    "total_consumption": 30.0,
    "total_production": 40.0,
    "temperature": 24.0,
    "max_cell_temp": 25.0,
    "charge_from_grid": False,
    "devices": [
        {
            "serial_num": "122140000001",
            "part_num": "500-00010",
            "type": "ENCHARGE",
            "percentFull": 75,
            "temperature": 24,
            "maxCellTemp": 25,
            "encharge_capacity": 5000,
            "img_pnum_running": "2.0.1",
            "reported_enc_grid_state": "grid-tied",
        }
    ],
}

# Cloud control settings merged in hybrid mode.
CLOUD_SETTINGS = {
    "chargeFromGrid": True,
    "profile": "self-consumption",
    "dtgControl": {"enabled": False},
    "rbdControl": {"enabled": True},
    "powerMatchControl": {"enabled": False},
    "batteryBackupPercentage": 20,
    "veryLowSoc": 10,
}


async def test_all_entities_snapshot(hass: HomeAssistant, snapshot: SnapshotAssertion) -> None:
    """Full hybrid setup creates the expected entities with the expected states."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Enphase Battery",
        entry_id="enphasebatterytestentry01",
        data={
            CONF_CONNECTION_MODE: CONNECTION_MODE_LOCAL,
            CONF_ENVOY_HOST: "192.168.1.50",
            "cloud_username": "user@example.com",
            "cloud_password": "password",
            "enable_cloud_control": True,
        },
        unique_id="ENVOY123456",
    )
    entry.add_to_hass(hass)

    local_api = MagicMock()
    local_api.authenticate = AsyncMock()
    local_api.get_battery_data = AsyncMock(return_value=dict(LOCAL_DATA))
    local_api.serial_number = "ENVOY123456"
    local_api.firmware_version = "D8.2.4225"
    local_api.close = AsyncMock()

    cloud_api = MagicMock()
    cloud_api.authenticate = AsyncMock()
    cloud_api._site_id = 12345
    cloud_api._user_id = 67890
    cloud_api.get_battery_settings = AsyncMock(return_value=CLOUD_SETTINGS)

    with (
        patch("custom_components.enphase_battery.coordinator.EnphaseEnvoyLocalAPI", return_value=local_api),
        patch("custom_components.enphase_battery.coordinator.EnphaseBatteryAPI", return_value=cloud_api),
        patch("custom_components.enphase_battery.coordinator.Store") as mock_store_cls,
        patch("custom_components.enphase_battery.coordinator.async_get_clientsession"),
        patch("custom_components.enphase_battery.coordinator.asyncio.sleep", new=AsyncMock()),
    ):
        mock_store_cls.return_value.async_load = AsyncMock(return_value=None)
        mock_store_cls.return_value.async_save = AsyncMock()

        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    registry = er.async_get(hass)
    entities = er.async_entries_for_config_entry(registry, entry.entry_id)
    assert entities, "no entities were created"

    for reg_entry in sorted(entities, key=lambda e: e.entity_id):
        assert reg_entry == snapshot(name=f"{reg_entry.entity_id}-entry")
        state = hass.states.get(reg_entry.entity_id)
        assert state == snapshot(name=f"{reg_entry.entity_id}-state")
