"""Switch platform for Enphase Battery."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DEVICE_INFO, DOMAIN
from .coordinator import EnphaseBatteryDataUpdateCoordinator

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from . import EnphaseBatteryConfigEntry

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: EnphaseBatteryConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Enphase Battery switch platform."""
    coordinator = entry.runtime_data.coordinator

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
        entities.append(PowerMatchSwitch(coordinator))
    else:
        _LOGGER.warning(
            "Charge From Grid switch disabled. "
            "Envoy firmware 8.x no longer supports battery control via local API. "
            "Enable 'Cloud Control' option in integration settings or use Enphase app."
        )

    if entities:
        async_add_entities(entities)


class ChargeFromGridSwitch(CoordinatorEntity[EnphaseBatteryDataUpdateCoordinator], SwitchEntity):
    """Charge From Grid switch entity."""

    # Use __slots__ to reduce memory footprint
    __slots__ = ("_optimistic_state",)

    # Class-level attributes (shared across all instances)
    _attr_device_info = DEVICE_INFO
    _attr_has_entity_name = True
    _attr_icon = "mdi:transmission-tower-import"

    def __init__(self, coordinator: EnphaseBatteryDataUpdateCoordinator) -> None:
        """Initialize the switch entity."""
        super().__init__(coordinator)
        self._attr_translation_key = "charge_from_grid"
        self._attr_unique_id = f"{DOMAIN}_charge_from_grid"
        self._optimistic_state: bool | None = None

    @property
    def is_on(self) -> bool | None:
        """Return true if switch is on."""
        # Return optimistic state if set (during API call)
        if self._optimistic_state is not None:
            return self._optimistic_state

        if not self.coordinator.data:
            return None

        return self.coordinator.data.get("charge_from_grid", False)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on."""
        # Set optimistic state immediately for UI feedback
        self._optimistic_state = True
        self.async_write_ha_state()

        try:
            # Always use cloud API (pure cloud mode or hybrid mode)
            if not self.coordinator.api:
                raise HomeAssistantError(
                    translation_domain=DOMAIN,
                    translation_key="cloud_api_not_initialized",
                )
            await self.coordinator.api.set_charge_from_grid(True)

            # Clear optimistic state and invalidate cache to force immediate cloud refresh
            self._optimistic_state = None
            self.coordinator.invalidate_cloud_control_cache()
            await self.coordinator.async_request_refresh()
        except Exception as err:
            # Clear optimistic state on error
            self._optimistic_state = None
            self.async_write_ha_state()
            _LOGGER.error("Failed to enable Charge From Grid: %s", err)
            raise

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off."""
        # Set optimistic state immediately for UI feedback
        self._optimistic_state = False
        self.async_write_ha_state()

        try:
            # Always use cloud API (pure cloud mode or hybrid mode)
            if not self.coordinator.api:
                raise HomeAssistantError(
                    translation_domain=DOMAIN,
                    translation_key="cloud_api_not_initialized",
                )
            await self.coordinator.api.set_charge_from_grid(False)

            # Clear optimistic state and invalidate cache to force immediate cloud refresh
            self._optimistic_state = None
            self.coordinator.invalidate_cloud_control_cache()
            await self.coordinator.async_request_refresh()
        except Exception as err:
            # Clear optimistic state on error
            self._optimistic_state = None
            self.async_write_ha_state()
            _LOGGER.error("Failed to disable Charge From Grid: %s", err)
            raise


