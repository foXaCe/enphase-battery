"""Config flow for Enphase Battery integration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
import voluptuous as vol

from .const import (
    CONF_CONNECTION_MODE,
    CONF_ENVOY_HOST,
    CONF_SITE_ID,
    CONF_USER_ID,
    CONNECTION_MODE_CLOUD,
    CONNECTION_MODE_LOCAL,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

# Configuration schema - Connection mode selection
STEP_MODE_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_CONNECTION_MODE, default=CONNECTION_MODE_LOCAL): vol.In(
            {
                CONNECTION_MODE_LOCAL: "Local (Envoy direct - rapide, pas de quota API)",
                CONNECTION_MODE_CLOUD: "Cloud (Enlighten - plus lent, quota API)",
            }
        ),
    }
)

# Schéma pour mode LOCAL - demande directement les identifiants cloud
STEP_LOCAL_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_ENVOY_HOST, default="envoy.local"): str,
        vol.Required("cloud_username"): str,
        vol.Required("cloud_password"): str,
        vol.Optional("enable_cloud_control", default=False): bool,
    }
)

# Schéma pour mode CLOUD
STEP_CLOUD_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
        vol.Optional(CONF_SITE_ID, description={"suggested_value": ""}): str,
        vol.Optional(CONF_USER_ID, description={"suggested_value": ""}): str,
    }
)


async def validate_local_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate local Envoy connection.

    Data has the keys from STEP_LOCAL_DATA_SCHEMA with values provided by the user.
    """
    from homeassistant.helpers.aiohttp_client import async_get_clientsession

    from .envoy_local_api import EnphaseEnvoyLocalAPI, EnvoyAuthError, EnvoyConnectionError

    host = data[CONF_ENVOY_HOST]
    cloud_username = data.get("cloud_username")
    cloud_password = data.get("cloud_password")

    session = async_get_clientsession(hass, verify_ssl=False)

    # For local mode, we always use cloud credentials (firmware 7.x/8.x)
    api = EnphaseEnvoyLocalAPI(
        session,
        host,
        username=None,
        password=None,
        cloud_username=cloud_username,
        cloud_password=cloud_password,
    )

    try:
        await api.authenticate()

        # Get basic info
        info = await api._get_info()
        serial = info.get("device", {}).get("sn") or info.get("sn") or api._serial_number or "UNKNOWN"

        return {
            "title": f"Enphase Battery Local ({host})",
            "serial": serial,
            "firmware": api._firmware_version,
        }

    except EnvoyAuthError as err:
        _LOGGER.error("Authentication failed: %s", err)
        raise InvalidAuth from err
    except EnvoyConnectionError as err:
        _LOGGER.error("Connection failed: %s", err)
        raise CannotConnect from err
    except Exception as err:
        _LOGGER.exception("Unexpected error during validation")
        raise CannotConnect from err


