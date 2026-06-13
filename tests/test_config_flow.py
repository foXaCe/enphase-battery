"""Tests for Enphase Battery config flow."""

from __future__ import annotations

from ipaddress import ip_address
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers.service_info.dhcp import DhcpServiceInfo
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.enphase_battery.api import (
    EnvoyAuthError,
    EnvoyConnectionError,
    EnvoyLocalApiError,
)
from custom_components.enphase_battery.config_flow import (
    CannotConnect,
    InvalidAuth,
    validate_cloud_input,
    validate_local_input,
)
from custom_components.enphase_battery.const import (
    CONF_CONNECTION_MODE,
    CONF_ENVOY_HOST,
    CONF_SITE_ID,
    CONF_USER_ID,
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


# ---------------------------------------------------------------------------
# Cloud flow error tests
# ---------------------------------------------------------------------------


async def test_form_cloud_cannot_connect(
    hass: HomeAssistant,
    mock_setup_entry: AsyncMock,
) -> None:
    """Test cloud flow with connection error."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_CONNECTION_MODE: CONNECTION_MODE_CLOUD},
    )

    with patch(
        "custom_components.enphase_battery.config_flow.validate_cloud_input",
        side_effect=CannotConnect,
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_USERNAME: "test@example.com",
                CONF_PASSWORD: "testpassword",
            },
        )

    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_form_cloud_invalid_auth(
    hass: HomeAssistant,
    mock_setup_entry: AsyncMock,
) -> None:
    """Test cloud flow with auth error."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_CONNECTION_MODE: CONNECTION_MODE_CLOUD},
    )

    with patch(
        "custom_components.enphase_battery.config_flow.validate_cloud_input",
        side_effect=InvalidAuth,
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_USERNAME: "test@example.com",
                CONF_PASSWORD: "wrongpassword",
            },
        )

    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}


async def test_form_cloud_unknown_error(
    hass: HomeAssistant,
    mock_setup_entry: AsyncMock,
) -> None:
    """Test cloud flow with unknown error."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_CONNECTION_MODE: CONNECTION_MODE_CLOUD},
    )

    with patch(
        "custom_components.enphase_battery.config_flow.validate_cloud_input",
        side_effect=RuntimeError("unexpected"),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_USERNAME: "test@example.com",
                CONF_PASSWORD: "testpassword",
            },
        )

    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"base": "unknown"}


async def test_form_local_unknown_error(
    hass: HomeAssistant,
    mock_setup_entry: AsyncMock,
) -> None:
    """Test local flow with unknown exception."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_CONNECTION_MODE: CONNECTION_MODE_LOCAL},
    )

    with patch(
        "custom_components.enphase_battery.config_flow.validate_local_input",
        side_effect=RuntimeError("something went wrong"),
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
    assert result["errors"] == {"base": "unknown"}


# ---------------------------------------------------------------------------
# Reauth flow tests
# ---------------------------------------------------------------------------


async def test_reauth_flow_local(
    hass: HomeAssistant,
    mock_setup_entry: AsyncMock,
) -> None:
    """Test re-authentication flow for local mode."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Enphase Battery Local",
        data={
            CONF_CONNECTION_MODE: CONNECTION_MODE_LOCAL,
            CONF_ENVOY_HOST: "192.168.1.100",
            "cloud_username": "test@example.com",
            "cloud_password": "oldpassword",
            "enable_cloud_control": False,
        },
        unique_id="LOCAL123",
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_REAUTH,
            "entry_id": entry.entry_id,
        },
        data=entry.data,
    )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"

    with patch(
        "custom_components.enphase_battery.config_flow.validate_local_input",
        return_value={
            "title": "Enphase Battery Local (192.168.1.100)",
            "serial": "LOCAL123",
            "firmware": "8.0.0",
        },
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_ENVOY_HOST: "192.168.1.100",
                "cloud_username": "test@example.com",
                "cloud_password": "newpassword",
                "enable_cloud_control": False,
            },
        )

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"


async def test_reauth_flow_cloud(
    hass: HomeAssistant,
    mock_setup_entry: AsyncMock,
) -> None:
    """Test re-authentication flow for cloud mode."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Enphase Battery Cloud",
        data={
            CONF_CONNECTION_MODE: CONNECTION_MODE_CLOUD,
            CONF_USERNAME: "test@example.com",
            CONF_PASSWORD: "oldpassword",
        },
        unique_id="CLOUD123",
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_REAUTH,
            "entry_id": entry.entry_id,
        },
        data=entry.data,
    )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"

    with patch(
        "custom_components.enphase_battery.config_flow.validate_cloud_input",
        return_value={
            "title": "Enphase Battery Cloud (test@example.com)",
            "serial": "CLOUD123",
        },
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_USERNAME: "test@example.com",
                CONF_PASSWORD: "newpassword",
            },
        )

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"


