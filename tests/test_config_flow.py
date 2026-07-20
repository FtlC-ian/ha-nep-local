"""Tests for the NEP Local config flow."""

from unittest.mock import AsyncMock, patch

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.nep_local.const import CONF_HOST, DOMAIN


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
    assert result["data"] == {CONF_HOST: "192.0.2.10"}
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
