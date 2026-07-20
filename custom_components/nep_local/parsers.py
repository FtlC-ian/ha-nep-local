"""Defensive parsers for observed NEP BDG-256 response shapes."""

from __future__ import annotations

import re
from html.parser import HTMLParser
from typing import Any

from .exceptions import NepInvalidResponse
from .models import (
    AggregateReading,
    GatewayInventory,
    InventoryModule,
    MinDatRecord,
    ModuleReading,
    ModuleStatus,
)

_MODULE_ID_RE = re.compile(r"(?:^|\s)M_ID\s*:\s*([^\s]+)", re.IGNORECASE)
_SERIAL_RE = re.compile(
    r"(?:gateway\s+)?(?:serial(?:\s+(?:number|no\.?))?|s/?n)\s*[:：]\s*([A-Za-z0-9_-]+)",
    re.IGNORECASE,
)
_GATEWAY_TABLE_RE = re.compile(
    r"<td[^>]*>\s*Gateway\s*</td>\s*<td[^>]*>\s*([^<\s]+)", re.IGNORECASE
)
_STATUS_RE = re.compile(r"^[0-9a-fA-F]+$")
_MISSING = {"", "--", "N/A", "null"}


def parse_optional_number(value: Any, field: str) -> float | None:
    if value is None or str(value).strip() in _MISSING:
        return None
    if isinstance(value, bool):
        raise NepInvalidResponse(f"{field} must be numeric")
    try:
        return float(str(value).strip().replace(",", ""))
    except (TypeError, ValueError) as error:
        raise NepInvalidResponse(f"{field} must be numeric") from error


def _status(value: Any, field: str) -> str | None:
    if value is None or str(value).strip() in _MISSING:
        return None
    if isinstance(value, bool):
        raise NepInvalidResponse(f"{field} must be a hexadecimal status string")
    status = str(value).strip()
    if not _STATUS_RE.fullmatch(status):
        raise NepInvalidResponse(f"{field} must be a hexadecimal status string")
    return status.upper().zfill(4)


class _InventoryParser(HTMLParser):
    """Collect module div attributes and visible overview text."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.boxes: list[dict[str, str]] = []
        self.text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "div":
            return
        values = {key.lower(): value or "" for key, value in attrs}
        if "box" in values.get("class", "").lower().split():
            self.boxes.append(values)

    def handle_data(self, data: str) -> None:
        if data.strip():
            self.text.append(data.strip())


def parse_inventory_page(payload: str) -> GatewayInventory:
    """Parse gateway serial and all logical module inputs from overview HTML."""
    if not isinstance(payload, str) or not payload.strip():
        raise NepInvalidResponse("inventory page is empty")
    parser = _InventoryParser()
    parser.feed(payload)
    text = " ".join(parser.text)
    serial_match = _SERIAL_RE.search(text) or _GATEWAY_TABLE_RE.search(payload)
    if serial_match is None:
        raise NepInvalidResponse("gateway serial not found")

    found: dict[str, InventoryModule] = {}
    for attrs in parser.boxes:
        address = attrs.get("addr", "").strip()
        raw_id_match = _MODULE_ID_RE.search(attrs.get("title", ""))
        if address and raw_id_match:
            raw_id = raw_id_match.group(1).strip().upper()
            found[raw_id] = InventoryModule(address=address, raw_id=raw_id)
    if not found:
        raise NepInvalidResponse("no module inventory boxes found")
    modules = tuple(sorted(found.values(), key=lambda module: int(module.address)))
    return GatewayInventory(serial=serial_match.group(1), modules=modules)


def _object(payload: Any, endpoint: str) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise NepInvalidResponse(f"{endpoint} response must be a JSON object")
    return payload


def parse_aggregate_json(payload: Any) -> AggregateReading:
    """Parse gateway aggregate JSON; now is W and energy fields are Wh."""
    data = _object(payload, "aggregate")
    return AggregateReading(
        power_w=parse_optional_number(data.get("now"), "aggregate now"),
        today_wh=parse_optional_number(data.get("today"), "aggregate today"),
        total_wh=parse_optional_number(data.get("total"), "aggregate total"),
        status_code=_status(data.get("status"), "aggregate status"),
        raw=data,
    )


def parse_module_json(payload: Any, *, address: str, raw_id: str) -> ModuleReading:
    """Parse one logical module JSON response."""
    data = _object(payload, "module")
    status_code = _status(data.get("status"), "module status")
    if status_code == "8000":
        status = ModuleStatus.LOW_LIGHT
    elif status_code == "0000":
        status = ModuleStatus.OK
    elif status_code is None:
        status = ModuleStatus.UNKNOWN
    else:
        status = ModuleStatus.FAULT
    return ModuleReading(
        raw_id=raw_id,
        address=address,
        power_w=parse_optional_number(data.get("now"), "module now"),
        today_wh=parse_optional_number(data.get("today"), "module today"),
        total_wh=parse_optional_number(data.get("total"), "module total"),
        status_code=status_code,
        status=status,
        raw=data,
    )


def parse_min_dat(payload: str) -> list[MinDatRecord]:
    """Parse all complete rich telemetry records in a response tail."""
    if not isinstance(payload, str) or not payload.strip():
        raise NepInvalidResponse("min.dat is empty")
    records: list[MinDatRecord] = []
    for line in payload.splitlines():
        fields = line.split()
        if not fields or fields[0].startswith("#") or len(fields) != 12:
            continue
        try:
            status_code = _status(fields[11], "min.dat status") or ""
            low_light = status_code == "8000"
            temperature = float(fields[7])
            records.append(
                MinDatRecord(
                    timestamp=f"{fields[0]} {fields[1]}",
                    power_w=float(fields[2]) * 1000,
                    voltage_dc_v=None if low_light else float(fields[3]),
                    voltage_ac_v=None if low_light else float(fields[4]),
                    current_a=float(fields[5]),
                    frequency_hz=None if low_light else float(fields[6]),
                    temperature_c=None if temperature <= -50 else temperature,
                    energy_wh=float(fields[8]) * 1000,
                    rssi=float(fields[9]),
                    diagnostic_code=fields[10],
                    status_code=status_code,
                )
            )
        except (ValueError, NepInvalidResponse):
            continue
    if not records:
        raise NepInvalidResponse("min.dat contains no complete records")
    return records
