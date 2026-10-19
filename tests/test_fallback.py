"""Contracts for the inventory-independent read path."""

import json
from datetime import timedelta
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.nep_local.client import NepGatewayClient
from custom_components.nep_local.const import DOMAIN
from custom_components.nep_local.coordinator import NepDataUpdateCoordinator
from custom_components.nep_local.diagnostics import async_get_config_entry_diagnostics
from custom_components.nep_local.exceptions import NepResponseMissing
from custom_components.nep_local.models import AggregateReading, GatewayInventory
from custom_components.nep_local.parsers import parse_min_dat, parse_module_registry


@pytest.mark.parametrize(
    "tail,status,power,energy,temp",
    [
        ("0.165054 31.07 246.1 0.1 59.98 31 0.574 1 0 8000", "8000", 165.054, 574, 31),
        ("0.001382 40.19 245.7 0 60.04 30 0.001 0 8B05 0", "0000", 1.382, 1, 30),
        ("0 0 0 0 0 -100 0 1 0 8000", "8000", 0, 0, None),
    ],
)
def test_observed_live_columns(tail, status, power, energy, temp):
    record = parse_min_dat(f"2026-10-19 15:40 {tail}")[-1]
    assert record.status_code == status
    assert record.power_w == pytest.approx(power)
    assert record.energy_wh == pytest.approx(energy)
    assert record.temperature_c == temp
    if power > 10:
        assert record.voltage_dc_v == 31.07
        assert record.voltage_ac_v == 246.1
        assert record.frequency_hz == 59.98
        assert record.current_a == 0.1
    if status == "0000":
        assert record.diagnostic_code == "8B05"


def test_fractional_telemetry_index_is_not_a_status_flag():
    record = parse_min_dat(
        "2026-10-19 16:15 0.012219 42.34 245.7 0.04 60 29 0.109 0.347 8B05 0"
    )[-1]
    assert record.rssi == 0.347
    assert record.status_code == "0000"
    assert record.diagnostic_code == "8B05"


async def test_plc_slots_aggregate_and_silent_spares_end_to_end(hass):
    fixture = json.loads(
        (Path(__file__).parent / "fixtures/fallback_slots.json").read_text()
    )
    stamp = dt_util.now().strftime("%Y-%m-%d %H:%M")
    registry_json = json.dumps(
        {
            "data": {
                f"Inverter{index}": {"plcid": raw_id}
                for index, raw_id in enumerate(fixture["com_ids"], start=1)
            }
        }
    )
    requests = []
    stale_slots = set()

    async def get_text(self, path, **kwargs):
        requests.append(path)
        if path == "/module/":
            return "<html><div id='box'></div></html>"
        if path == "/module/module.php":
            return registry_json
        if path.startswith("/data/"):
            slot = path.split("/")[2]
            if slot in fixture["slots"]:
                timestamp = "2000-01-01 00:00" if slot in stale_slots else stamp
                return timestamp + " " + fixture["slots"][slot].split(maxsplit=2)[2]
        raise NepResponseMissing()

    entry = MockConfigEntry(
        domain=DOMAIN, unique_id="TESTGW", data={"host": "192.0.2.10"}, version=2
    )
    entry.add_to_hass(hass)
    with patch.object(NepGatewayClient, "_get_text", get_text):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        coordinator = entry.runtime_data.coordinator
        data = coordinator.data
        assert [
            (m.slot, m.raw_id)
            for m in (data.inventory.modules[0], data.inventory.modules[-1])
        ] == [(1, "0X326ED5E0"), (12, "0X326F2770")]
        assert len(data.inventory.modules) == 12
        assert "/data/12/min.dat" in requests
        assert data.aggregate.power_w == pytest.approx(30.255)
        assert data.aggregate.today_wh == 611
        assert data.modules["0X326ED5E0"].reading.power_w == 0
        assert data.modules["0X326ED5E1"].reading.power_w == pytest.approx(12.993)
        entities = {
            entity.unique_id: entity
            for entity in er.async_entries_for_config_entry(
                er.async_get(hass), entry.entry_id
            )
        }
        for raw_id in (
            "3268C170",
            "3268C171",
            "3265F760",
            "3265F761",
            "326F2771",
            "326F2770",
        ):
            assert (
                hass.states.get(entities[f"TESTGW_0X{raw_id}_power"].entity_id).state
                == "unavailable"
            )
        diagnostics = await async_get_config_entry_diagnostics(hass, entry)
        check = diagnostics["gateway"]["aggregate_check"]
        assert check["source"] == "min_dat_slot_0"
        assert check["reporting_channels"] == 6
        assert check["channel_power_w"] == pytest.approx(30.255)
        assert check["channel_today_wh"] == 611
        assert check["power_delta_w"] == pytest.approx(0)
        assert check["today_delta_wh"] == 0
        stale_slots.add("2")
        await coordinator.async_refresh()
        assert coordinator.data.aggregate.power_w == pytest.approx(30.255)
        assert coordinator.data.aggregate_check["channel_power_w"] is None
        assert await hass.config_entries.async_unload(entry.entry_id)


