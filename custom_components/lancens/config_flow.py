"""Config flow for Lancens integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_TOKEN
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import LancensApiClient
from .const import DOMAIN, CONF_UID

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_TOKEN): str,
        vol.Optional(CONF_UID): str,
        vol.Optional("auth_pass"): str,
    }
)

async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate the user input allows us to connect."""
    session = async_get_clientsession(hass)
    client = LancensApiClient(token=data[CONF_TOKEN], session=session)

    uid = data.get(CONF_UID)
    if uid:
        try:
            await client.async_get_settings(uid)
        except Exception:
            try:
                await client.async_get_data()
            except Exception as e:
                raise InvalidAuth from e
    else:
        try:
            devices = await client.async_get_data()
            device_list = devices.get("deviceList",[]) if isinstance(devices, dict) else (devices if isinstance(devices, list) else[])
            if device_list and len(device_list) > 0:
                first_device = device_list[0]
                uid = first_device.get("uid") or first_device.get("uuid") or first_device.get("id")
        except Exception as err:
             raise InvalidAuth from err

    return {"title": f"叮叮智能 {uid if uid else ''}".strip()}


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Lancens."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        if user_input is None:
            return self.async_show_form(
                step_id="user", data_schema=STEP_USER_DATA_SCHEMA
            )

        errors = {}
        try:
            info = await validate_input(self.hass, user_input)
        except CannotConnect:
            errors["base"] = "cannot_connect"
        except InvalidAuth:
            errors["base"] = "invalid_auth"
        except Exception:
            errors["base"] = "unknown"
        else:
            return self.async_create_entry(title=info["title"], data=user_input)

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )

class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""

class InvalidAuth(HomeAssistantError):
    """Error to indicate there is invalid auth."""