async def test_reauth_flow_cannot_connect(
    hass: HomeAssistant,
    mock_setup_entry: AsyncMock,
) -> None:
    """Test reauth flow with cannot connect error."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Enphase Battery Local",
        data={
            CONF_CONNECTION_MODE: CONNECTION_MODE_LOCAL,
            CONF_ENVOY_HOST: "192.168.1.100",
            "cloud_username": "test@example.com",
            "cloud_password": "oldpassword",
            "enable_cloud_control": False,
        },
        unique_id="LOCAL123",
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_REAUTH,
            "entry_id": entry.entry_id,
        },
        data=entry.data,
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


async def test_reauth_flow_invalid_auth(
    hass: HomeAssistant,
    mock_setup_entry: AsyncMock,
) -> None:
    """Test reauth flow with invalid auth error."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Enphase Battery Cloud",
        data={
            CONF_CONNECTION_MODE: CONNECTION_MODE_CLOUD,
            CONF_USERNAME: "test@example.com",
            CONF_PASSWORD: "oldpassword",
        },
        unique_id="CLOUD123",
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_REAUTH,
            "entry_id": entry.entry_id,
        },
        data=entry.data,
    )

    with patch(
        "custom_components.enphase_battery.config_flow.validate_cloud_input",
        side_effect=InvalidAuth,
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_USERNAME: "test@example.com",
                CONF_PASSWORD: "badpassword",
            },
        )

    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}


async def test_reauth_flow_unknown_error(
    hass: HomeAssistant,
    mock_setup_entry: AsyncMock,
) -> None:
    """Test reauth flow with unknown error."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Enphase Battery Cloud",
        data={
            CONF_CONNECTION_MODE: CONNECTION_MODE_CLOUD,
            CONF_USERNAME: "test@example.com",
            CONF_PASSWORD: "oldpassword",
        },
        unique_id="CLOUD123",
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_REAUTH,
            "entry_id": entry.entry_id,
        },
        data=entry.data,
    )

    with patch(
        "custom_components.enphase_battery.config_flow.validate_cloud_input",
        side_effect=RuntimeError("unexpected"),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_USERNAME: "test@example.com",
                CONF_PASSWORD: "testpassword",
            },
        )

    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"base": "unknown"}


# ---------------------------------------------------------------------------
# Options flow tests
# ---------------------------------------------------------------------------


async def test_options_flow_init(
    hass: HomeAssistant,
    mock_setup_entry: AsyncMock,
) -> None:
    """Test options flow shows mode selection."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Enphase Battery Local",
        data={
            CONF_CONNECTION_MODE: CONNECTION_MODE_LOCAL,
            CONF_ENVOY_HOST: "192.168.1.100",
            "cloud_username": "test@example.com",
            "cloud_password": "testpassword",
            "enable_cloud_control": False,
        },
        unique_id="OPT123",
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "init"


async def test_options_flow_local_success(
    hass: HomeAssistant,
    mock_setup_entry: AsyncMock,
) -> None:
    """Test options flow local mode success."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Enphase Battery Local",
        data={
            CONF_CONNECTION_MODE: CONNECTION_MODE_LOCAL,
            CONF_ENVOY_HOST: "192.168.1.100",
            "cloud_username": "test@example.com",
            "cloud_password": "testpassword",
            "enable_cloud_control": False,
        },
        unique_id="OPT_LOCAL",
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)

    # Select local mode
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {CONF_CONNECTION_MODE: CONNECTION_MODE_LOCAL},
    )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "local"

    with patch(
        "custom_components.enphase_battery.config_flow.validate_local_input",
        return_value={
            "title": "Enphase Battery Local (192.168.1.200)",
            "serial": "OPT_LOCAL",
            "firmware": "8.0.0",
        },
    ):
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            {
                CONF_ENVOY_HOST: "192.168.1.200",
                "cloud_username": "new@example.com",
                "cloud_password": "newpassword",
                "enable_cloud_control": True,
            },
        )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    # Verify entry data was updated
    assert entry.data[CONF_ENVOY_HOST] == "192.168.1.200"
    assert entry.data["cloud_username"] == "new@example.com"
    assert entry.data[CONF_CONNECTION_MODE] == CONNECTION_MODE_LOCAL


async def test_options_flow_local_cannot_connect(
    hass: HomeAssistant,
    mock_setup_entry: AsyncMock,
) -> None:
    """Test options flow local mode with cannot connect error."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Enphase Battery Local",
        data={
            CONF_CONNECTION_MODE: CONNECTION_MODE_LOCAL,
            CONF_ENVOY_HOST: "192.168.1.100",
            "cloud_username": "test@example.com",
            "cloud_password": "testpassword",
            "enable_cloud_control": False,
        },
        unique_id="OPT_LOCAL_ERR",
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {CONF_CONNECTION_MODE: CONNECTION_MODE_LOCAL},
    )

    with patch(
        "custom_components.enphase_battery.config_flow.validate_local_input",
        side_effect=CannotConnect,
    ):
        result = await hass.config_entries.options.async_configure(
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


async def test_options_flow_local_invalid_auth(
    hass: HomeAssistant,
    mock_setup_entry: AsyncMock,
) -> None:
    """Test options flow local mode with invalid auth error."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Enphase Battery Local",
        data={
            CONF_CONNECTION_MODE: CONNECTION_MODE_LOCAL,
            CONF_ENVOY_HOST: "192.168.1.100",
            "cloud_username": "test@example.com",
            "cloud_password": "testpassword",
            "enable_cloud_control": False,
        },
        unique_id="OPT_LOCAL_AUTH",
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {CONF_CONNECTION_MODE: CONNECTION_MODE_LOCAL},
    )

    with patch(
        "custom_components.enphase_battery.config_flow.validate_local_input",
        side_effect=InvalidAuth,
    ):
        result = await hass.config_entries.options.async_configure(
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


async def test_options_flow_local_unknown_error(
    hass: HomeAssistant,
    mock_setup_entry: AsyncMock,
) -> None:
    """Test options flow local mode with unknown error."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Enphase Battery Local",
        data={
            CONF_CONNECTION_MODE: CONNECTION_MODE_LOCAL,
            CONF_ENVOY_HOST: "192.168.1.100",
            "cloud_username": "test@example.com",
            "cloud_password": "testpassword",
            "enable_cloud_control": False,
        },
        unique_id="OPT_LOCAL_UNK",
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {CONF_CONNECTION_MODE: CONNECTION_MODE_LOCAL},
    )

    with patch(
        "custom_components.enphase_battery.config_flow.validate_local_input",
        side_effect=RuntimeError("unexpected"),
    ):
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            {
                CONF_ENVOY_HOST: "192.168.1.100",
                "cloud_username": "test@example.com",
                "cloud_password": "testpassword",
                "enable_cloud_control": False,
            },
        )

    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"base": "unknown"}


