"""Select platform for Enphase Battery."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, ClassVar

from homeassistant.components.select import SelectEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    BATTERY_MODE_BACKUP_ONLY,
    BATTERY_MODE_COST_SAVINGS,
    BATTERY_MODE_EXPERT,
    BATTERY_MODE_SELF_CONSUMPTION,
    DEVICE_INFO,
    DOMAIN,
)
from .coordinator import EnphaseBatteryDataUpdateCoordinator

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from . import EnphaseBatteryConfigEntry

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: EnphaseBatteryConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Enphase Battery select platform."""
    coordinator = entry.runtime_data.coordinator

    entities = []

    # Battery Mode select available in:
    # 1. Cloud mode (always)
    # 2. Local mode with cloud control enabled (hybrid mode)
    # Local API no longer supports this since firmware 8.2.4225 (confirmed by Home Assistant docs)
    enable_cloud_control = entry.data.get("enable_cloud_control", False)

    if not coordinator.is_local_mode or enable_cloud_control:
        entities.append(BatteryModeSelect(coordinator))
    else:
        _LOGGER.warning(
            "Battery Mode select disabled. "
            "Envoy firmware 8.x no longer supports battery control via local API. "
            "Enable 'Cloud Control' option in integration settings or use Enphase app."
        )

    if entities:
        async_add_entities(entities)


class BatteryModeSelect(CoordinatorEntity, SelectEntity):
    """Battery Operation Mode select entity."""

    # Use __slots__ to reduce memory footprint
    __slots__ = ("_mode_api_to_ui", "_mode_ui_to_api")

    # Class-level attributes (shared across all instances)
    _attr_device_info = DEVICE_INFO
    _attr_has_entity_name = True
    _attr_icon = "mdi:battery-sync"
    _attr_options: ClassVar[list[str]] = [
        "Autoconsommation",  # self-consumption
        "Optimisation IA",  # cost_savings (AI optimization)
    ]

    def __init__(self, coordinator: EnphaseBatteryDataUpdateCoordinator) -> None:
        """Initialize the select entity."""
        super().__init__(coordinator)
        self._attr_name = "Mode de la batterie"
        self._attr_unique_id = f"{DOMAIN}_battery_mode"

        # Mapping API <-> UI
        self._mode_api_to_ui = {
            BATTERY_MODE_SELF_CONSUMPTION: "Autoconsommation",
            BATTERY_MODE_COST_SAVINGS: "Optimisation IA",
            # Modes cachés mais conservés pour compatibilité
            BATTERY_MODE_BACKUP_ONLY: "Backup uniquement",
            BATTERY_MODE_EXPERT: "Expert",
        }

        self._mode_ui_to_api = {v: k for k, v in self._mode_api_to_ui.items()}

    @property
    def current_option(self) -> str | None:
        """Return the current selected option."""
        if not self.coordinator.data:
            return None

        api_mode = self.coordinator.battery_mode
        if not api_mode:
            return None

        return self._mode_api_to_ui.get(api_mode)

    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""
        api_mode = self._mode_ui_to_api.get(option)

        if not api_mode:
            _LOGGER.error("Invalid mode selected: %s", option)
            return

        try:
            # Always use cloud API (pure cloud mode or hybrid mode)
            if not self.coordinator.api:
                raise Exception("Cloud API not initialized. Enable cloud control in settings.")
            await self.coordinator.api.set_battery_mode(api_mode)
            # Invalidate cache to force immediate cloud refresh
            self.coordinator.invalidate_cloud_control_cache()
            await self.coordinator.async_request_refresh()

        except Exception as err:
            _LOGGER.error("Failed to change battery mode: %s", err)
            raise
