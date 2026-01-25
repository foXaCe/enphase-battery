"""Tests for Enphase Battery config flow."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.enphase_battery.config_flow import (
    CannotConnect,
    InvalidAuth,
)
from custom_components.enphase_battery.const import (
    CONF_CONNECTION_MODE,
    CONF_ENVOY_HOST,
    CONNECTION_MODE_CLOUD,
    CONNECTION_MODE_LOCAL,
    DOMAIN,
)


async def test_form_user_step(hass: HomeAssistant) -> None:
    """Test the initial user step shows mode selection."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result.get("errors") is None or result["errors"] == {}


async def test_form_local_mode_selection(
    hass: HomeAssistant,
    mock_setup_entry: AsyncMock,
) -> None:
    """Test selecting local mode redirects to local step."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_CONNECTION_MODE: CONNECTION_MODE_LOCAL},
    )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "local"


async def test_form_cloud_mode_selection(
    hass: HomeAssistant,
    mock_setup_entry: AsyncMock,
) -> None:
    """Test selecting cloud mode redirects to cloud step."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_CONNECTION_MODE: CONNECTION_MODE_CLOUD},
    )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "cloud"


async def test_form_local_success(
    hass: HomeAssistant,
    mock_setup_entry: AsyncMock,
) -> None:
    """Test successful local configuration."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_CONNECTION_MODE: CONNECTION_MODE_LOCAL},
    )

    with patch(
        "custom_components.enphase_battery.config_flow.validate_local_input",
        return_value={
            "title": "Enphase Battery Local (192.168.1.100)",
            "serial": "TEST123456",
            "firmware": "8.0.0",
        },
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_ENVOY_HOST: "192.168.1.100",
                "cloud_username": "test@example.com",
                "cloud_password": "testpassword",
                "enable_cloud_control": False,
            },
        )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["title"] == "Enphase Battery Local (192.168.1.100)"
    assert result["data"][CONF_CONNECTION_MODE] == CONNECTION_MODE_LOCAL
    assert result["data"][CONF_ENVOY_HOST] == "192.168.1.100"


async def test_form_local_cannot_connect(
    hass: HomeAssistant,
    mock_setup_entry: AsyncMock,
) -> None:
    """Test handling connection error in local mode."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_CONNECTION_MODE: CONNECTION_MODE_LOCAL},
    )

    with patch(
        "custom_components.enphase_battery.config_flow.validate_local_input",
        side_effect=CannotConnect,
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_ENVOY_HOST: "192.168.1.100",
                "cloud_username": "test@example.com",
                "cloud_password": "testpassword",
                "enable_cloud_control": False,
            },
        )

    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_form_local_invalid_auth(
    hass: HomeAssistant,
    mock_setup_entry: AsyncMock,
) -> None:
    """Test handling invalid auth in local mode."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_CONNECTION_MODE: CONNECTION_MODE_LOCAL},
    )

    with patch(
        "custom_components.enphase_battery.config_flow.validate_local_input",
        side_effect=InvalidAuth,
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_ENVOY_HOST: "192.168.1.100",
                "cloud_username": "test@example.com",
                "cloud_password": "wrongpassword",
                "enable_cloud_control": False,
            },
        )

    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}


async def test_form_cloud_success(
    hass: HomeAssistant,
    mock_setup_entry: AsyncMock,
) -> None:
    """Test successful cloud configuration."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_CONNECTION_MODE: CONNECTION_MODE_CLOUD},
    )

    with patch(
        "custom_components.enphase_battery.config_flow.validate_cloud_input",
        return_value={
            "title": "Enphase Battery Cloud (test@example.com)",
            "serial": "CLOUD123456",
        },
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_USERNAME: "test@example.com",
                CONF_PASSWORD: "testpassword",
            },
        )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["title"] == "Enphase Battery Cloud (test@example.com)"
    assert result["data"][CONF_CONNECTION_MODE] == CONNECTION_MODE_CLOUD


async def test_form_already_configured(
    hass: HomeAssistant,
    mock_setup_entry: AsyncMock,
) -> None:
    """Test handling already configured device."""
    # Create an existing entry using MockConfigEntry
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Existing Entry",
        data={CONF_CONNECTION_MODE: CONNECTION_MODE_LOCAL},
        unique_id="TEST123456",
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_CONNECTION_MODE: CONNECTION_MODE_LOCAL},
    )

    with patch(
        "custom_components.enphase_battery.config_flow.validate_local_input",
        return_value={
            "title": "Enphase Battery Local (192.168.1.100)",
            "serial": "TEST123456",
            "firmware": "8.0.0",
        },
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_ENVOY_HOST: "192.168.1.100",
                "cloud_username": "test@example.com",
                "cloud_password": "testpassword",
                "enable_cloud_control": False,
            },
        )

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "already_configured"
