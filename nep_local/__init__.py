"""Local-only protocol support for NEP photovoltaic gateways.

This package deliberately contains no Home Assistant imports.  The HA
integration layer can depend on these small, testable protocol primitives.
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
