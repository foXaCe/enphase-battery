"""Config flow for Enphase Battery integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult

from .const import (
    DOMAIN,
    CONF_USE_MQTT,
    CONF_SITE_ID,
    CONF_USER_ID,
    CONF_CONNECTION_MODE,
    CONF_ENVOY_HOST,
    CONNECTION_MODE_LOCAL,
    CONNECTION_MODE_CLOUD,
)

_LOGGER = logging.getLogger(__name__)

# Schéma de configuration - Choix du mode de connexion
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


async def validate_local_input(
    hass: HomeAssistant, data: dict[str, Any]
) -> dict[str, Any]:
    """Validate local Envoy connection.

    Data has the keys from STEP_LOCAL_DATA_SCHEMA with values provided by the user.
    """
    from .envoy_local_api import EnphaseEnvoyLocalAPI, EnvoyAuthError, EnvoyConnectionError

    host = data[CONF_ENVOY_HOST]
    cloud_username = data.get("cloud_username")
    cloud_password = data.get("cloud_password")

    # Create temporary session for validation
    import aiohttp

    async with aiohttp.ClientSession() as session:
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
            serial = (
                info.get("device", {}).get("sn") or
                info.get("sn") or
                api._serial_number or
                "UNKNOWN"
            )

            return {
                "title": f"Enphase Battery Local ({host})",
                "serial": serial,
                "firmware": api._firmware_version,
            }

        except EnvoyAuthError as err:
            _LOGGER.error(f"Authentication failed: {err}")
            raise InvalidAuth from err
        except EnvoyConnectionError as err:
            _LOGGER.error(f"Connection failed: {err}")
            raise CannotConnect from err
        except Exception as err:
            _LOGGER.exception("Unexpected error during validation")
            raise CannotConnect from err


async def validate_cloud_input(
    hass: HomeAssistant, data: dict[str, Any]
) -> dict[str, Any]:
    """Validate cloud Enlighten connection.

    Data has the keys from STEP_CLOUD_DATA_SCHEMA with values provided by the user.
    """
    # TODO: Implémenter la validation avec l'API Cloud Enphase
    # 1. Authenticate with username/password
    # 2. Get user sites list
    # 3. Get battery serial for unique_id

    username = data[CONF_USERNAME]

    # from .api import EnphaseBatteryAPI
    # api = EnphaseBatteryAPI(hass, username, data[CONF_PASSWORD])
    # try:
    #     await api.authenticate()
    #     battery_info = await api.get_battery_info()
    #     serial = battery_info["serial"]
    # except AuthenticationError:
    #     raise InvalidAuth
    # except Exception as err:
    #     raise CannotConnect from err

    # Retourner les infos pour créer l'entrée
    return {
        "title": f"Enphase Battery Cloud ({username})",
        "serial": "TEMP_SERIAL",  # TODO: récupérer le vrai serial depuis l'API
    }


class EnphaseBatteryConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Enphase Battery."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize config flow."""
        self._connection_mode: str | None = None

    @staticmethod
    def async_get_options_flow(config_entry):
        """Get the options flow for this handler."""
        return EnphaseBatteryOptionsFlow(config_entry)

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
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

    async def async_step_local(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
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

    async def async_step_cloud(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
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
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle re-authentication confirmation."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                await validate_input(self.hass, user_input)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                # Mettre à jour l'entrée existante
                entry = self.hass.config_entries.async_get_entry(
                    self.context["entry_id"]
                )
                if entry:
                    self.hass.config_entries.async_update_entry(
                        entry, data=user_input
                    )
                    await self.hass.config_entries.async_reload(entry.entry_id)
                    return self.async_abort(reason="reauth_successful")

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )


class EnphaseBatteryOptionsFlow(config_entries.OptionsFlow):
    """Handle options flow for Enphase Battery."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        if user_input is not None:
            # Update config entry with new IDs
            new_data = {**self.config_entry.data}

            # Only update if values were provided
            if user_input.get(CONF_SITE_ID):
                new_data[CONF_SITE_ID] = user_input[CONF_SITE_ID]
            if user_input.get(CONF_USER_ID):
                new_data[CONF_USER_ID] = user_input[CONF_USER_ID]

            self.hass.config_entries.async_update_entry(
                self.config_entry, data=new_data
            )
            return self.async_create_entry(title="", data={})

        # Get current values (auto-detected or manually configured)
        current_site_id = self.config_entry.data.get(CONF_SITE_ID, "")
        current_user_id = self.config_entry.data.get(CONF_USER_ID, "")

        # Simple schema with suggested values
        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                vol.Schema(
                    {
                        vol.Optional(CONF_SITE_ID): str,
                        vol.Optional(CONF_USER_ID): str,
                    }
                ),
                {
                    CONF_SITE_ID: current_site_id,
                    CONF_USER_ID: current_user_id,
                }
            ),
        )


class CannotConnect(Exception):
    """Error to indicate we cannot connect."""


class InvalidAuth(Exception):
    """Error to indicate there is invalid auth."""