async def test_options_flow_cloud_success(
    hass: HomeAssistant,
    mock_setup_entry: AsyncMock,
) -> None:
    """Test options flow cloud mode success."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Enphase Battery Cloud",
        data={
            CONF_CONNECTION_MODE: CONNECTION_MODE_CLOUD,
            CONF_USERNAME: "test@example.com",
            CONF_PASSWORD: "testpassword",
        },
        unique_id="OPT_CLOUD",
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)

    # Select cloud mode
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {CONF_CONNECTION_MODE: CONNECTION_MODE_CLOUD},
    )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "cloud"

    with patch(
        "custom_components.enphase_battery.config_flow.validate_cloud_input",
        return_value={
            "title": "Enphase Battery Cloud (new@example.com)",
            "serial": "OPT_CLOUD",
        },
    ):
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            {
                CONF_USERNAME: "new@example.com",
                CONF_PASSWORD: "newpassword",
            },
        )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    # Verify entry data was updated
    assert entry.data[CONF_USERNAME] == "new@example.com"
    assert entry.data[CONF_CONNECTION_MODE] == CONNECTION_MODE_CLOUD


async def test_options_flow_cloud_cannot_connect(
    hass: HomeAssistant,
    mock_setup_entry: AsyncMock,
) -> None:
    """Test options flow cloud mode with cannot connect error."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Enphase Battery Cloud",
        data={
            CONF_CONNECTION_MODE: CONNECTION_MODE_CLOUD,
            CONF_USERNAME: "test@example.com",
            CONF_PASSWORD: "testpassword",
        },
        unique_id="OPT_CLOUD_ERR",
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {CONF_CONNECTION_MODE: CONNECTION_MODE_CLOUD},
    )

    with patch(
        "custom_components.enphase_battery.config_flow.validate_cloud_input",
        side_effect=CannotConnect,
    ):
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            {
                CONF_USERNAME: "test@example.com",
                CONF_PASSWORD: "testpassword",
            },
        )

    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_options_flow_cloud_invalid_auth(
    hass: HomeAssistant,
    mock_setup_entry: AsyncMock,
) -> None:
    """Test options flow cloud mode with invalid auth error."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Enphase Battery Cloud",
        data={
            CONF_CONNECTION_MODE: CONNECTION_MODE_CLOUD,
            CONF_USERNAME: "test@example.com",
            CONF_PASSWORD: "testpassword",
        },
        unique_id="OPT_CLOUD_AUTH",
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {CONF_CONNECTION_MODE: CONNECTION_MODE_CLOUD},
    )

    with patch(
        "custom_components.enphase_battery.config_flow.validate_cloud_input",
        side_effect=InvalidAuth,
    ):
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            {
                CONF_USERNAME: "test@example.com",
                CONF_PASSWORD: "badpassword",
            },
        )

    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}


async def test_options_flow_cloud_unknown_error(
    hass: HomeAssistant,
    mock_setup_entry: AsyncMock,
) -> None:
    """Test options flow cloud mode with unknown error."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Enphase Battery Cloud",
        data={
            CONF_CONNECTION_MODE: CONNECTION_MODE_CLOUD,
            CONF_USERNAME: "test@example.com",
            CONF_PASSWORD: "testpassword",
        },
        unique_id="OPT_CLOUD_UNK",
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {CONF_CONNECTION_MODE: CONNECTION_MODE_CLOUD},
    )

    with patch(
        "custom_components.enphase_battery.config_flow.validate_cloud_input",
        side_effect=RuntimeError("unexpected"),
    ):
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            {
                CONF_USERNAME: "test@example.com",
                CONF_PASSWORD: "testpassword",
            },
        )

    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"base": "unknown"}


