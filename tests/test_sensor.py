"""Tests for NEP Local sensor metadata and platform behavior."""

import json
from unittest.mock import AsyncMock, patch

from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import UnitOfEnergy, UnitOfPower
from homeassistant.helpers import device_registry as dr, entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.nep_local.client import NepGatewayClient
from custom_components.nep_local.const import CONF_HOST, DOMAIN
from custom_components.nep_local.diagnostics import async_get_config_entry_diagnostics
from custom_components.nep_local.models import (
    AggregateReading,
    GatewayInventory,
    InventoryModule,
    MinDatRecord,
    ModuleReading,
    ModuleStatus,
)
from custom_components.nep_local.sensor import GATEWAY_SENSORS, MODULE_SENSORS


def test_energy_and_power_metadata_are_home_assistant_native() -> None:
    gateway = {description.key: description for description in GATEWAY_SENSORS}
    modules = {description.key: description for description in MODULE_SENSORS}

    assert gateway["power"].device_class is SensorDeviceClass.POWER
    assert gateway["power"].native_unit_of_measurement == UnitOfPower.WATT
    assert gateway["power"].state_class is SensorStateClass.MEASUREMENT
    assert gateway["today_energy"].native_unit_of_measurement == UnitOfEnergy.WATT_HOUR
    assert gateway["today_energy"].state_class is SensorStateClass.TOTAL_INCREASING
    assert gateway["lifetime_energy"].state_class is SensorStateClass.TOTAL
    assert modules["status"].device_class is SensorDeviceClass.ENUM
    assert isinstance(modules["status"].options, list)
    assert "low_light" in modules["status"].options


def _module_reading(module: InventoryModule) -> ModuleReading:
    return ModuleReading(
        raw_id=module.raw_id,
        address=module.address,
        power_w=0,
        today_wh=0,
        total_wh=12345,
        status_code="8000",
        status=ModuleStatus.LOW_LIGHT,
    )


def _low_light_telemetry() -> MinDatRecord:
    return MinDatRecord(
        timestamp="2026-07-20 21:00",
        power_w=0,
        voltage_dc_v=None,
        voltage_ac_v=None,
        current_a=0,
        frequency_hz=None,
        temperature_c=None,
        energy_wh=12345,
        rssi=1,
        diagnostic_code="0",
        status_code="8000",
    )


def _entity_by_unique_id(hass, unique_id: str):
    return next(
        entry
        for entry in er.async_get(hass).entities.values()
        if entry.unique_id == unique_id
    )


async def test_setup_dynamic_discovery_availability_diagnostics_and_unload(
    hass,
) -> None:
    first = InventoryModule(address="9", raw_id="0XAAA00051")
    mate = InventoryModule(address="10", raw_id="0XAAA00050")
    inventory = GatewayInventory("TESTGW000001", (first,))

    async def module_read(module: InventoryModule):
        return _module_reading(module)

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "192.0.2.10"},
        unique_id="TESTGW000001",
    )
    entry.add_to_hass(hass)
    with (
        patch.object(
            NepGatewayClient, "inventory", AsyncMock(return_value=inventory)
        ) as inventory_mock,
        patch.object(
            NepGatewayClient,
            "aggregate",
            AsyncMock(
                return_value=AggregateReading(power_w=0, today_wh=0, total_wh=50000)
            ),
        ),
        patch.object(
            NepGatewayClient, "module", side_effect=module_read
        ) as module_mock,
        patch.object(
            NepGatewayClient,
            "min_dat",
            AsyncMock(return_value=_low_light_telemetry()),
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        power = _entity_by_unique_id(hass, "TESTGW000001_0XAAA00051_power")
        dc_voltage = _entity_by_unique_id(hass, "TESTGW000001_0XAAA00051_dc_voltage")
        status = _entity_by_unique_id(hass, "TESTGW000001_0XAAA00051_status")
        assert float(hass.states.get(power.entity_id).state) == 0
        assert hass.states.get(dc_voltage.entity_id).state == "unknown"
        assert hass.states.get(status.entity_id).state == "low_light"

        inverter_identifier = (DOMAIN, "TESTGW000001_0XAAA00050")
        inverter = dr.async_get(hass).async_get_device(
            identifiers={inverter_identifier}
        )
        assert inverter is not None
        assert power.device_id == inverter.id

        inventory_mock.return_value = GatewayInventory("TESTGW000001", (first, mate))
        await entry.runtime_data.coordinator.async_refresh()
        await hass.async_block_till_done()
        mate_power = _entity_by_unique_id(hass, "TESTGW000001_0XAAA00050_power")
        assert mate_power.device_id == inverter.id
        assert (
            len(
                [
                    device
                    for device in dr.async_get(hass).devices.values()
                    if inverter_identifier in device.identifiers
                ]
            )
            == 1
        )

        module_mock.side_effect = Exception("endpoint failed")
        await entry.runtime_data.coordinator.async_refresh()
        await hass.async_block_till_done()
        assert hass.states.get(power.entity_id).state == "unavailable"
        assert hass.states.get(dc_voltage.entity_id).state == "unknown"

        diagnostics = await async_get_config_entry_diagnostics(hass, entry)
        serialized = json.dumps(diagnostics)
        assert "192.0.2.10" not in serialized
        assert "TESTGW000001" not in serialized
        assert "0XAAA00051" not in serialized

        assert await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()
        assert entry.state is ConfigEntryState.NOT_LOADED

        module_mock.side_effect = module_read
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        assert entry.state is ConfigEntryState.LOADED
        assert hass.states.get(power.entity_id).state == "0"