async def validate_cloud_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate cloud Enlighten connection.

    Data has the keys from STEP_CLOUD_DATA_SCHEMA with values provided by the user.
    """
    from homeassistant.helpers.aiohttp_client import async_get_clientsession

    from .api import EnphaseBatteryAPI, EnphaseBatteryApiError, EnphaseBatteryAuthError

    username = data[CONF_USERNAME]
    password = data[CONF_PASSWORD]

    site_id_str = data.get(CONF_SITE_ID, "")
    user_id_str = data.get(CONF_USER_ID, "")
    site_id = int(site_id_str) if site_id_str else None
    user_id = int(user_id_str) if user_id_str else None

    session = async_get_clientsession(hass)
    api = EnphaseBatteryAPI(
        session=session,
        username=username,
        password=password,
        site_id=site_id,
        user_id=user_id,
    )

    try:
        await api.authenticate()
        # Use site_id as unique identifier for cloud entries
        serial = str(api._site_id) if api._site_id else f"cloud_{username}"
        return {
            "title": f"Enphase Battery Cloud ({username})",
            "serial": serial,
            "site_id": api._site_id,
            "user_id": api._user_id,
        }
    except EnphaseBatteryAuthError as err:
        _LOGGER.error("Cloud authentication failed: %s", err)
        raise InvalidAuth from err
    except EnphaseBatteryApiError as err:
        _LOGGER.error("Cloud connection failed: %s", err)
        raise CannotConnect from err
    except Exception as err:
        _LOGGER.exception("Unexpected error during cloud validation")
        raise CannotConnect from err


class EnphaseBatteryConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Enphase Battery."""

    VERSION = 2

    def __init__(self) -> None:
        """Initialize config flow."""
        self._connection_mode: str | None = None

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Get the options flow for this handler."""
        return EnphaseBatteryOptionsFlowHandler()

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Handle the initial step - select connection mode."""
        if user_input is not None:
            self._connection_mode = user_input[CONF_CONNECTION_MODE]

            # Redirect to appropriate config step
            if self._connection_mode == CONNECTION_MODE_LOCAL:
                return await self.async_step_local()
            else:
                return await self.async_step_cloud()

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_MODE_SCHEMA,
        )

    async def async_step_local(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Handle local Envoy configuration."""
        errors: dict[str, str] = {}

        if user_input is not None:
            # Add connection mode to data
            user_input[CONF_CONNECTION_MODE] = CONNECTION_MODE_LOCAL

            try:
                info = await validate_local_input(self.hass, user_input)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                # Créer une entrée unique basée sur le serial
                await self.async_set_unique_id(info["serial"])
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title=info["title"],
                    data=user_input,
                )

        return self.async_show_form(
            step_id="local",
            data_schema=STEP_LOCAL_DATA_SCHEMA,
            errors=errors,
            description_placeholders={
                "mode": "Local",
                "benefits": "Réactivité maximale\n✅ Pas de quota API\n✅ Identifiants Enlighten requis pour firmware 7.x/8.x",
            },
        )

    async def async_step_cloud(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Handle cloud Enlighten configuration."""
        errors: dict[str, str] = {}

        if user_input is not None:
            # Add connection mode to data
            user_input[CONF_CONNECTION_MODE] = CONNECTION_MODE_CLOUD

            try:
                info = await validate_cloud_input(self.hass, user_input)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                # Save auto-detected IDs to avoid re-detection on next startup
                if info.get("site_id"):
                    user_input[CONF_SITE_ID] = str(info["site_id"])
                if info.get("user_id"):
                    user_input[CONF_USER_ID] = str(info["user_id"])

                # Créer une entrée unique basée sur le serial
                await self.async_set_unique_id(info["serial"])
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title=info["title"],
                    data=user_input,
                )

        return self.async_show_form(
            step_id="cloud",
            data_schema=STEP_CLOUD_DATA_SCHEMA,
            errors=errors,
            description_placeholders={
                "mode": "Cloud",
                "benefits": "Accès à distance\n⚠️ Quota API limité\n⚠️ Latence plus élevée",
            },
        )

    async def async_step_reauth(self, entry_data: dict[str, Any]) -> FlowResult:
        """Handle re-authentication."""
        self._reauth_entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Handle re-authentication confirmation."""
        errors: dict[str, str] = {}

        # Determine which schema to use based on existing entry's connection mode
        entry = getattr(self, "_reauth_entry", None)
        is_local_mode = entry and entry.data.get(CONF_CONNECTION_MODE) == CONNECTION_MODE_LOCAL
        data_schema = STEP_LOCAL_DATA_SCHEMA if is_local_mode else STEP_CLOUD_DATA_SCHEMA

        if user_input is not None:
            # Add connection mode from existing entry
            if entry:
                user_input[CONF_CONNECTION_MODE] = entry.data.get(CONF_CONNECTION_MODE, CONNECTION_MODE_CLOUD)

            try:
                if is_local_mode:
                    await validate_local_input(self.hass, user_input)
                else:
                    await validate_cloud_input(self.hass, user_input)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                # Mettre à jour l'entrée existante
                if entry:
                    self.hass.config_entries.async_update_entry(entry, data=user_input)
                    await self.hass.config_entries.async_reload(entry.entry_id)
                    return self.async_abort(reason="reauth_successful")

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=data_schema,
            errors=errors,
        )

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Handle reconfiguration of the integration."""
        entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])
        if entry is None:
            return self.async_abort(reason="unknown")

        current_mode = entry.data.get(CONF_CONNECTION_MODE, CONNECTION_MODE_CLOUD)

        if user_input is not None:
            new_mode = user_input[CONF_CONNECTION_MODE]
            if new_mode == CONNECTION_MODE_LOCAL:
                self._reconfigure_entry = entry
                return await self.async_step_reconfigure_local()
            else:
                self._reconfigure_entry = entry
                return await self.async_step_reconfigure_cloud()

        data_schema = vol.Schema(
            {
                vol.Required(CONF_CONNECTION_MODE, default=current_mode): vol.In(
                    {
                        CONNECTION_MODE_LOCAL: "Local (Envoy direct)",
                        CONNECTION_MODE_CLOUD: "Cloud (Enlighten)",
                    }
                ),
            }
        )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=data_schema,
        )

    async def async_step_reconfigure_local(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Reconfigure local mode settings."""
        errors: dict[str, str] = {}
        entry = getattr(self, "_reconfigure_entry", None)
        current_data = entry.data if entry else {}

        if user_input is not None:
            user_input[CONF_CONNECTION_MODE] = CONNECTION_MODE_LOCAL

            try:
                await validate_local_input(self.hass, user_input)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception during reconfigure")
                errors["base"] = "unknown"
            else:
                if entry:
                    self.hass.config_entries.async_update_entry(entry, data=user_input)
                    await self.hass.config_entries.async_reload(entry.entry_id)
                    return self.async_abort(reason="reconfigure_successful")

        data_schema = vol.Schema(
            {
                vol.Required(CONF_ENVOY_HOST, default=current_data.get(CONF_ENVOY_HOST, "envoy.local")): str,
                vol.Required(
                    "cloud_username",
                    default=current_data.get("cloud_username", current_data.get(CONF_USERNAME, "")),
                ): str,
                vol.Required(
                    "cloud_password",
                    default=current_data.get("cloud_password", current_data.get(CONF_PASSWORD, "")),
                ): str,
                vol.Optional("enable_cloud_control", default=current_data.get("enable_cloud_control", False)): bool,
            }
        )

        return self.async_show_form(
            step_id="reconfigure_local",
            data_schema=data_schema,
            errors=errors,
        )

    async def async_step_reconfigure_cloud(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Reconfigure cloud mode settings."""
        errors: dict[str, str] = {}
        entry = getattr(self, "_reconfigure_entry", None)
        current_data = entry.data if entry else {}

        if user_input is not None:
            user_input[CONF_CONNECTION_MODE] = CONNECTION_MODE_CLOUD

            try:
                info = await validate_cloud_input(self.hass, user_input)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception during reconfigure")
                errors["base"] = "unknown"
            else:
                if info.get("site_id"):
                    user_input[CONF_SITE_ID] = str(info["site_id"])
                if info.get("user_id"):
                    user_input[CONF_USER_ID] = str(info["user_id"])
                if entry:
                    self.hass.config_entries.async_update_entry(entry, data=user_input)
                    await self.hass.config_entries.async_reload(entry.entry_id)
                    return self.async_abort(reason="reconfigure_successful")

        data_schema = vol.Schema(
            {
                vol.Required(CONF_USERNAME, default=current_data.get(CONF_USERNAME, "")): str,
                vol.Required(CONF_PASSWORD, default=current_data.get(CONF_PASSWORD, "")): str,
                vol.Optional(CONF_SITE_ID, default=current_data.get(CONF_SITE_ID, "")): str,
                vol.Optional(CONF_USER_ID, default=current_data.get(CONF_USER_ID, "")): str,
            }
        )

        return self.async_show_form(
            step_id="reconfigure_cloud",
            data_schema=data_schema,
            errors=errors,
        )


class EnphaseBatteryOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options flow for Enphase Battery."""

    def __init__(self) -> None:
        """Initialize options flow."""
        self._connection_mode: str | None = None

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """First step - choose connection mode."""
        current_data = self.config_entry.data
        current_mode = current_data.get(CONF_CONNECTION_MODE, CONNECTION_MODE_CLOUD)

        if user_input is not None:
            self._connection_mode = user_input[CONF_CONNECTION_MODE]

            # Redirect to appropriate config step
            if self._connection_mode == CONNECTION_MODE_LOCAL:
                return await self.async_step_local()
            else:
                return await self.async_step_cloud()

        data_schema = vol.Schema(
            {
                vol.Required(CONF_CONNECTION_MODE, default=current_mode): vol.In(
                    {
                        CONNECTION_MODE_LOCAL: "Local (Envoy direct)",
                        CONNECTION_MODE_CLOUD: "Cloud (Enlighten)",
                    }
                ),
            }
        )

        return self.async_show_form(
            step_id="init",
            data_schema=data_schema,
        )

    async def async_step_local(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Configure local mode."""
        errors: dict[str, str] = {}
        current_data = self.config_entry.data

        if user_input is not None:
            # Add connection mode
            user_input[CONF_CONNECTION_MODE] = CONNECTION_MODE_LOCAL

            try:
                await validate_local_input(self.hass, user_input)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception during options validation")
                errors["base"] = "unknown"
            else:
                # Update the config entry
                self.hass.config_entries.async_update_entry(
                    self.config_entry,
                    data=user_input,
                )
                return self.async_create_entry(title="", data={})

        data_schema = vol.Schema(
            {
                vol.Required(
                    CONF_ENVOY_HOST,
                    default=current_data.get(CONF_ENVOY_HOST, "envoy.local"),
                ): str,
                vol.Required(
                    "cloud_username",
                    default=current_data.get("cloud_username", current_data.get(CONF_USERNAME, "")),
                ): str,
                vol.Required(
                    "cloud_password",
                    default=current_data.get("cloud_password", current_data.get(CONF_PASSWORD, "")),
                ): str,
                vol.Optional(
                    "enable_cloud_control",
                    default=current_data.get("enable_cloud_control", False),
                ): bool,
            }
        )

        return self.async_show_form(
            step_id="local",
            data_schema=data_schema,
            errors=errors,
        )

    async def async_step_cloud(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Configure cloud mode."""
        errors: dict[str, str] = {}
        current_data = self.config_entry.data

        if user_input is not None:
            # Add connection mode
            user_input[CONF_CONNECTION_MODE] = CONNECTION_MODE_CLOUD

            try:
                await validate_cloud_input(self.hass, user_input)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception during options validation")
                errors["base"] = "unknown"
            else:
                # Update the config entry
                self.hass.config_entries.async_update_entry(
                    self.config_entry,
                    data=user_input,
                )
                return self.async_create_entry(title="", data={})

        data_schema = vol.Schema(
            {
                vol.Required(
                    CONF_USERNAME,
                    default=current_data.get(CONF_USERNAME, current_data.get("cloud_username", "")),
                ): str,
                vol.Required(
                    CONF_PASSWORD,
                    default=current_data.get(CONF_PASSWORD, current_data.get("cloud_password", "")),
                ): str,
                vol.Optional(
                    CONF_SITE_ID,
                    default=current_data.get(CONF_SITE_ID, ""),
                ): str,
                vol.Optional(
                    CONF_USER_ID,
                    default=current_data.get(CONF_USER_ID, ""),
                ): str,
            }
        )

        return self.async_show_form(
            step_id="cloud",
            data_schema=data_schema,
            errors=errors,
        )


class CannotConnect(Exception):
    """Error to indicate we cannot connect."""


class InvalidAuth(Exception):
    """Error to indicate there is invalid auth."""
