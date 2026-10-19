"""Diagnostics support for NEP Local."""

from __future__ import annotations

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from . import NepConfigEntry

TO_REDACT = {"host", "serial", "raw_id", "inverter_id"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: NepConfigEntry
) -> dict:
    """Return sanitized state without raw gateway payloads or identifiers."""
    data = entry.runtime_data.coordinator.data
    return async_redact_data(
        {
            "config_entry": dict(entry.data),
            "gateway": {
                "serial": data.inventory.serial,
                "aggregate_available": data.aggregate is not None,
                "module_count": len(data.inventory.modules),
                "fallback": data.inventory.fallback,
                "slot_mapping": "inverter_n_is_plc_slot_n"
                if data.inventory.fallback
                else "inventory",
                "aggregate_check": data.aggregate_check,
            },
            "modules": [
                {
                    "raw_id": module.raw_id,
                    "inverter_id": data.inventory.physical_inverter_id(module),
                    "address": module.address,
                    "slot": module.slot,
                    "live_available": data.modules[module.raw_id].reading is not None,
                    "telemetry_available": data.modules[module.raw_id].telemetry
                    is not None,
                }
                for module in data.inventory.modules
            ],
        },
        TO_REDACT,
    )
