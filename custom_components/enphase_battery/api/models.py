"""Typed data models for the Enphase Battery API clients.

These ``TypedDict`` definitions describe the normalized battery payload that the
cloud and local clients return and that the coordinator augments with derived
values. They are plain ``dict`` at runtime; the annotations document the shape
and let the type checker validate key access across the integration.
"""

from __future__ import annotations

from typing import Any, TypedDict


class BatteryDevice(TypedDict, total=False):
    """A single battery device as reported by the local Envoy inventory."""

    serial_num: str
    part_num: str
    type: str
    device_type: str
    percentFull: float
    temperature: float
    maxCellTemp: float
    encharge_capacity: int
    img_pnum_running: str
    reported_enc_grid_state: str


class BatteryData(TypedDict, total=False):
    """Normalized battery data shared by both clients and the coordinator.

    ``total=False`` because the available keys depend on the connection mode
    (local vs cloud), the firmware version, and which derived values the
    coordinator has computed so far.
    """

    # State of charge / health
    soc: int
    soh: int
    # Power (W, negative = charging, positive = discharging)
    power: int
    charge_power: int
    discharge_power: int
    # Energy (kWh)
    available_energy: int
    max_capacity: int
    total_energy_charged: float
    total_energy_discharged: float
    total_consumption: float
    total_production: float
    energy_charged_today: float
    energy_discharged_today: float
    consumption_24h: float
    estimated_backup_time: int
    # Configuration / control
    mode: str
    backup_reserve: int
    very_low_soc: int
    charge_from_grid: bool
    discharge_to_grid: bool
    reserve_battery_discharge: bool
    power_match: bool
    # System / diagnostics
    status: str
    temperature: float
    max_cell_temp: float
    devices: list[BatteryDevice]
    source: str
    timestamp: str
    last_update: str


# Raw, untyped API responses (Enlighten / Envoy JSON) before normalization.
RawApiResponse = dict[str, Any]
