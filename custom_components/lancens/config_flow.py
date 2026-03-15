import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_TOKEN
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from .api import LancensApiClient
from .const import DOMAIN, DEFAULT_NAME

class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            try:
                devices = await LancensApiClient(user_input[CONF_TOKEN], async_get_clientsession(self.hass)).async_get_data()
                
                if not devices.get("deviceList",[]) if isinstance(devices, dict) else (devices if isinstance(devices, list) else []):
                    errors["base"] = "未绑定任何设备"
                else:
                    await self.async_set_unique_id(user_input[CONF_TOKEN][:8])
                    self._abort_if_unique_id_configured()
                    return self.async_create_entry(title=DEFAULT_NAME, data=user_input)
            
            except Exception:
                errors["base"] = "令牌无效或无法连接至服务器"

        return self.async_show_form(
            step_id="user", 
            data_schema=vol.Schema({
                vol.Required(CONF_TOKEN): str, 
                vol.Optional("auth_pass"): str
            }), 
            errors=errors
        )