"""Switch platform for Enphase Battery."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import EnphaseBatteryDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Enphase Battery switch platform."""
    coordinator: EnphaseBatteryDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities = [
        ChargeFromGridSwitch(coordinator),
    ]

    async_add_entities(entities)


class ChargeFromGridSwitch(CoordinatorEntity, SwitchEntity):
    """Charge From Grid switch entity."""

    def __init__(self, coordinator: EnphaseBatteryDataUpdateCoordinator) -> None:
        """Initialize the switch entity."""
        super().__init__(coordinator)
        self._attr_name = "Charge depuis le réseau"
        self._attr_unique_id = f"{DOMAIN}_charge_from_grid"
        self._attr_has_entity_name = True
        self._attr_icon = "mdi:transmission-tower-import"

    @property
    def device_info(self) -> dict[str, Any]:
        """Return device information."""
        return {
            "identifiers": {(DOMAIN, "enphase_battery")},
            "name": "Enphase Battery IQ 5P",
            "manufacturer": "Enphase Energy",
            "model": "IQ Battery 5P",
        }

    @property
    def is_on(self) -> bool | None:
        """Return true if switch is on."""
        if not self.coordinator.data:
            return None

        return self.coordinator.data.get("charge_from_grid", False)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on."""
        try:
            await self.coordinator.api.set_charge_from_grid(True)
            await self.coordinator.async_request_refresh()
        except Exception as err:
            _LOGGER.error(f"Failed to enable Charge From Grid: {err}")
            raise

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off."""
        try:
            await self.coordinator.api.set_charge_from_grid(False)
            await self.coordinator.async_request_refresh()
        except Exception as err:
            _LOGGER.error(f"Failed to disable Charge From Grid: {err}")
            raise
