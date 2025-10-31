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

    entities = []

    # Charge From Grid switch available in:
    # 1. Cloud mode (always)
    # 2. Local mode with cloud control enabled (hybrid mode)
    # Local API no longer supports this since firmware 8.2.4225 (confirmed by Home Assistant docs)
    enable_cloud_control = entry.data.get("enable_cloud_control", False)

    if not coordinator.is_local_mode or enable_cloud_control:
        entities.append(ChargeFromGridSwitch(coordinator))
        entities.append(LimitDischargeSwitch(coordinator))
        entities.append(ReserveBatteryDischargeSwitch(coordinator))
        mode_desc = "Cloud mode" if not coordinator.is_local_mode else "Hybrid mode (Local data + Cloud control)"
    else:
        _LOGGER.warning(
            "Charge From Grid switch disabled. "
            "Envoy firmware 8.x no longer supports battery control via local API. "
            "Enable 'Cloud Control' option in integration settings or use Enphase app."
        )

    if entities:
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
            # Always use cloud API (pure cloud mode or hybrid mode)
            if not self.coordinator.api:
                raise Exception("Cloud API not initialized. Enable cloud control in settings.")
            await self.coordinator.api.set_charge_from_grid(True)
            await self.coordinator.async_request_refresh()
        except Exception as err:
            _LOGGER.error(f"Failed to enable Charge From Grid: {err}")
            raise

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off."""
        try:
            # Always use cloud API (pure cloud mode or hybrid mode)
            if not self.coordinator.api:
                raise Exception("Cloud API not initialized. Enable cloud control in settings.")
            await self.coordinator.api.set_charge_from_grid(False)
            await self.coordinator.async_request_refresh()
        except Exception as err:
            _LOGGER.error(f"Failed to disable Charge From Grid: {err}")
            raise


class LimitDischargeSwitch(CoordinatorEntity, SwitchEntity):
    """Discharge To Grid switch entity (dtgControl).

    When enabled: Battery can discharge to grid
    When disabled: Battery cannot discharge to grid (discharge is limited)
    """

    def __init__(self, coordinator: EnphaseBatteryDataUpdateCoordinator) -> None:
        """Initialize the switch entity."""
        super().__init__(coordinator)
        self._attr_name = "Autoriser la décharge vers le réseau"
        self._attr_unique_id = f"{DOMAIN}_discharge_to_grid"
        self._attr_has_entity_name = True
        self._attr_icon = "mdi:transmission-tower-export"
        self._attr_assumed_state = True  # Show optimistic state until API confirms
        self._optimistic_state: bool | None = None

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
        # Return optimistic state if set (during API call)
        if self._optimistic_state is not None:
            return self._optimistic_state

        if not self.coordinator.data:
            return None

        # Read from dtgControl.enabled (Discharge To Grid)
        return self.coordinator.data.get("discharge_to_grid", False)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on."""
        try:
            # Set optimistic state immediately for UI feedback
            self._optimistic_state = True
            self.async_write_ha_state()

            # Always use cloud API (pure cloud mode or hybrid mode)
            if not self.coordinator.api:
                raise Exception("Cloud API not initialized. Enable cloud control in settings.")
            await self.coordinator.api.set_limit_discharge(True)
            await self.coordinator.async_request_refresh()

            # Clear optimistic state after refresh
            self._optimistic_state = None
            self.async_write_ha_state()
        except Exception as err:
            # Clear optimistic state on error
            self._optimistic_state = None
            self.async_write_ha_state()
            _LOGGER.error(f"Failed to enable Limit Discharge: {err}")
            raise

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off."""
        try:
            # Set optimistic state immediately for UI feedback
            self._optimistic_state = False
            self.async_write_ha_state()

            # Always use cloud API (pure cloud mode or hybrid mode)
            if not self.coordinator.api:
                raise Exception("Cloud API not initialized. Enable cloud control in settings.")
            await self.coordinator.api.set_limit_discharge(False)
            await self.coordinator.async_request_refresh()

            # Clear optimistic state after refresh
            self._optimistic_state = None
            self.async_write_ha_state()
        except Exception as err:
            # Clear optimistic state on error
            self._optimistic_state = None
            self.async_write_ha_state()
            _LOGGER.error(f"Failed to disable Limit Discharge: {err}")
            raise


class ReserveBatteryDischargeSwitch(CoordinatorEntity, SwitchEntity):
    """Reserve Battery Discharge switch entity (rbdControl).

    When enabled: Battery discharge is limited/reserved
    When disabled: Battery can discharge freely
    """

    def __init__(self, coordinator: EnphaseBatteryDataUpdateCoordinator) -> None:
        """Initialize the switch entity."""
        super().__init__(coordinator)
        self._attr_name = "Limiter la décharge de la batterie"
        self._attr_unique_id = f"{DOMAIN}_reserve_battery_discharge"
        self._attr_has_entity_name = True
        self._attr_icon = "mdi:battery-lock"
        self._attr_assumed_state = True  # Show optimistic state until API confirms
        self._optimistic_state: bool | None = None

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
        # Return optimistic state if set (during API call)
        if self._optimistic_state is not None:
            return self._optimistic_state

        if not self.coordinator.data:
            return None

        # Read from rbdControl.enabled (Reserve Battery Discharge)
        return self.coordinator.data.get("reserve_battery_discharge", False)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on."""
        try:
            # Set optimistic state immediately for UI feedback
            self._optimistic_state = True
            self.async_write_ha_state()

            # Always use cloud API (pure cloud mode or hybrid mode)
            if not self.coordinator.api:
                raise Exception("Cloud API not initialized. Enable cloud control in settings.")
            await self.coordinator.api.set_reserve_battery_discharge(True)
            await self.coordinator.async_request_refresh()

            # Clear optimistic state after refresh
            self._optimistic_state = None
            self.async_write_ha_state()
        except Exception as err:
            # Clear optimistic state on error
            self._optimistic_state = None
            self.async_write_ha_state()
            _LOGGER.error(f"Failed to enable Reserve Battery Discharge: {err}")
            raise

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off."""
        try:
            # Set optimistic state immediately for UI feedback
            self._optimistic_state = False
            self.async_write_ha_state()

            # Always use cloud API (pure cloud mode or hybrid mode)
            if not self.coordinator.api:
                raise Exception("Cloud API not initialized. Enable cloud control in settings.")
            await self.coordinator.api.set_reserve_battery_discharge(False)
            await self.coordinator.async_request_refresh()

            # Clear optimistic state after refresh
            self._optimistic_state = None
            self.async_write_ha_state()
        except Exception as err:
            # Clear optimistic state on error
            self._optimistic_state = None
            self.async_write_ha_state()
            _LOGGER.error(f"Failed to disable Reserve Battery Discharge: {err}")
            raise
