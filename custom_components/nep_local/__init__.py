"""NEP Local integration."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .client import NepGatewayClient
from .const import CONF_HOST, DOMAIN
from .coordinator import NepDataUpdateCoordinator
from .models import InventoryModule

PLATFORMS = [Platform.SENSOR]
OBSOLETE_CHANNEL_SENSOR_KEYS = {"ac_voltage", "frequency", "temperature"}


@dataclass
class NepRuntimeData:
    """Runtime data stored on the config entry."""

    client: NepGatewayClient
    coordinator: NepDataUpdateCoordinator


NepConfigEntry = ConfigEntry[NepRuntimeData]


def gateway_url(host: str) -> str:
    """Normalize a configured host into a local HTTP base URL."""
    value = host.strip().rstrip("/")
    return value if value.startswith(("http://", "https://")) else f"http://{value}"


async def async_setup_entry(hass: HomeAssistant, entry: NepConfigEntry) -> bool:
    """Set up NEP Local from a config entry."""
    client = NepGatewayClient(
        async_get_clientsession(hass), gateway_url(entry.data[CONF_HOST])
    )
    coordinator = NepDataUpdateCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = NepRuntimeData(client=client, coordinator=coordinator)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Merge per-channel shared measurements into physical inverter entities."""
    if entry.version > 2:
        return False
    if entry.version == 1:
        registry = er.async_get(hass)
        canonical_entries = {}
        serial_prefix = f"{entry.unique_id}_"
        for entity in er.async_entries_for_config_entry(registry, entry.entry_id):
            if entity.platform != DOMAIN or not entity.unique_id.startswith(
                serial_prefix
            ):
                continue
            for key in OBSOLETE_CHANNEL_SENSOR_KEYS:
                suffix = f"_{key}"
                if not entity.unique_id.endswith(suffix):
                    continue
                raw_id = entity.unique_id[len(serial_prefix) : -len(suffix)]
                inverter_id = InventoryModule(address="", raw_id=raw_id).inverter_id
                canonical_unique_id = f"{serial_prefix}{inverter_id}{suffix}"
                canonical_entries.setdefault(canonical_unique_id, []).append(entity)
                break

        for canonical_unique_id, entities in canonical_entries.items():
            keeper = next(
                (
                    entity
                    for entity in entities
                    if entity.unique_id == canonical_unique_id
                ),
                entities[0],
            )
            if keeper.unique_id != canonical_unique_id:
                registry.async_update_entity(
                    keeper.entity_id, new_unique_id=canonical_unique_id
                )
            for duplicate in entities:
                if duplicate.entity_id != keeper.entity_id:
                    registry.async_remove(duplicate.entity_id)

        hass.config_entries.async_update_entry(
            entry,
            data={**entry.data, CONF_HOST: gateway_url(entry.data[CONF_HOST])},
            version=2,
        )
    return True


async def async_unload_entry(hass: HomeAssistant, entry: NepConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