# ---------------------------------------------------------------------------
# validate_local_input direct tests
# ---------------------------------------------------------------------------


async def test_validate_local_input_success(hass: HomeAssistant) -> None:
    """Test validate_local_input with successful connection."""
    data = {
        CONF_ENVOY_HOST: "192.168.1.100",
        "cloud_username": "test@example.com",
        "cloud_password": "testpassword",
    }

    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("aiohttp.ClientSession", return_value=mock_session),
        patch("custom_components.enphase_battery.config_flow.EnphaseEnvoyLocalAPI") as mock_api_cls,
    ):
        mock_api = MagicMock()
        mock_api.authenticate = AsyncMock()
        mock_api._get_info = AsyncMock(return_value={"device": {"sn": "TEST123"}})
        mock_api.serial_number = "TEST123"
        mock_api.firmware_version = "8.0.0"
        mock_api_cls.return_value = mock_api

        result = await validate_local_input(hass, data)

    assert result["title"] == "Enphase Battery Local (192.168.1.100)"
    assert result["serial"] == "TEST123"
    assert result["firmware"] == "8.0.0"


async def test_validate_local_input_auth_error(hass: HomeAssistant) -> None:
    """Test validate_local_input raises InvalidAuth on auth error."""
    data = {
        CONF_ENVOY_HOST: "192.168.1.100",
        "cloud_username": "test@example.com",
        "cloud_password": "wrongpassword",
    }

    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("aiohttp.ClientSession", return_value=mock_session),
        patch("custom_components.enphase_battery.config_flow.EnphaseEnvoyLocalAPI") as mock_api_cls,
    ):
        mock_api = MagicMock()
        mock_api.authenticate = AsyncMock(side_effect=EnvoyAuthError("bad credentials"))
        mock_api_cls.return_value = mock_api

        with pytest.raises(InvalidAuth):
            await validate_local_input(hass, data)


async def test_validate_local_input_connection_error(hass: HomeAssistant) -> None:
    """Test validate_local_input raises CannotConnect on connection error."""
    data = {
        CONF_ENVOY_HOST: "192.168.1.100",
        "cloud_username": "test@example.com",
        "cloud_password": "testpassword",
    }

    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("aiohttp.ClientSession", return_value=mock_session),
        patch("custom_components.enphase_battery.config_flow.EnphaseEnvoyLocalAPI") as mock_api_cls,
    ):
        mock_api = MagicMock()
        mock_api.authenticate = AsyncMock(side_effect=EnvoyConnectionError("host unreachable"))
        mock_api_cls.return_value = mock_api

        with pytest.raises(CannotConnect):
            await validate_local_input(hass, data)


async def test_validate_local_input_unexpected_error(hass: HomeAssistant) -> None:
    """Test validate_local_input raises CannotConnect on unexpected error."""
    data = {
        CONF_ENVOY_HOST: "192.168.1.100",
        "cloud_username": "test@example.com",
        "cloud_password": "testpassword",
    }

    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("aiohttp.ClientSession", return_value=mock_session),
        patch("custom_components.enphase_battery.config_flow.EnphaseEnvoyLocalAPI") as mock_api_cls,
    ):
        mock_api = MagicMock()
        mock_api.authenticate = AsyncMock(side_effect=ValueError("something unexpected"))
        mock_api_cls.return_value = mock_api

        with pytest.raises(CannotConnect):
            await validate_local_input(hass, data)


async def test_validate_local_input_serial_from_info(hass: HomeAssistant) -> None:
    """Test validate_local_input extracts serial from info response."""
    data = {
        CONF_ENVOY_HOST: "envoy.local",
        "cloud_username": "test@example.com",
        "cloud_password": "testpassword",
    }

    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("aiohttp.ClientSession", return_value=mock_session),
        patch("custom_components.enphase_battery.config_flow.EnphaseEnvoyLocalAPI") as mock_api_cls,
    ):
        mock_api = MagicMock()
        mock_api.authenticate = AsyncMock()
        # Serial only available via top-level "sn" key (not nested in device)
        mock_api._get_info = AsyncMock(return_value={"sn": "ENVOY999"})
        mock_api.serial_number = "ENVOY999"
        mock_api.firmware_version = "7.6.175"
        mock_api_cls.return_value = mock_api

        result = await validate_local_input(hass, data)

    assert result["serial"] == "ENVOY999"
    assert result["firmware"] == "7.6.175"


# ---------------------------------------------------------------------------
# validate_cloud_input test
# ---------------------------------------------------------------------------


