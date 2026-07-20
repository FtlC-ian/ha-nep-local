"""Local-only protocol support for NEP photovoltaic gateways.

These protocol primitives are staging code for the future Home Assistant
custom component; no standalone package metadata is shipped.
"""

from .client import EndpointPaths, NepGatewayClient
from .models import AggregateReading, InventoryModule, MinDatRecord, ModuleReading, ModuleStatus

__all__ = [
    "AggregateReading",
    "EndpointPaths",
    "InventoryModule",
    "MinDatRecord",
    "ModuleReading",
    "ModuleStatus",
    "NepGatewayClient",
]
