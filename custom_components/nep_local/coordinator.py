"""Data coordinator for NEP Local."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable
from dataclasses import dataclass
from datetime import datetime
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .client import NepGatewayClient
from .const import (
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    TELEMETRY_FUTURE_TOLERANCE,
    TELEMETRY_MAX_AGE,
)
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

    @staticmethod
    def _telemetry_is_fresh(record: MinDatRecord, now: datetime) -> bool:
        """Return whether a gateway-local telemetry timestamp is current."""
        now_utc = dt_util.as_utc(now)
        possible_ages = (
            now_utc
            - dt_util.as_utc(record.timestamp.replace(tzinfo=now.tzinfo, fold=fold))
            for fold in (0, 1)
        )
        return any(
            -TELEMETRY_FUTURE_TOLERANCE <= age <= TELEMETRY_MAX_AGE
            for age in possible_ages
        )

    async def _async_update_data(self) -> GatewayData:
        try:
            inventory = await self.client.inventory()
        except NepError as error:
            raise UpdateFailed(f"Unable to read gateway inventory: {error}") from error

        tasks: list[Awaitable[object]] = [self.client.aggregate()]
        for module in inventory.modules:
            tasks.append(self.client.module(module))
            tasks.append(self.client.min_dat(module))
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
            if telemetry is not None and not self._telemetry_is_fresh(
                telemetry, dt_util.now()
            ):
                _LOGGER.debug("Module telemetry endpoint returned a stale sample")
                telemetry = None
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
