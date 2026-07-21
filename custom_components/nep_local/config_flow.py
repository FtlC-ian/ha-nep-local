"""Config flow for NEP Local."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from . import gateway_url
from .client import NepGatewayClient
from .const import CONF_HOST, DOMAIN
from .exceptions import NepConnectionError, NepError, NepInvalidResponse


async def _validate_host(hass: HomeAssistant, host: str) -> str:
    client = NepGatewayClient(async_get_clientsession(hass), gateway_url(host))
    inventory = await client.inventory()
    return inventory.serial


class NepLocalConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle NEP Local configuration."""

    VERSION = 2

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Configure a gateway by host or IP address."""
        errors: dict[str, str] = {}
        if user_input is not None:
            host = gateway_url(user_input[CONF_HOST])
            try:
                serial = await _validate_host(self.hass, host)
            except NepConnectionError:
                errors["base"] = "cannot_connect"
            except (NepInvalidResponse, NepError):
                errors["base"] = "invalid_response"
            else:
                await self.async_set_unique_id(serial)
                self._abort_if_unique_id_configured(updates={CONF_HOST: host})
                return self.async_create_entry(
                    title=f"NEP Gateway {serial}", data={CONF_HOST: host}
                )
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required(CONF_HOST): str}),
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Update the host while preserving the gateway identity."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            host = gateway_url(user_input[CONF_HOST])
            try:
                serial = await _validate_host(self.hass, host)
            except NepConnectionError:
                errors["base"] = "cannot_connect"
            except (NepInvalidResponse, NepError):
                errors["base"] = "invalid_response"
            else:
                if serial != entry.unique_id:
                    errors["base"] = "wrong_gateway"
                else:
                    return self.async_update_reload_and_abort(
                        entry, data_updates={CONF_HOST: host}
                    )
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema(
                {vol.Required(CONF_HOST, default=entry.data[CONF_HOST]): str}
            ),
            errors=errors,
        )
