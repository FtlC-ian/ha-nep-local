"""Data coordinator for NEP Local."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable
from dataclasses import dataclass, field, replace
from datetime import datetime

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .client import NepGatewayClient
from .const import (
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    FALLBACK_ENABLED,
    TELEMETRY_FUTURE_TOLERANCE,
    TELEMETRY_MAX_AGE,
)
from .exceptions import NepError
from .models import (
    AggregateReading,
    GatewayInventory,
    InventoryModule,
    MinDatRecord,
    ModuleReading,
)
from .parsers import parse_module_json

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
    aggregate_check: dict[str, object] = field(default_factory=dict)


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
            inventory = self._preserve_registered_ids(await self.client.inventory())
        except NepError as error:
            if not FALLBACK_ENABLED:
                raise UpdateFailed(
                    f"Unable to read gateway inventory: {error}"
                ) from error
            try:
                return await self._async_fallback_data()
            except NepError as fallback_error:
                raise UpdateFailed(
                    f"Unable to read slot telemetry: {fallback_error}"
                ) from fallback_error

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

    def _preserve_registered_ids(self, inventory: GatewayInventory) -> GatewayInventory:
        registry = er.async_get(self.hass)
        registered_ids = {
            entity.unique_id
            for entity in er.async_entries_for_config_entry(
                registry, self.config_entry.entry_id
            )
            if entity.platform == DOMAIN
        }
        modules_by_identity = []
        for module in inventory.modules:
            spellings = (module.raw_id, module.raw_id.removeprefix("0X"))
            matches = {
                raw_id
                for raw_id in spellings
                if any(
                    entity_id.startswith(f"{inventory.serial}_{raw_id}_")
                    for entity_id in registered_ids
                )
            }
            if len(matches) > 1:
                raise UpdateFailed(
                    "Conflicting registered COM-ID spellings; refusing to split history"
                )
            modules_by_identity.append(
                replace(module, raw_id=next(iter(matches), module.raw_id))
            )
        return replace(inventory, modules=tuple(modules_by_identity))

    async def _async_fallback_data(self) -> GatewayData:
        inventory = self._preserve_registered_ids(
            await self.client.fallback_inventory(self.config_entry.unique_id or "")
        )
        records = await self.client.scan_slots(
            {module.slot for module in inventory.modules if module.slot is not None}
        )
        now = dt_util.now()
        records = {
            slot: record
            for slot, record in records.items()
            if self._telemetry_is_fresh(record, now)
        }
        try:
            gateway_record = await self.client.min_dat(InventoryModule("0", "", slot=0))
        except NepError:
            gateway_record = None
        if gateway_record is not None and not self._telemetry_is_fresh(
            gateway_record, now
        ):
            gateway_record = None
        modules = {}
        for module in inventory.modules:
            telemetry = records.get(module.slot)
            if telemetry is not None and not telemetry.has_measurements:
                telemetry = None
            reading = None
            if telemetry is not None:
                reading = parse_module_json(
                    {
                        "now": telemetry.power_w,
                        "today": telemetry.energy_wh,
                        "status": telemetry.status_code,
                    },
                    address=module.address,
                    raw_id=module.raw_id,
                )
            modules[module.raw_id] = ModuleData(reading, telemetry)
        if gateway_record is None and not any(
            data.reading is not None for data in modules.values()
        ):
            raise UpdateFailed("No fresh registered slot measurements were readable")
        readings = [data.reading for data in modules.values()]

        def complete_sum(attribute: str) -> float | None:
            values = [
                getattr(reading, attribute) if reading else None for reading in readings
            ]
            return sum(values) if all(value is not None for value in values) else None

        aggregate = AggregateReading(
            power_w=gateway_record.power_w
            if gateway_record
            else complete_sum("power_w"),
            today_wh=gateway_record.energy_wh
            if gateway_record
            else complete_sum("today_wh"),
            total_wh=complete_sum("total_wh"),
        )
        channel_records = [records.get(module.slot) for module in inventory.modules]

        def raw_sum(attribute: str) -> float | None:
            if any(
                record is None or getattr(record, attribute) is None
                for record in channel_records
            ):
                return None
            return sum(getattr(record, attribute) for record in channel_records)

        power_sum = raw_sum("power_w")
        today_sum = raw_sum("energy_wh")
        check = {
            "source": "min_dat_slot_0" if gateway_record else "complete_channel_sum",
            "gateway_timestamp": gateway_record.timestamp.isoformat()
            if gateway_record
            else None,
            "channel_timestamps": sorted(
                {
                    record.timestamp.isoformat()
                    for record in channel_records
                    if record is not None
                }
            ),
            "fresh_channel_records": sum(
                record is not None for record in channel_records
            ),
            "reporting_channels": sum(
                data.reading is not None for data in modules.values()
            ),
            "channel_power_w": power_sum,
            "channel_today_wh": today_sum,
            "power_delta_w": gateway_record.power_w - power_sum
            if gateway_record and power_sum is not None
            else None,
            "today_delta_wh": gateway_record.energy_wh - today_sum
            if gateway_record and today_sum is not None
            else None,
        }
        return GatewayData(inventory, aggregate, modules, check)
