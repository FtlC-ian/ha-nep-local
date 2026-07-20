"""Typed values returned by the NEP gateway's local web interface."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ModuleStatus(str, Enum):
    OK = "ok"
    LOW_LIGHT = "low_light"
    FAULT = "fault"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class InventoryModule:
    """A routable ``addr`` and stable ``M_ID`` from the status overview."""

    address: str
    raw_id: str
    name: str | None = None


@dataclass(frozen=True)
class AggregateReading:
    power_w: float | None = None
    today_wh: float | None = None
    total_wh: float | None = None
    status_code: str | None = None
    raw: dict[str, Any] = field(default_factory=dict, compare=False, repr=False)


@dataclass(frozen=True)
class ModuleReading:
    raw_id: str
    address: str
    power_w: float | None = None
    today_wh: float | None = None
    total_wh: float | None = None
    status_code: str | None = None
    status: ModuleStatus = ModuleStatus.UNKNOWN
    # A parsed response proves transport health, including status ``8000``.
    transport_healthy: bool = True
    raw: dict[str, Any] = field(default_factory=dict, compare=False, repr=False)


@dataclass(frozen=True)
class MinDatRecord:
    """One complete ``/data/{address}/min.dat`` record, normalized to W/Wh."""

    timestamp: str
    power_w: float
    voltage_dc_v: float
    voltage_ac_v: float
    current_a: float
    frequency_hz: float
    # The gateway uses -100 as an unavailable-temperature sentinel.
    temperature_c: float | None
    energy_wh: float
    rssi: float
    firmware: str
    status_code: str
