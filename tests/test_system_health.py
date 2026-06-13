"""Tests for the Enphase Battery system_health."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from homeassistant.core import HomeAssistant

from custom_components.enphase_battery import system_health


def test_async_register() -> None:
    """async_register wires the info callback."""
    register = MagicMock()
    system_health.async_register(MagicMock(), register)
    register.async_register_info.assert_called_once()


async def test_system_health_info(hass: HomeAssistant) -> None:
    """The info dict reports cloud reachability."""
    # async_check_can_reach_url is a sync callback returning an awaitable; patch
    # it with a plain MagicMock so the value lands in the info dict as-is.
    mock_check = MagicMock(return_value="reachable")
    with patch(
        "custom_components.enphase_battery.system_health.system_health.async_check_can_reach_url",
        new=mock_check,
    ):
        info = await system_health._async_system_health_info(hass)

    assert info == {"can_reach_cloud": "reachable"}
    mock_check.assert_called_once()
