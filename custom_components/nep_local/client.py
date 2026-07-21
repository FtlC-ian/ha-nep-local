"""Async local HTTP client for an NEP BDG-256 gateway."""

from __future__ import annotations

import asyncio
import json
from time import time
from urllib.parse import quote

from aiohttp import ClientError, ClientSession, ClientTimeout

from .const import MAX_CONCURRENT_REQUESTS
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
            async with self._request_semaphore:
                async with self._session.get(
                    self._url(path), headers=headers, timeout=REQUEST_TIMEOUT
                ) as response:
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

    async def module(self, module: InventoryModule) -> ModuleReading:
        path = STATUS_PATH.format(
            address=quote(module.address, safe=""), cachebuster=self._cachebuster()
        )
        return parse_module_json(
            await self._get_json(path), address=module.address, raw_id=module.raw_id
        )

    async def min_dat(self, module: InventoryModule) -> MinDatRecord:
        """Return the newest complete rich record from a bounded file tail."""
        path = MIN_DAT_PATH.format(address=quote(module.address, safe=""))
        records = parse_min_dat(
            await self._get_text(path, headers={"Range": "bytes=-1024"})
        )
        return records[-1]
