"""Enphase Battery API clients (cloud Enlighten + local Envoy)."""

from __future__ import annotations

from .cloud_client import EnphaseBatteryAPI
from .exceptions import (
    EnphaseBatteryApiError,
    EnphaseBatteryAuthError,
    EnphaseBatteryConnectionError,
    EnphaseBatteryRateLimitError,
    EnvoyAuthError,
    EnvoyConnectionError,
    EnvoyLocalApiError,
)
from .local_client import EnphaseEnvoyLocalAPI
from .models import BatteryData, BatteryDevice

__all__ = [
    "BatteryData",
    "BatteryDevice",
    "EnphaseBatteryAPI",
    "EnphaseBatteryApiError",
    "EnphaseBatteryAuthError",
    "EnphaseBatteryConnectionError",
    "EnphaseBatteryRateLimitError",
    "EnphaseEnvoyLocalAPI",
    "EnvoyAuthError",
    "EnvoyConnectionError",
    "EnvoyLocalApiError",
]