def test_registry_keeps_explicit_indices_and_inventory_identity_format():
    html = "<input id='plcid0' value='FFFF'><input id='plcid1' value='326ED5E0'><input id='plcid3' value='326EFF30'>"
    modules = parse_module_registry(html)
    assert [(m.slot, m.raw_id) for m in modules] == [
        (1, "0X326ED5E0"),
        (3, "0X326EFF30"),
    ]
    assert modules == parse_module_registry(
        {
            "data": {
                "Inverter1": {"plcid": "326ED5E0"},
                "Inverter3": {"plcid": "326EFF30"},
            }
        }
    )


async def test_scan_stops_after_consecutive_missing_not_isolated_gap():
    client = NepGatewayClient(None, "http://example.invalid")
    record = parse_min_dat("2026-10-19 15:40 0 0 0 0 0 -100 0 1 0 8000")[-1]
    client.min_dat = AsyncMock(
        side_effect=[
            record,
            NepResponseMissing(),
            record,
            NepResponseMissing(),
            NepResponseMissing(),
            NepResponseMissing(),
        ]
    )
    records = await client.scan_slots()
    assert set(records) == {1, 3}
    assert [call.args[0].slot for call in client.min_dat.call_args_list] == list(
        range(1, 7)
    )


async def test_scan_does_not_hide_registered_slot_behind_missing_gap():
    client = NepGatewayClient(None, "http://example.invalid")
    record = parse_min_dat("2026-10-19 15:40 0 0 0 0 0 -100 0 1 0 8000")[-1]
    client.min_dat = AsyncMock(
        side_effect=[NepResponseMissing()] * 6 + [record] + [NepResponseMissing()] * 3
    )
    records = await client.scan_slots({7})
    assert records[7] == record
    assert client.min_dat.await_count == 10


async def test_conflicting_registered_spellings_do_not_split_history(hass):
    entry = MockConfigEntry(domain=DOMAIN, unique_id="TESTGW", data={})
    entry.add_to_hass(hass)
    registry = er.async_get(hass)
    for raw_id in ("0X326ED5E0", "326ED5E0"):
        registry.async_get_or_create(
            "sensor", DOMAIN, f"TESTGW_{raw_id}_status", config_entry=entry
        )
    client = AsyncMock()
    client.inventory.return_value = GatewayInventory(
        "TESTGW", parse_module_registry("<input id='plcid1' value='326ED5E0'>")
    )
    coordinator = NepDataUpdateCoordinator(hass, entry, client)
    await coordinator.async_refresh()
    assert not coordinator.last_update_success
    assert "Conflicting registered COM-ID spellings" in str(coordinator.last_exception)
    client.scan_slots.assert_not_called()


