"""Defensive parsers for the loosely-versioned NEP local web interface."""

from __future__ import annotations

import csv
import io
import re
from html.parser import HTMLParser
from typing import Any, Iterable

from .exceptions import NepInvalidResponse
from .models import AggregateReading, InventoryModule, MinDatRecord, ModuleReading, ModuleStatus

_KEY_NORMALIZE = re.compile(r"[^a-z0-9]+")
_ADDRESS_RE = re.compile(r"(?:addr(?:ess)?|id)\s*=\s*([A-Za-z0-9_.:-]+)", re.I)


def _key(value: str) -> str:
    return _KEY_NORMALIZE.sub("", value.lower())


def _first(mapping: dict[str, Any], *names: str) -> Any:
    normalized = {_key(str(key)): value for key, value in mapping.items()}
    for name in names:
        value = normalized.get(_key(name))
        if value not in (None, ""):
            return value
    return None


def _number(value: Any, field: str) -> float | None:
    if value in (None, "", "--", "N/A", "null"):
        return None
    if isinstance(value, bool):
        raise NepInvalidResponse(f"{field} must be numeric")
    try:
        return float(str(value).strip().replace(",", ""))
    except (TypeError, ValueError) as error:
        raise NepInvalidResponse(f"{field} must be numeric") from error


def _integer(value: Any, field: str) -> int | None:
    numeric = _number(value, field)
    return None if numeric is None else int(numeric)


class _InventoryTableParser(HTMLParser):
    """Small tolerant table parser; gateways often emit malformed HTML."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[tuple[list[str], dict[str, str]]] = []
        self._cells: list[str] | None = None
        self._cell: list[str] | None = None
        self._attrs: dict[str, str] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "tr":
            self._cells, self._attrs = [], {k.lower(): v or "" for k, v in attrs}
        elif tag in {"td", "th"} and self._cells is not None:
            self._cell = []
        elif tag == "a" and self._cells is not None:
            href = dict(attrs).get("href", "")
            found = _ADDRESS_RE.search(href)
            if found:
                self._attrs.setdefault("href_address", found.group(1))

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"td", "th"} and self._cell is not None and self._cells is not None:
            self._cells.append("".join(self._cell).strip())
            self._cell = None
        elif tag == "tr" and self._cells is not None:
            self.rows.append((self._cells, self._attrs))
            self._cells = None


def parse_inventory_page(payload: str) -> list[InventoryModule]:
    if not isinstance(payload, str) or not payload.strip():
        raise NepInvalidResponse("inventory page is empty")
    parser = _InventoryTableParser()
    parser.feed(payload)
    headers: list[str] | None = None
    found: dict[str, InventoryModule] = {}
    for cells, attrs in parser.rows:
        normalized = [_key(value) for value in cells]
        if any(value in {"address", "moduleid", "serialnumber", "sn"} for value in normalized):
            headers = normalized
            continue
        row = dict(zip(headers or [], cells))
        address = attrs.get("data-address") or attrs.get("data-addr") or attrs.get("href_address")
        address = address or _first(row, "address", "module address", "addr")
        raw_id = attrs.get("data-module-id") or attrs.get("data-id")
        raw_id = raw_id or _first(row, "module id", "serial number", "serial", "sn", "id")
        if address is None or raw_id is None:
            continue
        address, raw_id = str(address).strip(), str(raw_id).strip()
        if address and raw_id:
            found[raw_id] = InventoryModule(address=address, raw_id=raw_id, name=_first(row, "name", "module name"))
    if not found:
        raise NepInvalidResponse("no module inventory rows found")
    return list(found.values())


def _object(payload: Any, endpoint: str) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise NepInvalidResponse(f"{endpoint} response must be a JSON object")
    # Some firmware wraps readings one level below a familiar envelope key.
    for key in ("data", "result", "overview", "module"):
        if isinstance(payload.get(key), dict):
            return payload[key]
    return payload


def parse_aggregate_json(payload: Any) -> AggregateReading:
    data = _object(payload, "aggregate")
    return AggregateReading(
        power_w=_number(_first(data, "power", "power w", "pac", "total power"), "aggregate power"),
        energy_wh=_number(_first(data, "energy", "energy wh", "e today", "today energy"), "aggregate energy"),
        raw=data,
    )


def parse_module_json(payload: Any, *, address: str, raw_id: str) -> ModuleReading:
    data = _object(payload, "module")
    status_code = _integer(_first(data, "status", "status code", "state"), "module status")
    status = ModuleStatus.LOW_LIGHT if status_code == 8000 else ModuleStatus.OK if status_code == 0 else ModuleStatus.FAULT if status_code is not None else ModuleStatus.UNKNOWN
    return ModuleReading(
        raw_id=str(_first(data, "module id", "serial", "sn", "id") or raw_id),
        address=address,
        power_w=_number(_first(data, "power", "power w", "pac"), "module power"),
        energy_wh=_number(_first(data, "energy", "energy wh", "e today"), "module energy"),
        voltage_v=_number(_first(data, "voltage", "voltage v", "vac"), "module voltage"),
        status_code=status_code,
        status=status,
        raw=data,
    )


def parse_min_dat(payload: str) -> list[MinDatRecord]:
    if not isinstance(payload, str) or not payload.strip():
        raise NepInvalidResponse("min.dat is empty")
    records: list[MinDatRecord] = []
    for line in payload.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            values = {key.strip(): value.strip() for key, value in (part.split("=", 1) for part in line.split(";")) if key.strip()}
        else:
            row = next(csv.reader(io.StringIO(line)))
            values = {str(index): value.strip() for index, value in enumerate(row) if value.strip()}
        if values:
            records.append(MinDatRecord(values=values))
    if not records:
        raise NepInvalidResponse("min.dat contains no records")
    return records
