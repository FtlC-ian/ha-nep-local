from pathlib import Path

import pytest

from nep_local.exceptions import NepInvalidResponse
from nep_local.models import ModuleStatus
from nep_local.parsers import parse_aggregate_json, parse_inventory_page, parse_min_dat, parse_module_json

FIXTURES = Path(__file__).parent / "fixtures"


def test_inventory_supports_dynamic_addresses_and_stable_raw_ids() -> None:
    modules = parse_inventory_page((FIXTURES / "inventory.html").read_text())
    assert [(module.raw_id, module.address) for module in modules] == [
        ("fixture-module-alpha", "12"),
        ("fixture-module-beta", "27"),
    ]


def test_genuine_zero_is_not_missing() -> None:
    import json
    reading = parse_aggregate_json(json.loads((FIXTURES / "aggregate.json").read_text()))
    assert reading.power_w == 0.0
    assert reading.energy_wh == 1234.5


def test_missing_value_is_none_not_zero() -> None:
    assert parse_aggregate_json({"Pac": ""}).power_w is None


def test_low_light_is_not_transport_failure() -> None:
    import json
    reading = parse_module_json(json.loads((FIXTURES / "module_low_light.json").read_text()), address="12", raw_id="fallback")
    assert reading.status is ModuleStatus.LOW_LIGHT
    assert reading.transport_healthy is True
    assert reading.power_w == 0.0


def test_malformed_inventory_and_numeric_values_raise() -> None:
    with pytest.raises(NepInvalidResponse):
        parse_inventory_page("<html>nothing here</html>")
    with pytest.raises(NepInvalidResponse):
        parse_aggregate_json({"Pac": "not a number"})


def test_min_dat_key_value_and_csv_records() -> None:
    records = parse_min_dat((FIXTURES / "min.dat").read_text())
    assert records[0].values["power"] == "0"
    assert records[1].values == {"0": "2026-01-01T12:05:00", "1": "0", "2": "8000"}
