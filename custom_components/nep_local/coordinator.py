"""Data coordinator for NEP Local."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .client import NepGatewayClient
from .const import DEFAULT_SCAN_INTERVAL, DOMAIN
from .exceptions import NepError
from .models import AggregateReading, GatewayInventory, MinDatRecord, ModuleReading

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class ModuleData:
    """Best available readings for one discovered logical input."""

    reading: ModuleReading | None
    telemetry: MinDatRecord | None


@dataclass(frozen=True)
class GatewayData:
    """One coordinated gateway snapshot."""

    inventory: GatewayInventory
    aggregate: AggregateReading | None
    modules: dict[str, ModuleData]


class NepDataUpdateCoordinator(DataUpdateCoordinator[GatewayData]):
    """Poll inventory, aggregate, and all discovered modules together."""

    config_entry: ConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        client: NepGatewayClient,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=config_entry,
            name=DOMAIN,
            update_interval=DEFAULT_SCAN_INTERVAL,
        )
        self.client = client

    async def _async_update_data(self) -> GatewayData:
        try:
            inventory = await self.client.inventory()
        except NepError as error:
            raise UpdateFailed(f"Unable to read gateway inventory: {error}") from error

        tasks: list[asyncio.Task[object]] = [
            asyncio.create_task(self.client.aggregate())
        ]
        for module in inventory.modules:
            tasks.append(asyncio.create_task(self.client.module(module)))
            tasks.append(asyncio.create_task(self.client.min_dat(module)))
        results = await asyncio.gather(*tasks, return_exceptions=True)

        aggregate = results[0] if isinstance(results[0], AggregateReading) else None
        if isinstance(results[0], Exception):
            _LOGGER.debug(
                "Aggregate endpoint failed with %s", type(results[0]).__name__
            )
        modules: dict[str, ModuleData] = {}
        successful_readings = int(aggregate is not None)
        for index, module in enumerate(inventory.modules):
            reading_result = results[1 + index * 2]
            telemetry_result = results[2 + index * 2]
            reading = (
                reading_result if isinstance(reading_result, ModuleReading) else None
            )
            telemetry = (
                telemetry_result if isinstance(telemetry_result, MinDatRecord) else None
            )
            if isinstance(reading_result, Exception):
                _LOGGER.debug(
                    "Module live endpoint failed with %s",
                    type(reading_result).__name__,
                )
            if isinstance(telemetry_result, Exception):
                _LOGGER.debug(
                    "Module telemetry endpoint failed with %s",
                    type(telemetry_result).__name__,
                )
            successful_readings += int(reading is not None or telemetry is not None)
            modules[module.raw_id] = ModuleData(reading=reading, telemetry=telemetry)

        if successful_readings == 0:
            raise UpdateFailed(
                "Gateway inventory responded, but no measurements were readable"
            )
        return GatewayData(inventory=inventory, aggregate=aggregate, modules=modules)
