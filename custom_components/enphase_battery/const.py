"""Constants for the Enphase Battery integration."""

from __future__ import annotations

from typing import Final

from homeassistant.helpers.device_registry import DeviceInfo

DOMAIN: Final = "enphase_battery"

# Configuration
CONF_SERIAL_NUMBER: Final = "serial_number"
CONF_USERNAME: Final = "username"
CONF_PASSWORD: Final = "password"
CONF_SITE_ID: Final = "site_id"  # ID du site Enphase
CONF_USER_ID: Final = "user_id"  # ID utilisateur Enphase (optionnel)
CONF_CONNECTION_MODE: Final = "connection_mode"  # Connection mode (local/cloud)
CONF_ENVOY_HOST: Final = "envoy_host"  # Hostname/IP Envoy pour mode local
CONF_ENABLE_CLOUD_CONTROL: Final = "enable_cloud_control"  # Activer contrôle cloud en mode local

# API Endpoints
API_BASE_URL: Final = "https://enlighten.enphaseenergy.com"
API_AUTH_URL: Final = "https://entrez.enphaseenergy.com"
API_TIMEOUT: Final = 30  # secondes

# Connection modes
CONNECTION_MODE_CLOUD: Final = "cloud"
CONNECTION_MODE_LOCAL: Final = "local"
CONNECTION_MODES: Final = [CONNECTION_MODE_LOCAL, CONNECTION_MODE_CLOUD]

# Update intervals
DEFAULT_SCAN_INTERVAL: Final = 60  # secondes (mode polling cloud)
LOCAL_SCAN_INTERVAL: Final = 10  # secondes (mode local - plus rapide)

# Battery modes (noms API réels découverts)
BATTERY_MODE_SELF_CONSUMPTION: Final = "self-consumption"
BATTERY_MODE_COST_SAVINGS: Final = "cost_savings"
BATTERY_MODE_BACKUP_ONLY: Final = "backup_only"
BATTERY_MODE_EXPERT: Final = "expert"

BATTERY_MODES: Final = [
    BATTERY_MODE_SELF_CONSUMPTION,
    BATTERY_MODE_COST_SAVINGS,
    BATTERY_MODE_BACKUP_ONLY,
    BATTERY_MODE_EXPERT,
]

# Sensor types
SENSOR_TYPE_BATTERY_SOC: Final = "battery_soc"
SENSOR_TYPE_BATTERY_POWER: Final = "battery_power"
SENSOR_TYPE_BATTERY_VOLTAGE: Final = "battery_voltage"
SENSOR_TYPE_BATTERY_CURRENT: Final = "battery_current"
SENSOR_TYPE_BATTERY_TEMPERATURE: Final = "battery_temperature"
SENSOR_TYPE_BATTERY_ENERGY_CHARGED: Final = "battery_energy_charged"
SENSOR_TYPE_BATTERY_ENERGY_DISCHARGED: Final = "battery_energy_discharged"

# Attributes
ATTR_BATTERY_SERIAL: Final = "serial_number"
ATTR_BATTERY_MODEL: Final = "model"
ATTR_BATTERY_FIRMWARE: Final = "firmware_version"
ATTR_BATTERY_CAPACITY: Final = "capacity"
ATTR_BATTERY_HEALTH: Final = "health"

# Device info for the battery system (shared across system-level entities)
DEVICE_INFO: Final = DeviceInfo(
    identifiers={(DOMAIN, "enphase_battery_system")},
    name="Enphase Battery System",
    manufacturer="Enphase Energy",
    model="IQ Battery 5P System",
)


def get_battery_device_info(serial_num: str, part_num: str | None = None) -> DeviceInfo:
    """Get device info for an individual battery."""
    return DeviceInfo(
        identifiers={(DOMAIN, f"battery_{serial_num}")},
        name=f"Enphase Battery {serial_num[-4:]}",
        manufacturer="Enphase Energy",
        model=part_num or "IQ Battery 5P",
        serial_number=serial_num,
        via_device=(DOMAIN, "enphase_battery_system"),
    )