async def test_validate_cloud_input(hass: HomeAssistant) -> None:
    """Test validate_cloud_input returns expected data."""
    data = {
        CONF_USERNAME: "cloud@example.com",
        CONF_PASSWORD: "cloudpassword",
    }

    mock_api = MagicMock()
    mock_api.authenticate = AsyncMock()
    mock_api._site_id = 12345
    mock_api._user_id = 67890

    with patch(
        "custom_components.enphase_battery.config_flow.EnphaseBatteryAPI",
        return_value=mock_api,
    ):
        result = await validate_cloud_input(hass, data)

    assert result["title"] == "Enphase Battery Cloud (cloud@example.com)"
    assert result["serial"] == "12345"
    assert result["site_id"] == 12345
    assert result["user_id"] == 67890
    mock_api.authenticate.assert_awaited_once()


# ---------------------------------------------------------------------------
# validate_cloud_input error tests
# ---------------------------------------------------------------------------


async def test_validate_cloud_input_auth_error(hass: HomeAssistant) -> None:
    """Test validate_cloud_input raises InvalidAuth on auth error."""
    from custom_components.enphase_battery.api import EnphaseBatteryAuthError

    data = {
        CONF_USERNAME: "cloud@example.com",
        CONF_PASSWORD: "wrongpassword",
    }

    mock_api = MagicMock()
    mock_api.authenticate = AsyncMock(side_effect=EnphaseBatteryAuthError("bad credentials"))

    with (
        patch(
            "custom_components.enphase_battery.config_flow.EnphaseBatteryAPI",
            return_value=mock_api,
        ),
        pytest.raises(InvalidAuth),
    ):
        await validate_cloud_input(hass, data)


async def test_validate_cloud_input_api_error(hass: HomeAssistant) -> None:
    """Test validate_cloud_input raises CannotConnect on API error."""
    from custom_components.enphase_battery.api import EnphaseBatteryApiError

    data = {
        CONF_USERNAME: "cloud@example.com",
        CONF_PASSWORD: "testpassword",
    }

    mock_api = MagicMock()
    mock_api.authenticate = AsyncMock(side_effect=EnphaseBatteryApiError("server error"))

    with (
        patch(
            "custom_components.enphase_battery.config_flow.EnphaseBatteryAPI",
            return_value=mock_api,
        ),
        pytest.raises(CannotConnect),
    ):
        await validate_cloud_input(hass, data)


async def test_validate_cloud_input_unexpected_error(hass: HomeAssistant) -> None:
    """Test validate_cloud_input raises CannotConnect on unexpected error."""
    data = {
        CONF_USERNAME: "cloud@example.com",
        CONF_PASSWORD: "testpassword",
    }

    mock_api = MagicMock()
    mock_api.authenticate = AsyncMock(side_effect=ValueError("something unexpected"))

    with (
        patch(
            "custom_components.enphase_battery.config_flow.EnphaseBatteryAPI",
            return_value=mock_api,
        ),
        pytest.raises(CannotConnect),
    ):
        await validate_cloud_input(hass, data)


# ---------------------------------------------------------------------------
# Cloud flow with auto-detected IDs
# ---------------------------------------------------------------------------


async def test_form_cloud_success_with_auto_detected_ids(
    hass: HomeAssistant,
    mock_setup_entry: AsyncMock,
) -> None:
    """Test cloud flow saves auto-detected site_id and user_id."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_CONNECTION_MODE: CONNECTION_MODE_CLOUD},
    )

    with patch(
        "custom_components.enphase_battery.config_flow.validate_cloud_input",
        return_value={
            "title": "Enphase Battery Cloud (test@example.com)",
            "serial": "CLOUD_AUTO",
            "site_id": 99999,
            "user_id": 88888,
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
    assert result["data"][CONF_SITE_ID] == "99999"
    assert result["data"][CONF_USER_ID] == "88888"


# ---------------------------------------------------------------------------
# Reconfigure flow tests
# ---------------------------------------------------------------------------


async def test_reconfigure_flow_shows_form(
    hass: HomeAssistant,
    mock_setup_entry: AsyncMock,
) -> None:
    """Test reconfigure flow shows mode selection form."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Enphase Battery Local",
        data={
            CONF_CONNECTION_MODE: CONNECTION_MODE_LOCAL,
            CONF_ENVOY_HOST: "192.168.1.100",
            "cloud_username": "test@example.com",
            "cloud_password": "testpassword",
            "enable_cloud_control": False,
        },
        unique_id="RECONFIG1",
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": "reconfigure",
            "entry_id": entry.entry_id,
        },
    )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "reconfigure"


async def test_reconfigure_flow_routes_to_local(
    hass: HomeAssistant,
    mock_setup_entry: AsyncMock,
) -> None:
    """Test reconfigure flow routes to local step."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Enphase Battery Local",
        data={
            CONF_CONNECTION_MODE: CONNECTION_MODE_LOCAL,
            CONF_ENVOY_HOST: "192.168.1.100",
            "cloud_username": "test@example.com",
            "cloud_password": "testpassword",
            "enable_cloud_control": False,
        },
        unique_id="RECONFIG2",
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": "reconfigure",
            "entry_id": entry.entry_id,
        },
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_CONNECTION_MODE: CONNECTION_MODE_LOCAL},
    )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "reconfigure_local"


async def test_reconfigure_flow_routes_to_cloud(
    hass: HomeAssistant,
    mock_setup_entry: AsyncMock,
) -> None:
    """Test reconfigure flow routes to cloud step."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Enphase Battery Cloud",
        data={
            CONF_CONNECTION_MODE: CONNECTION_MODE_CLOUD,
            CONF_USERNAME: "test@example.com",
            CONF_PASSWORD: "testpassword",
        },
        unique_id="RECONFIG3",
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": "reconfigure",
            "entry_id": entry.entry_id,
        },
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_CONNECTION_MODE: CONNECTION_MODE_CLOUD},
    )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "reconfigure_cloud"


