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
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_TOKEN): str,
        vol.Optional("auth_pass"): str,
    }
)

async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    session = async_get_clientsession(hass)
    client = LancensApiClient(token=data[CONF_TOKEN], session=session)

    try:
        devices = await client.async_get_data()
        device_list = devices.get("deviceList",[]) if isinstance(devices, dict) else (devices if isinstance(devices, list) else[])
        if not device_list or len(device_list) == 0:
            raise InvalidAuth("账号下未找到任何绑定的设备")
    except Exception as err:
        raise InvalidAuth from err

    return {"title": f"叮叮智能 (发现 {len(device_list)} 个设备)"}


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
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
            await self.async_set_unique_id(user_input[CONF_TOKEN][:8])
            self._abort_if_unique_id_configured()
            return self.async_create_entry(title=info["title"], data=user_input)

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )

class CannotConnect(HomeAssistantError):
    pass

class InvalidAuth(HomeAssistantError):
    pass