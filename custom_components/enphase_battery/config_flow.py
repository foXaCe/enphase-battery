"""Config flow for Enphase Battery integration."""

from __future__ import annotations

import logging
import socket
from typing import Any

from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)
from homeassistant.helpers.service_info.dhcp import DhcpServiceInfo
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo
import voluptuous as vol

from .api import (
    EnphaseBatteryAPI,
    EnphaseBatteryApiError,
    EnphaseBatteryAuthError,
    EnphaseEnvoyLocalAPI,
    EnvoyAuthError,
    EnvoyConnectionError,
    EnvoyLocalApiError,
)
from .const import (
    CONF_CONNECTION_MODE,
    CONF_ENVOY_HOST,
    CONF_SITE_ID,
    CONF_USER_ID,
    CONNECTION_MODE_CLOUD,
    CONNECTION_MODE_LOCAL,
    CONNECTION_MODES,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

# Translated dropdown for the connection mode (labels live in translations).
CONNECTION_MODE_SELECTOR = SelectSelector(
    SelectSelectorConfig(
        options=CONNECTION_MODES,
        translation_key="connection_mode",
        mode=SelectSelectorMode.LIST,
    )
)

# Configuration schema - Connection mode selection
STEP_MODE_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_CONNECTION_MODE, default=CONNECTION_MODE_LOCAL): CONNECTION_MODE_SELECTOR,
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
    host = data[CONF_ENVOY_HOST]
    cloud_username = data.get("cloud_username")
    cloud_password = data.get("cloud_password")

    session = async_get_clientsession(hass, verify_ssl=False)

    # For local mode, we always use cloud credentials (firmware 7.x/8.x)
    api = EnphaseEnvoyLocalAPI(
        session,
        host,
        username=None,  # type: ignore[arg-type]
        password=None,
        cloud_username=cloud_username,
        cloud_password=cloud_password,
    )

    try:
        await api.authenticate()

        # Get basic info
        info = await api._get_info()
        serial = info.get("device", {}).get("sn") or info.get("sn") or api.serial_number or "UNKNOWN"

        return {
            "title": f"Enphase Battery Local ({host})",
            "serial": serial,
            "firmware": api.firmware_version,
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

    VERSION = 3

    def __init__(self) -> None:
        """Initialize config flow."""
        self._connection_mode: str | None = None
        self._discovered_host: str | None = None

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Get the options flow for this handler."""
        return EnphaseBatteryOptionsFlowHandler(config_entry)

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
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

    async def async_step_local(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
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
        )

    async def async_step_cloud(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
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
        )

    async def async_step_zeroconf(self, discovery_info: ZeroconfServiceInfo) -> ConfigFlowResult:
        """Handle an Envoy discovered via zeroconf (mDNS)."""
        serial = discovery_info.properties.get("serialnum") or discovery_info.hostname.partition(".")[0]
        # Envoys often advertise only an IPv6 ULA over mDNS, which is usually not
        # routable. Prefer IPv4; otherwise fall back to the (resolvable) hostname
        # rather than a raw IPv6 literal.
        ipv4 = next((str(ip) for ip in discovery_info.ip_addresses if ip.version == 4), None)
        if not ipv4 and discovery_info.hostname:
            # The Envoy advertised IPv6 only, and Home Assistant's async resolver
            # cannot resolve .local (mDNS); resolve the hostname to IPv4 ourselves.
            ipv4 = await self._async_resolve_ipv4(discovery_info.hostname.rstrip("."))
        host = ipv4 or discovery_info.hostname.rstrip(".") or discovery_info.host

        await self.async_set_unique_id(str(serial))
        # Only refresh a configured entry's host when we found an IPv4, so a
        # working host is never clobbered with an unreachable IPv6 literal.
        self._abort_if_unique_id_configured(updates={CONF_ENVOY_HOST: ipv4} if ipv4 else {})

        self._discovered_host = host
        self.context["title_placeholders"] = {"name": f"Envoy {serial}"}
        return await self.async_step_zeroconf_confirm()

    async def _async_resolve_ipv4(self, hostname: str) -> str | None:
        """Resolve a hostname to an IPv4 address using the OS resolver (handles mDNS)."""
        try:
            infos = await self.hass.async_add_executor_job(
                socket.getaddrinfo, hostname, 443, socket.AF_INET, socket.SOCK_STREAM
            )
        except OSError:
            return None
        return str(infos[0][4][0]) if infos else None

    async def async_step_zeroconf_confirm(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Collect the Enlighten credentials for a discovered Envoy (local mode)."""
        errors: dict[str, str] = {}

        if user_input is not None:
            data = {
                CONF_CONNECTION_MODE: CONNECTION_MODE_LOCAL,
                CONF_ENVOY_HOST: self._discovered_host,
                **user_input,
            }
            try:
                info = await validate_local_input(self.hass, data)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                return self.async_create_entry(title=info["title"], data=data)

        return self.async_show_form(
            step_id="zeroconf_confirm",
            data_schema=vol.Schema(
                {
                    vol.Required("cloud_username"): str,
                    vol.Required("cloud_password"): str,
                    vol.Optional("enable_cloud_control", default=False): bool,
                }
            ),
            errors=errors,
            description_placeholders={"host": self._discovered_host or ""},
        )

    async def async_step_dhcp(self, discovery_info: DhcpServiceInfo) -> ConfigFlowResult:
        """Handle an Envoy discovered via DHCP."""
        host = discovery_info.ip

        # DHCP carries no serial, so query the unauthenticated /info to identify the Envoy.
        session = async_get_clientsession(self.hass, verify_ssl=False)
        api = EnphaseEnvoyLocalAPI(session, host)
        try:
            info = await api._get_info()
        except EnvoyLocalApiError:
            return self.async_abort(reason="cannot_connect")

        serial = (
            info.get("device", {}).get("sn")
            or info.get("device", {}).get("serial_num")
            or info.get("sn")
            or info.get("serial_num")
            or info.get("serialNumber")
        )
        if not serial:
            return self.async_abort(reason="cannot_connect")

        await self.async_set_unique_id(str(serial))
        self._abort_if_unique_id_configured(updates={CONF_ENVOY_HOST: host})

        self._discovered_host = host
        self.context["title_placeholders"] = {"name": f"Envoy {serial}"}
        return await self.async_step_zeroconf_confirm()

    async def async_step_reauth(self, entry_data: dict[str, Any]) -> ConfigFlowResult:
        """Handle re-authentication."""
        self._reauth_entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
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

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
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
                vol.Required(CONF_CONNECTION_MODE, default=current_mode): CONNECTION_MODE_SELECTOR,
            }
        )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=data_schema,
        )

    async def async_step_reconfigure_local(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
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

    async def async_step_reconfigure_cloud(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
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

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        super().__init__()
        self._config_entry = config_entry
        self._connection_mode: str | None = None

    @property
    def config_entry(self) -> config_entries.ConfigEntry:
        """Return config entry."""
        return self._config_entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
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
                vol.Required(CONF_CONNECTION_MODE, default=current_mode): CONNECTION_MODE_SELECTOR,
            }
        )

        return self.async_show_form(
            step_id="init",
            data_schema=data_schema,
        )

    async def async_step_local(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
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

    async def async_step_cloud(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
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
