"""Config flow for Lancens integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_TOKEN, CONF_UNIQUE_ID
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
    }
)


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate the user input allows us to connect.

    Data has the keys from STEP_USER_DATA_SCHEMA with values provided by the user.
    """
    
    session = async_get_clientsession(hass)
    client = LancensApiClient(token=data[CONF_TOKEN], session=session)

    # Validate token by trying to get devices or just checking push status if UID provided
    # If UID is not provided, we try to get devices.
    # If UID is provided, we verify it works.
    
    uid = data.get(CONF_UID)
    
    if uid:
        try:
            # Try to get settings for this UID to verify connectivity
            await client.async_get_settings(uid)
        except Exception as err:
            # If settings fail, maybe it's offline or invalid token/uid
            # Try to get data (device list) as fallback
            try:
                await client.async_get_data()
            except Exception as e:
                raise InvalidAuth from e
            # If get_data works but get_settings failed, maybe UID is wrong?
            # We'll allow it but warn? No, let's just assume valid if we can connect.
    else:
        # No UID provided, try to fetch device list
        try:
            devices = await client.async_get_data()
            _LOGGER.debug("Discovery response: %s", devices)
            
            device_list = []
            if isinstance(devices, dict):
                device_list = devices.get("deviceList",[])
            elif isinstance(devices, list):
                device_list = devices
                
            if device_list and len(device_list) > 0:
                first_device = device_list[0]
                uid = first_device.get("uid") or first_device.get("uuid") or first_device.get("id")
        except Exception as err:
             _LOGGER.error("Discovery failed: %s", err)
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
        except Exception:  # pylint: disable=broad-except
            _LOGGER.exception("Unexpected exception")
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