async def test_reconfigure_local_success(
    hass: HomeAssistant,
    mock_setup_entry: AsyncMock,
) -> None:
    """Test successful local reconfiguration."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Enphase Battery Local",
        data={
            CONF_CONNECTION_MODE: CONNECTION_MODE_LOCAL,
            CONF_ENVOY_HOST: "192.168.1.100",
            "cloud_username": "test@example.com",
            "cloud_password": "testpassword",
            "enable_cloud_control": False,
        },
        unique_id="RECONFIG_LOCAL",
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": "reconfigure",
            "entry_id": entry.entry_id,
        },
    )

    # Select local mode
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_CONNECTION_MODE: CONNECTION_MODE_LOCAL},
    )

    assert result["step_id"] == "reconfigure_local"

    with patch(
        "custom_components.enphase_battery.config_flow.validate_local_input",
        return_value={
            "title": "Enphase Battery Local (192.168.1.200)",
            "serial": "RECONFIG_LOCAL",
            "firmware": "8.0.0",
        },
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_ENVOY_HOST: "192.168.1.200",
                "cloud_username": "new@example.com",
                "cloud_password": "newpassword",
                "enable_cloud_control": True,
            },
        )

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    # Verify entry data was updated
    assert entry.data[CONF_ENVOY_HOST] == "192.168.1.200"
    assert entry.data["cloud_username"] == "new@example.com"
    assert entry.data[CONF_CONNECTION_MODE] == CONNECTION_MODE_LOCAL


async def test_reconfigure_local_cannot_connect(
    hass: HomeAssistant,
    mock_setup_entry: AsyncMock,
) -> None:
    """Test local reconfiguration with connection error."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Enphase Battery Local",
        data={
            CONF_CONNECTION_MODE: CONNECTION_MODE_LOCAL,
            CONF_ENVOY_HOST: "192.168.1.100",
            "cloud_username": "test@example.com",
            "cloud_password": "testpassword",
            "enable_cloud_control": False,
        },
        unique_id="RECONFIG_LOCAL_ERR",
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": "reconfigure",
            "entry_id": entry.entry_id,
        },
    )

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


