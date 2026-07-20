"""Async local HTTP client for a NEP gateway.

The caller owns the aiohttp session; this prevents hidden session lifetime and
keeps all traffic explicitly local to the configured gateway URL.
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import quote

from aiohttp import ClientSession

from .exceptions import NepInvalidResponse, NepResponseMissing
from .models import AggregateReading, InventoryModule, MinDatRecord, ModuleReading
from .parsers import parse_aggregate_json, parse_inventory_page, parse_min_dat, parse_module_json


@dataclass(frozen=True)
class EndpointPaths:
    inventory: str = "/"
    aggregate: str = "/api/aggregate.json"
    module: str = "/api/modules/{address}.json"
    min_dat: str = "/min.dat"


class NepGatewayClient:
    def __init__(self, session: ClientSession, base_url: str, paths: EndpointPaths | None = None) -> None:
        if not base_url.startswith(("http://", "https://")):
            raise ValueError("base_url must include http:// or https://")
        self._session = session
        self._base_url = base_url.rstrip("/")
        self._paths = paths or EndpointPaths()

    def _url(self, path: str) -> str:
        return f"{self._base_url}/{path.lstrip('/')}"

    async def _get_text(self, path: str) -> str:
        async with self._session.get(self._url(path)) as response:
            if response.status in (204, 404):
                raise NepResponseMissing(f"{path}: HTTP {response.status}")
            if response.status >= 400:
                raise NepInvalidResponse(f"{path}: HTTP {response.status}")
            text = await response.text()
        if not text.strip():
            raise NepResponseMissing(f"{path}: empty response")
        return text

    async def _get_json(self, path: str) -> object:
        text = await self._get_text(path)
        try:
            import json
            return json.loads(text)
        except (TypeError, ValueError) as error:
            raise NepInvalidResponse(f"{path}: invalid JSON") from error

    async def inventory(self) -> list[InventoryModule]:
        return parse_inventory_page(await self._get_text(self._paths.inventory))

    async def aggregate(self) -> AggregateReading:
        return parse_aggregate_json(await self._get_json(self._paths.aggregate))

    async def module(self, module: InventoryModule) -> ModuleReading:
        path = self._paths.module.format(address=quote(module.address, safe=""))
        return parse_module_json(await self._get_json(path), address=module.address, raw_id=module.raw_id)

    async def min_dat(self) -> list[MinDatRecord]:
        return parse_min_dat(await self._get_text(self._paths.min_dat))
