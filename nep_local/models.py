"""Typed values returned by a NEP gateway.

Numeric readings are optional on purpose: ``0.0`` is a valid measured value,
whereas ``None`` means the gateway did not provide a usable value.
"""

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
    """A module found on the gateway inventory page.

    ``address`` is the currently routable gateway address and can change after
    rediscovery.  ``raw_id`` is the gateway's unmodified module identifier and
    is the stable identity consumers should persist.
    """

    address: str
    raw_id: str
    name: str | None = None


@dataclass(frozen=True)
class AggregateReading:
    power_w: float | None = None
    energy_wh: float | None = None
    raw: dict[str, Any] = field(default_factory=dict, compare=False, repr=False)


@dataclass(frozen=True)
class ModuleReading:
    raw_id: str
    address: str
    power_w: float | None = None
    energy_wh: float | None = None
    voltage_v: float | None = None
    status_code: int | None = None
    status: ModuleStatus = ModuleStatus.UNKNOWN
    # Status 8000 is a valid low-light report, not an unavailable device.
    transport_healthy: bool = True
    raw: dict[str, Any] = field(default_factory=dict, compare=False, repr=False)


@dataclass(frozen=True)
class MinDatRecord:
    """One unmodified-key record parsed from ``min.dat``."""

    values: dict[str, str]
