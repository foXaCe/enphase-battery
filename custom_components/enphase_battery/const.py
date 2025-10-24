"""Constants for the Enphase Battery integration."""
from typing import Final

DOMAIN: Final = "enphase_battery"

# Configuration
CONF_SERIAL_NUMBER: Final = "serial_number"
CONF_USERNAME: Final = "username"
CONF_PASSWORD: Final = "password"
CONF_SITE_ID: Final = "site_id"  # ID du site Enphase
CONF_USER_ID: Final = "user_id"  # ID utilisateur Enphase (optionnel)
CONF_USE_MQTT: Final = "use_mqtt"  # Option pour activer MQTT

# API Endpoints
API_BASE_URL: Final = "https://enlighten.enphaseenergy.com"
API_AUTH_URL: Final = "https://entrez.enphaseenergy.com"
API_TIMEOUT: Final = 30  # secondes

# Update intervals
DEFAULT_SCAN_INTERVAL: Final = 60  # secondes (mode polling)
MQTT_SCAN_INTERVAL: Final = 300  # secondes (backup avec MQTT)
MQTT_RECONNECT_INTERVAL: Final = 900  # 15 minutes (durée token MQTT)

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

# Attributs
ATTR_BATTERY_SERIAL: Final = "serial_number"
ATTR_BATTERY_MODEL: Final = "model"
ATTR_BATTERY_FIRMWARE: Final = "firmware_version"
ATTR_BATTERY_CAPACITY: Final = "capacity"
ATTR_BATTERY_HEALTH: Final = "health"
