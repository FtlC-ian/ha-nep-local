"""Typed values returned by the NEP gateway local interface."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ModuleStatus(str, Enum):
    """Normalized module status."""

    OK = "ok"
    LOW_LIGHT = "low_light"
    FAULT = "fault"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class InventoryModule:
    """A routable address and stable M_ID from the status overview."""

    address: str
    raw_id: str

    @property
    def inverter_id(self) -> str:
        """Return the physical dual-input inverter identifier when derivable."""
        try:
            value = int(self.raw_id, 16)
        except ValueError:
            return self.raw_id
        return f"0X{value & ~1:08X}"


@dataclass(frozen=True)
class GatewayInventory:
    """Gateway identity and its discovered logical module inputs."""

    serial: str
    modules: tuple[InventoryModule, ...]

    def physical_inverter_id(self, module: InventoryModule) -> str:
        """Pair inputs only when the inventory proves a low-bit channel pair."""
        candidates = [
            candidate
            for candidate in self.modules
            if candidate.inverter_id == module.inverter_id
        ]
        if len(candidates) != 2:
            return module.raw_id
        try:
            values = {int(candidate.raw_id, 16) for candidate in candidates}
        except ValueError:
            return module.raw_id
        return module.inverter_id if len(values) == 2 else module.raw_id


@dataclass(frozen=True)
class AggregateReading:
    """Live gateway aggregate values."""

    power_w: float | None = None
    today_wh: float | None = None
    total_wh: float | None = None
    status_code: str | None = None
    raw: dict[str, Any] = field(default_factory=dict, compare=False, repr=False)


@dataclass(frozen=True)
class ModuleReading:
    """Live logical module values."""

    raw_id: str
    address: str
    power_w: float | None = None
    today_wh: float | None = None
    total_wh: float | None = None
    status_code: str | None = None
    status: ModuleStatus = ModuleStatus.UNKNOWN
    raw: dict[str, Any] = field(default_factory=dict, compare=False, repr=False)


@dataclass(frozen=True)
class MinDatRecord:
    """One complete min.dat record, normalized to W and Wh."""

    timestamp: str
    power_w: float | None
    voltage_dc_v: float | None
    voltage_ac_v: float | None
    current_a: float | None
    frequency_hz: float | None
    temperature_c: float | None
    energy_wh: float | None
    rssi: float | None
    diagnostic_code: str
    status_code: str
