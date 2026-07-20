"""Defensive parsers for the NEP gateway's observed local response shapes."""

from __future__ import annotations

import re
from html.parser import HTMLParser
from typing import Any

from .exceptions import NepInvalidResponse
from .models import AggregateReading, InventoryModule, MinDatRecord, ModuleReading, ModuleStatus

_MODULE_ID_RE = re.compile(r"(?:^|\s)M_ID\s*:\s*([^\s]+)", re.I)
_STATUS_RE = re.compile(r"^[0-9a-fA-F]+$")


def _number(value: Any, field: str) -> float | None:
    if value in (None, "", "--", "N/A", "null"):
        return None
    if isinstance(value, bool):
        raise NepInvalidResponse(f"{field} must be numeric")
    try:
        return float(str(value).strip().replace(",", ""))
    except (TypeError, ValueError) as error:
        raise NepInvalidResponse(f"{field} must be numeric") from error


def _status(value: Any, field: str) -> str | None:
    if value in (None, "", "--", "N/A", "null"):
        return None
    if isinstance(value, bool):
        raise NepInvalidResponse(f"{field} must be a hexadecimal status string")
    status = str(value).strip()
    if not _STATUS_RE.fullmatch(status):
        raise NepInvalidResponse(f"{field} must be a hexadecimal status string")
    return status.upper().zfill(4)


class _InventoryBoxParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.boxes: list[dict[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "div":
            return
        values = {key.lower(): value or "" for key, value in attrs}
        if "box" in values.get("class", "").lower().split():
            self.boxes.append(values)


def parse_inventory_page(payload: str) -> list[InventoryModule]:
    if not isinstance(payload, str) or not payload.strip():
        raise NepInvalidResponse("inventory page is empty")
    parser = _InventoryBoxParser()
    parser.feed(payload)
    found: dict[str, InventoryModule] = {}
    for attrs in parser.boxes:
        address = attrs.get("addr", "").strip()
        raw_id_match = _MODULE_ID_RE.search(attrs.get("title", ""))
        if address and raw_id_match:
            raw_id = raw_id_match.group(1).strip()
            found[raw_id] = InventoryModule(address=address, raw_id=raw_id)
    if not found:
        raise NepInvalidResponse("no module inventory boxes found")
    return list(found.values())


def _object(payload: Any, endpoint: str) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise NepInvalidResponse(f"{endpoint} response must be a JSON object")
    return payload


def parse_aggregate_json(payload: Any) -> AggregateReading:
    data = _object(payload, "aggregate")
    return AggregateReading(
        power_w=_number(data.get("now"), "aggregate now"),
        today_wh=_number(data.get("today"), "aggregate today"),
        total_wh=_number(data.get("total"), "aggregate total"),
        status_code=_status(data.get("status"), "aggregate status"),
        raw=data,
    )


def parse_module_json(payload: Any, *, address: str, raw_id: str) -> ModuleReading:
    data = _object(payload, "module")
    status_code = _status(data.get("status"), "module status")
    status = (
        ModuleStatus.LOW_LIGHT if status_code == "8000" else
        ModuleStatus.OK if status_code == "0000" else
        ModuleStatus.FAULT if status_code is not None else ModuleStatus.UNKNOWN
    )
    return ModuleReading(
        raw_id=raw_id,
        address=address,
        power_w=_number(data.get("now"), "module now"),
        today_wh=_number(data.get("today"), "module today"),
        total_wh=_number(data.get("total"), "module total"),
        status_code=status_code,
        status=status,
        raw=data,
    )


def parse_min_dat(payload: str) -> list[MinDatRecord]:
    if not isinstance(payload, str) or not payload.strip():
        raise NepInvalidResponse("min.dat is empty")
    records: list[MinDatRecord] = []
    for line in payload.splitlines():
        fields = line.split()
        if not fields or fields[0].startswith("#"):
            continue
        if len(fields) != 12:
            continue
        try:
            records.append(MinDatRecord(
                timestamp=f"{fields[0]} {fields[1]}", power_w=float(fields[2]) * 1000,
                voltage_dc_v=float(fields[3]), voltage_ac_v=float(fields[4]),
                current_a=float(fields[5]), frequency_hz=float(fields[6]),
                temperature_c=float(fields[7]), energy_wh=float(fields[8]) * 1000,
                rssi=float(fields[9]), firmware=fields[10],
                status_code=_status(fields[11], "min.dat status") or "",
            ))
        except (ValueError, NepInvalidResponse):
            continue
    if not records:
        raise NepInvalidResponse("min.dat contains no complete records")
    return records
