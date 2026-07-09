"""Config flow for the Junos NETCONF integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD, CONF_PORT, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from .const import (
    CONF_HOST,
    CONF_INTERFACE_ALLOWLIST,
    CONF_SCAN_INTERVAL,
    CONF_TIMEOUT,
    CONF_VERIFY_HOSTKEY,
    DEFAULT_NETCONF_PORT,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_TIMEOUT,
    DOMAIN,
    MIN_SCAN_INTERVAL,
    MIN_TIMEOUT,
)
from .exceptions import JunosNetconfAuthError, JunosNetconfConnectionError
from .junos_client import JunosPyEzClient

_LOGGER = logging.getLogger(__name__)


STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Optional(CONF_PORT, default=DEFAULT_NETCONF_PORT): vol.All(
            vol.Coerce(int),
            vol.Range(min=1, max=65535),
        ),
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): selector.TextSelector(
            selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
        ),
        vol.Optional(CONF_TIMEOUT, default=DEFAULT_TIMEOUT): vol.All(
            vol.Coerce(int),
            vol.Range(min=MIN_TIMEOUT),
        ),
        vol.Optional(CONF_VERIFY_HOSTKEY, default=False): bool,
        vol.Optional(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): vol.All(
            vol.Coerce(int),
            vol.Range(min=MIN_SCAN_INTERVAL),
        ),
        vol.Optional(
            CONF_INTERFACE_ALLOWLIST, default=""
        ): selector.TextSelector(),
    }
)


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> str:
    """Validate credentials by opening NETCONF and reading operational data."""
    client = JunosPyEzClient(
        host=data[CONF_HOST],
        port=data[CONF_PORT],
        username=data[CONF_USERNAME],
        password=data[CONF_PASSWORD],
        timeout=data[CONF_TIMEOUT],
        verify_hostkey=data[CONF_VERIFY_HOSTKEY],
    )
    device = await hass.async_add_executor_job(client.get_data)
    return device.serial_number or device.hostname or f"{data[CONF_HOST]}:{data[CONF_PORT]}"


class JunosNetconfConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a Junos NETCONF config flow."""

    VERSION = 1

    async def async_step_user(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> FlowResult:
        """Handle the initial setup step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                unique_id = await validate_input(self.hass, user_input)
            except JunosNetconfAuthError:
                errors["base"] = "invalid_auth"
            except JunosNetconfConnectionError as err:
                _LOGGER.warning("Junos NETCONF connection validation failed: %s", err)
                errors["base"] = "cannot_connect"
            except Exception as err:
                _LOGGER.exception("Unexpected Junos NETCONF config flow error: %s", err)
                errors["base"] = "unknown"
            else:
                await self.async_set_unique_id(unique_id)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=user_input[CONF_HOST],
                    data=user_input,
                )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )

    @staticmethod
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Return the options flow."""
        return JunosNetconfOptionsFlow()


class JunosNetconfOptionsFlow(config_entries.OptionsFlow):
    """Handle Junos NETCONF options."""

    async def async_step_init(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> FlowResult:
        """Manage polling and interface allowlist options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current_interval = self.config_entry.options.get(
            CONF_SCAN_INTERVAL,
            self.config_entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
        )
        current_allowlist = self.config_entry.options.get(
            CONF_INTERFACE_ALLOWLIST,
            self.config_entry.data.get(CONF_INTERFACE_ALLOWLIST, ""),
        )
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_SCAN_INTERVAL,
                        default=current_interval,
                    ): vol.All(vol.Coerce(int), vol.Range(min=MIN_SCAN_INTERVAL)),
                    vol.Optional(
                        CONF_INTERFACE_ALLOWLIST,
                        default=current_allowlist,
                    ): selector.TextSelector(),
                }
            ),
        )
