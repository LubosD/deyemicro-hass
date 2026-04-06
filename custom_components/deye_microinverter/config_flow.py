"""Config flow for Deye Microinverter integration."""

import re

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST, CONF_PORT

from .const import CONF_SERIAL_NUMBER, DOMAIN

SERIAL_NUMBER_PATTERN = re.compile(r"^\d{10}$")
DEFAULT_PORT = 8899


class DeyeMicroinverterConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Deye Microinverter."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            serial = user_input[CONF_SERIAL_NUMBER]

            if not SERIAL_NUMBER_PATTERN.match(serial):
                errors[CONF_SERIAL_NUMBER] = "invalid_serial_number"
            else:
                await self.async_set_unique_id(serial)
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title=f"Deye {serial}",
                    data=user_input,
                )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_HOST): str,
                    vol.Required(CONF_PORT, default=DEFAULT_PORT): vol.Coerce(int),
                    vol.Required(CONF_SERIAL_NUMBER): str,
                }
            ),
            errors=errors,
        )
