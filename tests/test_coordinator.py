"""Tests for coordinated gateway updates."""

import logging
from unittest.mock import AsyncMock

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.nep_local.const import CONF_HOST, DOMAIN
from custom_components.nep_local.coordinator import NepDataUpdateCoordinator
from custom_components.nep_local.exceptions import NepResponseMissing
from custom_components.nep_local.models import (
    AggregateReading,
    GatewayInventory,
    InventoryModule,
    ModuleReading,
    ModuleStatus,
)


async def test_coordinator_keeps_partial_module_data(hass, caplog) -> None:
    module = InventoryModule(address="9", raw_id="0XAAA00050")
    client = AsyncMock()
    client.inventory.return_value = GatewayInventory("TESTGW000001", (module,))
    client.aggregate.return_value = AggregateReading(power_w=42)
    client.module.return_value = ModuleReading(
        raw_id=module.raw_id,
        address=module.address,
        power_w=42,
        status_code="8000",
        status=ModuleStatus.LOW_LIGHT,
    )
    client.min_dat.side_effect = NepResponseMissing("nighttime telemetry omitted")
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_HOST: "192.0.2.10"})
    entry.add_to_hass(hass)

    coordinator = NepDataUpdateCoordinator(hass, entry, client)
    with caplog.at_level(logging.DEBUG):
        await coordinator.async_refresh()

    assert coordinator.last_update_success
    assert coordinator.data.aggregate.power_w == 42
    assert (
        coordinator.data.modules[module.raw_id].reading.status is ModuleStatus.LOW_LIGHT
    )
    assert coordinator.data.modules[module.raw_id].telemetry is None
    assert "Module telemetry endpoint failed with NepResponseMissing" in caplog.text
    assert module.raw_id not in caplog.text
