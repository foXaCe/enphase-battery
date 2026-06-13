"""Switch platform for Enphase Battery."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
import logging
from typing import TYPE_CHECKING, Any

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_ENABLE_CLOUD_CONTROL, DEVICE_INFO, DOMAIN
from .coordinator import EnphaseBatteryDataUpdateCoordinator

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from . import EnphaseBatteryConfigEntry
    from .api import EnphaseBatteryAPI

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 1


@dataclass(frozen=True, kw_only=True)
class EnphaseBatterySwitchEntityDescription(SwitchEntityDescription):
    """Describes an Enphase Battery switch.

    ``set_fn`` performs the cloud API call; the switch's data key (read from
    ``coordinator.data``) and translation key both equal ``key``.
    """

    set_fn: Callable[[EnphaseBatteryAPI, bool], Awaitable[bool]]


SWITCHES: tuple[EnphaseBatterySwitchEntityDescription, ...] = (
    EnphaseBatterySwitchEntityDescription(
        key="charge_from_grid",
        translation_key="charge_from_grid",
        icon="mdi:transmission-tower-import",
        set_fn=lambda api, enabled: api.set_charge_from_grid(enabled),
    ),
    EnphaseBatterySwitchEntityDescription(
        key="discharge_to_grid",
        translation_key="discharge_to_grid",
        icon="mdi:transmission-tower-export",
        set_fn=lambda api, enabled: api.set_limit_discharge(enabled),
    ),
    EnphaseBatterySwitchEntityDescription(
        key="reserve_battery_discharge",
        translation_key="reserve_battery_discharge",
        icon="mdi:battery-lock",
        set_fn=lambda api, enabled: api.set_reserve_battery_discharge(enabled),
    ),
    EnphaseBatterySwitchEntityDescription(
        key="power_match",
        translation_key="power_match",
        icon="mdi:sine-wave",
        set_fn=lambda api, enabled: api.set_power_match(enabled),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: EnphaseBatteryConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Enphase Battery switch platform."""
    coordinator = entry.runtime_data.coordinator

    # Switches are available in cloud mode (always) and in local mode only when
    # cloud control is enabled (hybrid). Envoy firmware 8.x no longer supports
    # battery control via the local API.
    enable_cloud_control = entry.data.get(CONF_ENABLE_CLOUD_CONTROL, False)

    if coordinator.is_local_mode and not enable_cloud_control:
        _LOGGER.warning(
            "Battery control switches disabled. "
            "Envoy firmware 8.x no longer supports battery control via local API. "
            "Enable 'Cloud Control' in the integration settings or use the Enphase app."
        )
        return

    async_add_entities(EnphaseBatterySwitch(coordinator, description) for description in SWITCHES)


class EnphaseBatterySwitch(CoordinatorEntity[EnphaseBatteryDataUpdateCoordinator], SwitchEntity):
    """A cloud-controlled Enphase Battery switch."""

    entity_description: EnphaseBatterySwitchEntityDescription
    _attr_device_info = DEVICE_INFO
    _attr_has_entity_name = True

    __slots__ = ("_optimistic_state",)

    def __init__(
        self,
        coordinator: EnphaseBatteryDataUpdateCoordinator,
        description: EnphaseBatterySwitchEntityDescription,
    ) -> None:
        """Initialize the switch entity."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.unique_id_prefix}_{description.key}"
        self._optimistic_state: bool | None = None

    @property
    def is_on(self) -> bool | None:
        """Return true if the switch is on."""
        # Optimistic state shown while a control request is in flight.
        if self._optimistic_state is not None:
            return self._optimistic_state
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get(self.entity_description.key, False)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on."""
        await self._async_set_state(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off."""
        await self._async_set_state(False)

    async def _async_set_state(self, state: bool) -> None:
        """Apply the new state via the cloud API with optimistic UI feedback."""
        self._optimistic_state = state
        self.async_write_ha_state()

        try:
            if not self.coordinator.api:
                raise HomeAssistantError(
                    translation_domain=DOMAIN,
                    translation_key="cloud_api_not_initialized",
                )
            await self.entity_description.set_fn(self.coordinator.api, state)

            # Force the next refresh to read the fresh value from the cloud.
            self._optimistic_state = None
            self.coordinator.invalidate_cloud_control_cache()
            await self.coordinator.async_request_refresh()
        except Exception as err:
            self._optimistic_state = None
            self.async_write_ha_state()
            _LOGGER.error("Failed to set %s to %s: %s", self.entity_description.key, state, err)
            raise
