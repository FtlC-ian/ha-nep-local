"""Async local HTTP client for an NEP BDG-256 gateway."""

from __future__ import annotations

import asyncio
import json
from time import time
from urllib.parse import quote

from aiohttp import ClientError, ClientSession, ClientTimeout

from .const import MAX_CONCURRENT_REQUESTS, MISSING_SLOT_LIMIT, SLOT_END, SLOT_START
from .exceptions import NepConnectionError, NepInvalidResponse, NepResponseMissing
from .models import (
    AggregateReading,
    GatewayInventory,
    InventoryModule,
    MinDatRecord,
    ModuleReading,
)
from .parsers import (
    parse_aggregate_json,
    parse_inventory_page,
    parse_min_dat,
    parse_module_json,
    parse_module_registry,
)

INVENTORY_PATH = "/nep/status/index/"
STATUS_PATH = "/nep/static/local/{address}_status/{cachebuster}"
MIN_DAT_PATH = "/data/{address}/min.dat"
REQUEST_TIMEOUT = ClientTimeout(total=10)


class NepGatewayClient:
    """Read the gateway using a Home Assistant-owned aiohttp session."""

    def __init__(self, session: ClientSession, base_url: str) -> None:
        if not base_url.startswith(("http://", "https://")):
            raise ValueError("base_url must include http:// or https://")
        self._session = session
        self._base_url = base_url.rstrip("/")
        self._request_semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)

    def _url(self, path: str) -> str:
        return f"{self._base_url}/{path.lstrip('/')}"

    async def _get_text(
        self, path: str, *, headers: dict[str, str] | None = None
    ) -> str:
        try:
            async with (
                self._request_semaphore,
                self._session.get(
                    self._url(path), headers=headers, timeout=REQUEST_TIMEOUT
                ) as response,
            ):
                if response.status in (204, 404):
                    raise NepResponseMissing(f"{path}: HTTP {response.status}")
                if response.status >= 400:
                    raise NepInvalidResponse(f"{path}: HTTP {response.status}")
                text = await response.text()
        except (TimeoutError, ClientError) as error:
            raise NepConnectionError(f"cannot connect to {self._base_url}") from error
        if not text.strip():
            raise NepResponseMissing(f"{path}: empty response")
        return text

    async def _get_json(self, path: str) -> object:
        text = await self._get_text(path)
        try:
            return json.loads(text)
        except (TypeError, ValueError) as error:
            raise NepInvalidResponse(f"{path}: invalid JSON") from error

    @staticmethod
    def _cachebuster() -> str:
        return str(int(time() * 1000))

    async def inventory(self) -> GatewayInventory:
        return parse_inventory_page(await self._get_text(INVENTORY_PATH))

    async def aggregate(self) -> AggregateReading:
        path = STATUS_PATH.format(address="0", cachebuster=self._cachebuster())
        return parse_aggregate_json(await self._get_json(path))

    async def fallback_inventory(self, serial: str) -> GatewayInventory:
        """Read registry identities, retaining the configured gateway serial."""
        if not serial:
            raise NepInvalidResponse("fallback requires the gateway serial number")
        html = await self._get_text("/module/")
        try:
            modules = parse_module_registry(html)
        except NepInvalidResponse:
            modules = parse_module_registry(await self._get_json("/module/module.php"))
        return GatewayInventory(serial, modules, fallback=True)

    async def scan_slots(
        self, registered_slots: set[int] | None = None
    ) -> dict[int, MinDatRecord]:
        """Bound discovery and stop only for consecutive absent files."""
        records = {}
        missing = 0
        last_registered = max(
            (slot for slot in registered_slots or () if SLOT_START <= slot <= SLOT_END),
            default=SLOT_START - 1,
        )
        for slot in range(SLOT_START, SLOT_END + 1):
            try:
                record = await self.min_dat(InventoryModule(str(slot), "", slot=slot))
            except NepResponseMissing:
                missing += 1
                if missing >= MISSING_SLOT_LIMIT and slot >= last_registered:
                    break
            except NepInvalidResponse:
                missing = 0
            else:
                missing = 0
                records[slot] = record
        return records

    async def module(self, module: InventoryModule) -> ModuleReading:
        path = STATUS_PATH.format(
            address=quote(module.address, safe=""), cachebuster=self._cachebuster()
        )
        return parse_module_json(
            await self._get_json(path), address=module.address, raw_id=module.raw_id
        )

    async def min_dat(self, module: InventoryModule) -> MinDatRecord:
        """Return the newest complete rich record from a bounded file tail."""
        address = str(module.slot) if module.slot is not None else module.address
        path = MIN_DAT_PATH.format(address=quote(address, safe=""))
        records = parse_min_dat(
            await self._get_text(path, headers={"Range": "bytes=-1024"})
        )
        return records[-1]