async def test_reconfigure_local_invalid_auth(
    hass: HomeAssistant,
    mock_setup_entry: AsyncMock,
) -> None:
    """Test local reconfiguration with auth error."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Enphase Battery Local",
        data={
            CONF_CONNECTION_MODE: CONNECTION_MODE_LOCAL,
            CONF_ENVOY_HOST: "192.168.1.100",
            "cloud_username": "test@example.com",
            "cloud_password": "testpassword",
            "enable_cloud_control": False,
        },
        unique_id="RECONFIG_LOCAL_AUTH",
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": "reconfigure",
            "entry_id": entry.entry_id,
        },
    )

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


async def test_reconfigure_local_unknown_error(
    hass: HomeAssistant,
    mock_setup_entry: AsyncMock,
) -> None:
    """Test local reconfiguration with unknown error."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Enphase Battery Local",
        data={
            CONF_CONNECTION_MODE: CONNECTION_MODE_LOCAL,
            CONF_ENVOY_HOST: "192.168.1.100",
            "cloud_username": "test@example.com",
            "cloud_password": "testpassword",
            "enable_cloud_control": False,
        },
        unique_id="RECONFIG_LOCAL_UNK",
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": "reconfigure",
            "entry_id": entry.entry_id,
        },
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_CONNECTION_MODE: CONNECTION_MODE_LOCAL},
    )

    with patch(
        "custom_components.enphase_battery.config_flow.validate_local_input",
        side_effect=RuntimeError("unexpected"),
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
    assert result["errors"] == {"base": "unknown"}


async def test_reconfigure_cloud_success(
    hass: HomeAssistant,
    mock_setup_entry: AsyncMock,
) -> None:
    """Test successful cloud reconfiguration with auto-detected IDs."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Enphase Battery Cloud",
        data={
            CONF_CONNECTION_MODE: CONNECTION_MODE_CLOUD,
            CONF_USERNAME: "test@example.com",
            CONF_PASSWORD: "testpassword",
        },
        unique_id="RECONFIG_CLOUD",
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": "reconfigure",
            "entry_id": entry.entry_id,
        },
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_CONNECTION_MODE: CONNECTION_MODE_CLOUD},
    )

    assert result["step_id"] == "reconfigure_cloud"

    with patch(
        "custom_components.enphase_battery.config_flow.validate_cloud_input",
        return_value={
            "title": "Enphase Battery Cloud (new@example.com)",
            "serial": "RECONFIG_CLOUD",
            "site_id": 55555,
            "user_id": 66666,
        },
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_USERNAME: "new@example.com",
                CONF_PASSWORD: "newpassword",
            },
        )

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    # Verify entry data was updated with auto-detected IDs
    assert entry.data[CONF_USERNAME] == "new@example.com"
    assert entry.data[CONF_SITE_ID] == "55555"
    assert entry.data[CONF_USER_ID] == "66666"
    assert entry.data[CONF_CONNECTION_MODE] == CONNECTION_MODE_CLOUD


async def test_reconfigure_cloud_cannot_connect(
    hass: HomeAssistant,
    mock_setup_entry: AsyncMock,
) -> None:
    """Test cloud reconfiguration with connection error."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Enphase Battery Cloud",
        data={
            CONF_CONNECTION_MODE: CONNECTION_MODE_CLOUD,
            CONF_USERNAME: "test@example.com",
            CONF_PASSWORD: "testpassword",
        },
        unique_id="RECONFIG_CLOUD_ERR",
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": "reconfigure",
            "entry_id": entry.entry_id,
        },
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_CONNECTION_MODE: CONNECTION_MODE_CLOUD},
    )

    with patch(
        "custom_components.enphase_battery.config_flow.validate_cloud_input",
        side_effect=CannotConnect,
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_USERNAME: "test@example.com",
                CONF_PASSWORD: "testpassword",
            },
        )

    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_reconfigure_cloud_invalid_auth(
    hass: HomeAssistant,
    mock_setup_entry: AsyncMock,
) -> None:
    """Test cloud reconfiguration with auth error."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Enphase Battery Cloud",
        data={
            CONF_CONNECTION_MODE: CONNECTION_MODE_CLOUD,
            CONF_USERNAME: "test@example.com",
            CONF_PASSWORD: "testpassword",
        },
        unique_id="RECONFIG_CLOUD_AUTH",
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": "reconfigure",
            "entry_id": entry.entry_id,
        },
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_CONNECTION_MODE: CONNECTION_MODE_CLOUD},
    )

    with patch(
        "custom_components.enphase_battery.config_flow.validate_cloud_input",
        side_effect=InvalidAuth,
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_USERNAME: "test@example.com",
                CONF_PASSWORD: "badpassword",
            },
        )

    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}


async def test_reconfigure_cloud_unknown_error(
    hass: HomeAssistant,
    mock_setup_entry: AsyncMock,
) -> None:
    """Test cloud reconfiguration with unknown error."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Enphase Battery Cloud",
        data={
            CONF_CONNECTION_MODE: CONNECTION_MODE_CLOUD,
            CONF_USERNAME: "test@example.com",
            CONF_PASSWORD: "testpassword",
        },
        unique_id="RECONFIG_CLOUD_UNK",
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": "reconfigure",
            "entry_id": entry.entry_id,
        },
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_CONNECTION_MODE: CONNECTION_MODE_CLOUD},
    )

    with patch(
        "custom_components.enphase_battery.config_flow.validate_cloud_input",
        side_effect=RuntimeError("unexpected"),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_USERNAME: "test@example.com",
                CONF_PASSWORD: "testpassword",
            },
        )

    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"base": "unknown"}


# ---------------------------------------------------------------------------
# Zeroconf discovery
# ---------------------------------------------------------------------------


def _zeroconf_info(host: str = "192.168.1.50", serial: str = "122050042807") -> ZeroconfServiceInfo:
    """Build a ZeroconfServiceInfo for a discovered Envoy."""
    return ZeroconfServiceInfo(
        ip_address=ip_address(host),
        ip_addresses=[ip_address(host)],
        hostname="envoy.local.",
        name=f"envoy_{serial}._enphase-envoy._tcp.local.",
        port=443,
        type="_enphase-envoy._tcp.local.",
        properties={"serialnum": serial},
    )


async def test_zeroconf_discovery_creates_entry(hass: HomeAssistant, mock_local_api) -> None:
    """A discovered Envoy shows a confirm form and creates a local entry."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_ZEROCONF}, data=_zeroconf_info()
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "zeroconf_confirm"

    result2 = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"cloud_username": "u@example.com", "cloud_password": "pw", "enable_cloud_control": False},
    )
    assert result2["type"] == FlowResultType.CREATE_ENTRY
    assert result2["data"][CONF_CONNECTION_MODE] == CONNECTION_MODE_LOCAL
    assert result2["data"][CONF_ENVOY_HOST] == "192.168.1.50"


async def test_zeroconf_already_configured_updates_host(hass: HomeAssistant) -> None:
    """Re-discovering a configured Envoy aborts and refreshes its stored host."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_CONNECTION_MODE: CONNECTION_MODE_LOCAL,
            CONF_ENVOY_HOST: "192.168.1.10",
            "cloud_username": "u@example.com",
            "cloud_password": "pw",
        },
        unique_id="122050042807",
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_ZEROCONF},
        data=_zeroconf_info(host="192.168.1.50", serial="122050042807"),
    )

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert entry.data[CONF_ENVOY_HOST] == "192.168.1.50"