class LimitDischargeSwitch(CoordinatorEntity[EnphaseBatteryDataUpdateCoordinator], SwitchEntity):
    """Discharge To Grid switch entity (dtgControl).

    When enabled: Battery can discharge to grid
    When disabled: Battery cannot discharge to grid (discharge is limited)
    """

    # Use __slots__ to reduce memory footprint
    __slots__ = ("_optimistic_state",)

    # Class-level attributes (shared across all instances)
    _attr_device_info = DEVICE_INFO
    _attr_has_entity_name = True
    _attr_icon = "mdi:transmission-tower-export"

    def __init__(self, coordinator: EnphaseBatteryDataUpdateCoordinator) -> None:
        """Initialize the switch entity."""
        super().__init__(coordinator)
        self._attr_translation_key = "discharge_to_grid"
        self._attr_unique_id = f"{DOMAIN}_discharge_to_grid"
        self._optimistic_state: bool | None = None

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
        # Set optimistic state immediately for UI feedback
        self._optimistic_state = True
        self.async_write_ha_state()

        try:
            # Always use cloud API (pure cloud mode or hybrid mode)
            if not self.coordinator.api:
                raise HomeAssistantError(
                    translation_domain=DOMAIN,
                    translation_key="cloud_api_not_initialized",
                )
            await self.coordinator.api.set_limit_discharge(True)

            # Clear optimistic state and invalidate cache to force immediate cloud refresh
            self._optimistic_state = None
            self.coordinator.invalidate_cloud_control_cache()
            await self.coordinator.async_request_refresh()
        except Exception as err:
            # Clear optimistic state on error
            self._optimistic_state = None
            self.async_write_ha_state()
            _LOGGER.error("Failed to enable Limit Discharge: %s", err)
            raise

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off."""
        # Set optimistic state immediately for UI feedback
        self._optimistic_state = False
        self.async_write_ha_state()

        try:
            # Always use cloud API (pure cloud mode or hybrid mode)
            if not self.coordinator.api:
                raise HomeAssistantError(
                    translation_domain=DOMAIN,
                    translation_key="cloud_api_not_initialized",
                )
            await self.coordinator.api.set_limit_discharge(False)

            # Clear optimistic state and invalidate cache to force immediate cloud refresh
            self._optimistic_state = None
            self.coordinator.invalidate_cloud_control_cache()
            await self.coordinator.async_request_refresh()
        except Exception as err:
            # Clear optimistic state on error
            self._optimistic_state = None
            self.async_write_ha_state()
            _LOGGER.error("Failed to disable Limit Discharge: %s", err)
            raise


class ReserveBatteryDischargeSwitch(CoordinatorEntity[EnphaseBatteryDataUpdateCoordinator], SwitchEntity):
    """Reserve Battery Discharge switch entity (rbdControl).

    When enabled: Battery discharge is limited/reserved
    When disabled: Battery can discharge freely
    """

    # Use __slots__ to reduce memory footprint
    __slots__ = ("_optimistic_state",)

    # Class-level attributes (shared across all instances)
    _attr_device_info = DEVICE_INFO
    _attr_has_entity_name = True
    _attr_icon = "mdi:battery-lock"

    def __init__(self, coordinator: EnphaseBatteryDataUpdateCoordinator) -> None:
        """Initialize the switch entity."""
        super().__init__(coordinator)
        self._attr_translation_key = "reserve_battery_discharge"
        self._attr_unique_id = f"{DOMAIN}_reserve_battery_discharge"
        self._optimistic_state: bool | None = None

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
        # Set optimistic state immediately for UI feedback
        self._optimistic_state = True
        self.async_write_ha_state()

        try:
            # Always use cloud API (pure cloud mode or hybrid mode)
            if not self.coordinator.api:
                raise HomeAssistantError(
                    translation_domain=DOMAIN,
                    translation_key="cloud_api_not_initialized",
                )
            await self.coordinator.api.set_reserve_battery_discharge(True)

            # Clear optimistic state and invalidate cache to force immediate cloud refresh
            self._optimistic_state = None
            self.coordinator.invalidate_cloud_control_cache()
            await self.coordinator.async_request_refresh()
        except Exception as err:
            # Clear optimistic state on error
            self._optimistic_state = None
            self.async_write_ha_state()
            _LOGGER.error("Failed to enable Reserve Battery Discharge: %s", err)
            raise

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off."""
        # Set optimistic state immediately for UI feedback
        self._optimistic_state = False
        self.async_write_ha_state()

        try:
            # Always use cloud API (pure cloud mode or hybrid mode)
            if not self.coordinator.api:
                raise HomeAssistantError(
                    translation_domain=DOMAIN,
                    translation_key="cloud_api_not_initialized",
                )
            await self.coordinator.api.set_reserve_battery_discharge(False)

            # Clear optimistic state and invalidate cache to force immediate cloud refresh
            self._optimistic_state = None
            self.coordinator.invalidate_cloud_control_cache()
            await self.coordinator.async_request_refresh()
        except Exception as err:
            # Clear optimistic state on error
            self._optimistic_state = None
            self.async_write_ha_state()
            _LOGGER.error("Failed to disable Reserve Battery Discharge: %s", err)
            raise


class PowerMatchSwitch(CoordinatorEntity[EnphaseBatteryDataUpdateCoordinator], SwitchEntity):
    """PowerMatch switch entity (powerMatchControl).

    PowerMatch optimizes battery usage to match grid power patterns.
    """

    # Use __slots__ to reduce memory footprint
    __slots__ = ("_optimistic_state",)

    # Class-level attributes (shared across all instances)
    _attr_device_info = DEVICE_INFO
    _attr_has_entity_name = True
    _attr_icon = "mdi:sine-wave"

    def __init__(self, coordinator: EnphaseBatteryDataUpdateCoordinator) -> None:
        """Initialize the switch entity."""
        super().__init__(coordinator)
        self._attr_translation_key = "power_match"
        self._attr_unique_id = f"{DOMAIN}_power_match"
        self._optimistic_state: bool | None = None

    @property
    def is_on(self) -> bool | None:
        """Return true if switch is on."""
        # Return optimistic state if set (during API call)
        if self._optimistic_state is not None:
            return self._optimistic_state

        if not self.coordinator.data:
            return None

        # Read from powerMatchControl.enabled
        return self.coordinator.data.get("power_match", False)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on."""
        # Set optimistic state immediately for UI feedback
        self._optimistic_state = True
        self.async_write_ha_state()

        try:
            # Always use cloud API (pure cloud mode or hybrid mode)
            if not self.coordinator.api:
                raise HomeAssistantError(
                    translation_domain=DOMAIN,
                    translation_key="cloud_api_not_initialized",
                )
            await self.coordinator.api.set_power_match(True)

            # Clear optimistic state and invalidate cache to force immediate cloud refresh
            self._optimistic_state = None
            self.coordinator.invalidate_cloud_control_cache()
            await self.coordinator.async_request_refresh()
        except Exception as err:
            # Clear optimistic state on error
            self._optimistic_state = None
            self.async_write_ha_state()
            _LOGGER.error("Failed to enable PowerMatch: %s", err)
            raise

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off."""
        # Set optimistic state immediately for UI feedback
        self._optimistic_state = False
        self.async_write_ha_state()

        try:
            # Always use cloud API (pure cloud mode or hybrid mode)
            if not self.coordinator.api:
                raise HomeAssistantError(
                    translation_domain=DOMAIN,
                    translation_key="cloud_api_not_initialized",
                )
            await self.coordinator.api.set_power_match(False)

            # Clear optimistic state and invalidate cache to force immediate cloud refresh
            self._optimistic_state = None
            self.coordinator.invalidate_cloud_control_cache()
            await self.coordinator.async_request_refresh()
        except Exception as err:
            # Clear optimistic state on error
            self._optimistic_state = None
            self.async_write_ha_state()
            _LOGGER.error("Failed to disable PowerMatch: %s", err)
            raise
