"""System health for the Enphase Battery integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components import system_health
from homeassistant.core import HomeAssistant, callback

from .api.cloud_client import API_BASE_URL


@callback
def async_register(hass: HomeAssistant, register: system_health.SystemHealthRegistration) -> None:
    """Register system health callbacks."""
    register.async_register_info(_async_system_health_info)


async def _async_system_health_info(hass: HomeAssistant) -> dict[str, Any]:
    """Return information for the System Health panel."""
    return {
        "can_reach_cloud": system_health.async_check_can_reach_url(hass, API_BASE_URL),
    }
