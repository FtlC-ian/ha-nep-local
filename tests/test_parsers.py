import json
from datetime import datetime
from pathlib import Path

import pytest

from custom_components.nep_local.exceptions import NepInvalidResponse
from custom_components.nep_local.models import ModuleStatus
from custom_components.nep_local.parsers import (
    parse_aggregate_json,
    parse_inventory_page,
    parse_min_dat,
    parse_module_json,
)

FIXTURES = Path(__file__).parent / "fixtures"


def test_inventory_reads_gateway_box_addr_and_raw_m_id() -> None:
    inventory = parse_inventory_page((FIXTURES / "inventory.html").read_text())
    assert inventory.serial == "TESTGW000001"
    assert [module.address for module in inventory.modules] == [
        "1",
        "2",
        "3",
        "4",
        "9",
        "10",
    ]
    assert inventory.modules[0].raw_id == "0XAAA00010"
    assert inventory.physical_inverter_id(
        inventory.modules[0]
    ) == inventory.physical_inverter_id(inventory.modules[1])


def test_inventory_does_not_drop_zero_production_or_historical_addresses() -> None:
    boxes = "".join(
        f'<div class="box" addr="{address}" title="M_ID:0X{address:08X}"></div>'
        for address in range(1, 13)
    )
    inventory = parse_inventory_page(
        f"<table><tr><td>Gateway</td><td>TESTGW000001</td></tr></table>{boxes}"
    )
    assert len(inventory.modules) == 12


def test_physical_device_id_is_stable_before_and_after_mate_discovery() -> None:
    first = parse_inventory_page(
        "<table><tr><td>Gateway</td><td>TESTGW000001</td></tr></table>"
        '<div class="box" addr="9" title="M_ID:0XAAA00051"></div>'
    )
    with_mate = parse_inventory_page(
        "<table><tr><td>Gateway</td><td>TESTGW000001</td></tr></table>"
        '<div class="box" addr="9" title="M_ID:0XAAA00051"></div>'
        '<div class="box" addr="10" title="M_ID:0XAAA00050"></div>'
    )
    assert first.physical_inverter_id(first.modules[0]) == "0XAAA00050"
    assert {with_mate.physical_inverter_id(module) for module in with_mate.modules} == {
        "0XAAA00050"
    }


def test_realdata_units_are_w_and_wh_and_zero_is_not_missing() -> None:
    reading = parse_aggregate_json(
        json.loads((FIXTURES / "aggregate.json").read_text())
    )
    assert (
        reading.power_w,
        reading.today_wh,
        reading.total_wh,
        reading.status_code,
    ) == (0.0, 0.0, 123456.0, "0000")
    assert parse_aggregate_json({"now": ""}).power_w is None


def test_status_8000_is_low_light_not_transport_failure() -> None:
    reading = parse_module_json(
        json.loads((FIXTURES / "module_low_light.json").read_text()),
        address="9",
        raw_id="REDACTED_MODULE_A",
    )
    assert reading.status is ModuleStatus.LOW_LIGHT
    assert reading.status_code == "8000"
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
    assert records[-1].timestamp == datetime(2026, 7, 20, 12, 5)
    assert records[-1].status_code == "8000"
    # Historical/inactive modules retain their original data; only the invalid
    # temperature sentinel becomes missing.
    assert records[-1].diagnostic_code == "0"
    assert records[-1].temperature_c is None
    assert records[-1].power_w == 0.0
    assert records[-1].energy_wh == 0.0
    assert records[-1].voltage_dc_v is None
    assert records[-1].voltage_ac_v is None
    assert records[-1].frequency_hz is None


def test_min_dat_skips_malformed_complete_record_before_current_sample() -> None:
    records = parse_min_dat(
        "2026-07-20 12:00:00 0.1 37 230 0.4 60 40 1 -70 FW BAD-STATUS\n"
        "2026-07-20 12:05:00 0.2 38 231 0.5 60 41 2 -71 FW 0000\n"
    )
    assert len(records) == 1
    assert records[-1].timestamp == datetime(2026, 7, 20, 12, 5)


def test_inventory_skips_one_bad_module_when_valid_modules_remain(caplog) -> None:
    inventory = parse_inventory_page(
        "<table><tr><td>Gateway</td><td>TESTGW000001</td></tr></table>"
        '<div class="box" addr="nine" title="M_ID:0XAAA00050"></div>'
        '<div class="box" addr="9" title="M_ID:0XAAA00051"></div>'
    )

    assert [module.address for module in inventory.modules] == ["9"]
    assert "Skipped 1 module inventory box" in caplog.text


def test_malformed_responses_raise_instead_of_using_fabricated_shapes() -> None:
    with pytest.raises(NepInvalidResponse):
        parse_inventory_page("<table><tr><td>not a gateway box</td></tr></table>")
    with pytest.raises(NepInvalidResponse):
        parse_aggregate_json({"now": "not a number"})
    with pytest.raises(NepInvalidResponse):
        parse_min_dat("2026-07-20 12:00:00 missing fields")
    with pytest.raises(NepInvalidResponse):
        parse_module_json({"status": "not-hex"}, address="9", raw_id="id")
    with pytest.raises(NepInvalidResponse):
        parse_inventory_page(
            "<table><tr><td>Gateway</td><td>TESTGW000001</td></tr></table>"
            '<div class="box" addr="nine" title="M_ID:0XAAA00050"></div>'
        )
    with pytest.raises(NepInvalidResponse):
        parse_aggregate_json({"now": "nan"})
    with pytest.raises(NepInvalidResponse):
        parse_min_dat("2026-07-20 12:00:00 nan 37 230 0.4 60 40 1 -70 0 0000")