# ---------------------------------------------------------------------------
# DHCP discovery
# ---------------------------------------------------------------------------


def _dhcp_info(ip: str = "192.168.1.60") -> DhcpServiceInfo:
    """Build a DhcpServiceInfo for a discovered Envoy."""
    return DhcpServiceInfo(ip=ip, hostname="envoy", macaddress="001dc0aabbcc")


async def test_dhcp_discovery_creates_entry(hass: HomeAssistant, mock_local_api) -> None:
    """A DHCP-discovered Envoy resolves its serial via /info and creates an entry."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_DHCP}, data=_dhcp_info()
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "zeroconf_confirm"

    result2 = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"cloud_username": "u@example.com", "cloud_password": "pw", "enable_cloud_control": False},
    )
    assert result2["type"] == FlowResultType.CREATE_ENTRY
    assert result2["data"][CONF_ENVOY_HOST] == "192.168.1.60"


async def test_dhcp_discovery_cannot_connect(hass: HomeAssistant, mock_local_api) -> None:
    """A DHCP-discovered host that cannot be queried aborts cleanly."""
    mock_local_api._get_info = AsyncMock(side_effect=EnvoyLocalApiError("unreachable"))

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_DHCP}, data=_dhcp_info()
    )

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "cannot_connect"


async def test_dhcp_discovery_no_serial_aborts(hass: HomeAssistant, mock_local_api) -> None:
    """A DHCP host whose /info lacks a serial aborts as cannot_connect."""
    mock_local_api._get_info = AsyncMock(return_value={"device": {}})

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_DHCP}, data=_dhcp_info()
    )

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "cannot_connect"


async def test_zeroconf_prefers_ipv4(hass: HomeAssistant, mock_local_api) -> None:
    """When both IPv4 and IPv6 are advertised, the IPv4 address is used."""
    info = ZeroconfServiceInfo(
        ip_address=ip_address("fd8d::c272"),
        ip_addresses=[ip_address("fd8d::c272"), ip_address("192.168.1.77")],
        hostname="envoy.local.",
        name="envoy_122050042807._enphase-envoy._tcp.local.",
        port=443,
        type="_enphase-envoy._tcp.local.",
        properties={"serialnum": "122050042807"},
    )
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_ZEROCONF}, data=info
    )
    assert result["type"] == FlowResultType.FORM
    result2 = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"cloud_username": "u@example.com", "cloud_password": "pw", "enable_cloud_control": False},
    )
    assert result2["type"] == FlowResultType.CREATE_ENTRY
    assert result2["data"][CONF_ENVOY_HOST] == "192.168.1.77"


async def test_zeroconf_ipv6_only_keeps_existing_host(hass: HomeAssistant) -> None:
    """An IPv6-only rediscovery must not overwrite a working (reachable) host."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_CONNECTION_MODE: CONNECTION_MODE_LOCAL,
            CONF_ENVOY_HOST: "envoy.local",
            "cloud_username": "u@example.com",
            "cloud_password": "pw",
        },
        unique_id="122050042807",
    )
    entry.add_to_hass(hass)

    info = ZeroconfServiceInfo(
        ip_address=ip_address("fd8d::c272"),
        ip_addresses=[ip_address("fd8d::c272")],  # IPv6 only
        hostname="envoy.local.",
        name="envoy_122050042807._enphase-envoy._tcp.local.",
        port=443,
        type="_enphase-envoy._tcp.local.",
        properties={"serialnum": "122050042807"},
    )
    # The hostname cannot be resolved here, so no IPv4 is found and the host is kept.
    with patch("custom_components.enphase_battery.config_flow.socket.getaddrinfo", side_effect=OSError):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_ZEROCONF}, data=info
        )

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert entry.data[CONF_ENVOY_HOST] == "envoy.local"


async def test_zeroconf_ipv6_resolves_hostname_to_ipv4(hass: HomeAssistant) -> None:
    """When only IPv6 is advertised, the .local hostname is resolved to IPv4."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_CONNECTION_MODE: CONNECTION_MODE_LOCAL,
            CONF_ENVOY_HOST: "10.0.0.9",
            "cloud_username": "u@example.com",
            "cloud_password": "pw",
        },
        unique_id="122050042807",
    )
    entry.add_to_hass(hass)

    info = ZeroconfServiceInfo(
        ip_address=ip_address("fd8d::c272"),
        ip_addresses=[ip_address("fd8d::c272")],  # IPv6 only
        hostname="envoy.local.",
        name="envoy_122050042807._enphase-envoy._tcp.local.",
        port=443,
        type="_enphase-envoy._tcp.local.",
        properties={"serialnum": "122050042807"},
    )
    resolved = [(2, 1, 6, "", ("192.168.1.39", 443))]
    with patch("custom_components.enphase_battery.config_flow.socket.getaddrinfo", return_value=resolved):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_ZEROCONF}, data=info
        )

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert entry.data[CONF_ENVOY_HOST] == "192.168.1.39"
