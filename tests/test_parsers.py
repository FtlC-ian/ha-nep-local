import json
from pathlib import Path

import pytest

from nep_local.exceptions import NepInvalidResponse
from nep_local.models import ModuleStatus
from nep_local.parsers import parse_aggregate_json, parse_inventory_page, parse_min_dat, parse_module_json

FIXTURES = Path(__file__).parent / "fixtures"


def test_inventory_reads_gateway_box_addr_and_raw_m_id() -> None:
    modules = parse_inventory_page((FIXTURES / "inventory.html").read_text())
    assert [(module.raw_id, module.address) for module in modules] == [
        (f"REDACTED_MODULE_{address:02d}", str(address)) for address in range(1, 13)
    ]


def test_realdata_units_are_w_and_wh_and_zero_is_not_missing() -> None:
    reading = parse_aggregate_json(json.loads((FIXTURES / "aggregate.json").read_text()))
    assert (reading.power_w, reading.today_wh, reading.total_wh, reading.status_code) == (0.0, 0.0, 123456.0, "0000")
    assert parse_aggregate_json({"now": ""}).power_w is None


def test_status_8000_is_low_light_not_transport_failure() -> None:
    reading = parse_module_json(json.loads((FIXTURES / "module_low_light.json").read_text()), address="9", raw_id="REDACTED_MODULE_A")
    assert reading.status is ModuleStatus.LOW_LIGHT
    assert reading.status_code == "8000"
    assert reading.transport_healthy is True
    assert reading.power_w == 0.0
    assert reading.total_wh == 12345.0


def test_min_dat_parses_complete_whitespace_records_and_normalizes_units() -> None:
    records = parse_min_dat((FIXTURES / "min.dat").read_text())
    assert len(records) == 2
    assert records[0].power_w == 123.0
    assert records[0].energy_wh == 12345.0
    assert records[0].voltage_dc_v == 37.5
    assert records[0].frequency_hz == 60.0
    # The final complete line is the most current sample.
    assert records[-1].timestamp == "2026-07-20 12:05:00"
    assert records[-1].status_code == "8000"
    # Historical/inactive modules retain their original data; only the invalid
    # temperature sentinel becomes missing.
    assert records[-1].firmware == "0"
    assert records[-1].temperature_c is None
    assert records[-1].power_w == 0.0
    assert records[-1].energy_wh == 0.0


def test_min_dat_skips_malformed_complete_record_before_current_sample() -> None:
    records = parse_min_dat(
        "2026-07-20 12:00:00 0.1 37 230 0.4 60 40 1 -70 FW BAD-STATUS\n"
        "2026-07-20 12:05:00 0.2 38 231 0.5 60 41 2 -71 FW 0000\n"
    )
    assert len(records) == 1
    assert records[-1].timestamp == "2026-07-20 12:05:00"


def test_malformed_responses_raise_instead_of_using_fabricated_shapes() -> None:
    with pytest.raises(NepInvalidResponse):
        parse_inventory_page("<table><tr><td>not a gateway box</td></tr></table>")
    with pytest.raises(NepInvalidResponse):
        parse_aggregate_json({"now": "not a number"})
    with pytest.raises(NepInvalidResponse):
        parse_min_dat("2026-07-20 12:00:00 missing fields")
    with pytest.raises(NepInvalidResponse):
        parse_module_json({"status": "not-hex"}, address="9", raw_id="id")