async def test_fallback_totals_freshness_and_preferred_path_recovery(hass):
    modules = parse_module_registry(
        {
            "data": {
                "Inverter1": {"plcid": "326ED5E0"},
                "Inverter2": {"plcid": "326ED5E1"},
            }
        }
    )
    stamp = dt_util.now().replace(tzinfo=None)
    record = parse_min_dat(f"{stamp:%Y-%m-%d %H:%M} 0.1 31 245 0.1 60 30 0.5 0 8B05 0")[
        -1
    ]
    client = AsyncMock()
    client.inventory.side_effect = NepResponseMissing()
    client.fallback_inventory.return_value = GatewayInventory(
        "TESTGW", modules, fallback=True
    )
    client.scan_slots.return_value = {1: record, 2: record}
    client.min_dat.side_effect = NepResponseMissing()
    entry = MockConfigEntry(domain=DOMAIN, unique_id="TESTGW", data={})
    entry.add_to_hass(hass)
    coordinator = NepDataUpdateCoordinator(hass, entry, client)
    await coordinator.async_refresh()
    assert coordinator.data.aggregate.power_w == 200
    assert coordinator.data.aggregate.today_wh == 1000
    assert coordinator.data.aggregate.total_wh is None
    assert coordinator.data.modules[modules[0].raw_id].reading.total_wh is None
    client.aggregate.assert_not_called()
    stale = parse_min_dat(
        f"{stamp - timedelta(hours=1):%Y-%m-%d %H:%M} 0 0 0 0 0 -100 0 1 0 8000"
    )[-1]
    client.scan_slots.return_value = {1: record, 2: stale}
    await coordinator.async_refresh()
    assert coordinator.data.aggregate.power_w is None
    assert coordinator.data.modules[modules[1].raw_id].reading is None
    client.inventory.side_effect = None
    client.inventory.return_value = GatewayInventory("TESTGW", modules)
    client.aggregate.return_value = AggregateReading(power_w=300)
    await coordinator.async_refresh()
    assert not coordinator.data.inventory.fallback
    assert coordinator.data.aggregate.power_w == 300
    client.aggregate.assert_awaited_once()


@pytest.mark.parametrize(
    "com_id,seed_key", [("0X326ED5E0", "power"), ("326ED5E0", "status")]
)
async def test_fallback_restores_registered_entity_history_ids(hass, com_id, seed_key):
    stamp = dt_util.now().replace(tzinfo=None)
    telemetry = (
        f"{stamp:%Y-%m-%d %H:%M} 0.165054 31.07 246.1 0.1 59.98 31 0.574 1 0 8000"
    )

    async def get_text(self, path, **kwargs):
        if path == "/module/":
            return "<html><div id='box'></div></html>"
        if path == "/module/module.php":
            return json.dumps({"data": {"Inverter1": {"plcid": "326ED5E0"}}})
        if path == "/data/1/min.dat":
            return telemetry
        raise NepResponseMissing()

    entry = MockConfigEntry(
        domain=DOMAIN, unique_id="TESTGW", data={"host": "192.0.2.10"}, version=2
    )
    entry.add_to_hass(hass)
    registry = er.async_get(hass)
    retained = registry.async_get_or_create(
        "sensor",
        DOMAIN,
        f"TESTGW_{com_id}_{seed_key}",
        config_entry=entry,
        suggested_object_id="original_power",
    )
    with patch.object(NepGatewayClient, "_get_text", get_text):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        assert (
            registry.async_get(retained.entity_id).unique_id
            == f"TESTGW_{com_id}_{seed_key}"
        )
        entities = {
            entity.unique_id: entity
            for entity in er.async_entries_for_config_entry(registry, entry.entry_id)
        }
        assert f"TESTGW_{com_id}_today_energy" in entities
        assert f"TESTGW_{com_id}_lifetime_energy" in entities
        assert float(
            hass.states.get(entities[f"TESTGW_{com_id}_power"].entity_id).state
        ) == pytest.approx(165.054)
        assert (
            hass.states.get(
                entities[f"TESTGW_{com_id}_lifetime_energy"].entity_id
            ).state
            == "unknown"
        )
        assert (
            hass.states.get(entities[f"TESTGW_{com_id}_status"].entity_id).state
            == "low_light"
        )
        assert await hass.config_entries.async_unload(entry.entry_id)
