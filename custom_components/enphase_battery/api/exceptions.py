"""Exceptions for the Enphase Battery API clients."""

from __future__ import annotations


# ---------------------------------------------------------------------------
# Cloud (Enlighten) API
# ---------------------------------------------------------------------------
class EnphaseBatteryApiError(Exception):
    """Base exception for Enphase Battery cloud API errors."""


class EnphaseBatteryAuthError(EnphaseBatteryApiError):
    """Authentication error (invalid credentials / expired session)."""


class EnphaseBatteryConnectionError(EnphaseBatteryApiError):
    """Connection error (network / timeout / unreachable)."""


class EnphaseBatteryRateLimitError(EnphaseBatteryApiError):
    """Rate limit exceeded error."""


# ---------------------------------------------------------------------------
# Local (Envoy/IQ Gateway) API
# ---------------------------------------------------------------------------
class EnvoyLocalApiError(Exception):
    """Base exception for Envoy local API errors."""


class EnvoyAuthError(EnvoyLocalApiError):
    """Authentication error (invalid token / credentials)."""


class EnvoyConnectionError(EnvoyLocalApiError):
    """Connection error (network / timeout / unreachable)."""
