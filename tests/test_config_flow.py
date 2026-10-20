"""Tests for the NEP Local config flow."""

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.nep_local.client import NepGatewayClient
from custom_components.nep_local.const import CONF_HOST, DOMAIN
from custom_components.nep_local.exceptions import NepResponseMissing


async def test_confirmed_manual_serial_allows_fallback_configuration(hass):
    async def get_text(self, path, **kwargs):
        if path == "/module/":
            return "<input id='plcid1' value='12340000'>"
        raise NepResponseMissing()

    with (
        patch.object(NepGatewayClient, "_get_text", get_text),
        patch(
            "custom_components.nep_local.async_setup_entry",
            AsyncMock(return_value=True),
        ),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_USER},
            data={
                CONF_HOST: "192.0.2.10",
                "serial": "21000000012345",
                "confirm_serial": True,
            },
        )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["result"].unique_id == "21000000012345"


@pytest.mark.parametrize(
    "serial,confirmed", [("typo", True), ("21000000012345", False)]
)
async def test_manual_serial_requires_format_and_explicit_confirmation(
    hass, serial, confirmed
):
    with patch(
        "custom_components.nep_local.config_flow._validate_host",
        AsyncMock(return_value=serial),
    ) as validate:
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_USER},
            data={
                CONF_HOST: "192.0.2.10",
                "serial": serial,
                "confirm_serial": confirmed,
            },
        )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "confirm_serial"}
    validate.assert_not_called()


async def test_user_flow_creates_entry_with_gateway_serial(hass) -> None:
    with (
        patch(
            "custom_components.nep_local.config_flow._validate_host",
            AsyncMock(return_value="TESTGW000001"),
        ),
        patch(
            "custom_components.nep_local.async_setup_entry",
            AsyncMock(return_value=True),
        ),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_USER},
            data={CONF_HOST: "192.0.2.10"},
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {CONF_HOST: "http://192.0.2.10"}
    assert result["result"].unique_id == "TESTGW000001"


async def test_reconfigure_rejects_a_different_gateway(hass) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "192.0.2.10"},
        unique_id="TESTGW000001",
    )
    entry.add_to_hass(hass)
    with patch(
        "custom_components.nep_local.config_flow._validate_host",
        AsyncMock(return_value="OTHERGW000001"),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={
                "source": config_entries.SOURCE_RECONFIGURE,
                "entry_id": entry.entry_id,
            },
            data={CONF_HOST: "192.0.2.11"},
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "wrong_gateway"}
