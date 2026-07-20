"""NEP Local integration."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .client import NepGatewayClient
from .const import CONF_HOST
from .coordinator import NepDataUpdateCoordinator

PLATFORMS = [Platform.SENSOR]


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


async def async_unload_entry(hass: HomeAssistant, entry: NepConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
