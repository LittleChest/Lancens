from homeassistant.components.switch import SwitchEntity
from homeassistant.exceptions import HomeAssistantError
from .const import DOMAIN
from .entity import LancensEntity

async def async_setup_entry(hass, entry, async_add_entities):
    entities = []
    for c in hass.data[DOMAIN][entry.entry_id].values():
        entities.extend([
            LancensSettingSwitch(c, "bat_display_en", "电量显示", "mdi:battery"),
            LancensSettingSwitch(c, "call_screen_on", "呼叫唤醒", "mdi:video"),
            LancensSettingSwitch(c, "standby_mode", "待机模式", "mdi:power-sleep"),
            LancensWxPushSwitch(c)
        ])
    async_add_entities(entities)

class LancensSettingSwitch(LancensEntity, SwitchEntity):
    def __init__(self, coordinator, key, name, icon):
        super().__init__(coordinator)
        self._key = key
        self._attr_unique_id = f"{coordinator.uid}_{key}"
        self._attr_name = f"{coordinator.device_name} {name}"
        self._attr_icon = icon

    @property
    def is_on(self):
        if self.coordinator.data and (settings := self.coordinator.data.get("settings")):
            return bool(settings[0].get(self._key))
        return None

    async def _async_set_state(self, state):
        try:
            if self._key == "bat_display_en":
                await self.coordinator.client.async_set_battery_display(self.coordinator.uid, state)
            else:
                timeout = self.coordinator.data.get("settings", [{}])[0].get("screenon_timeout", 5) if self.coordinator.data else 5
                await self.coordinator.client.async_set_screen_settings(self.coordinator.uid, **{self._key: int(state), "screenon_timeout": timeout})
            await self.coordinator.async_request_refresh()
        except Exception as err:
            raise HomeAssistantError(f"无法修改设置: {err}") from err

    async def async_turn_on(self): await self._async_set_state(True)
    async def async_turn_off(self): await self._async_set_state(False)

class LancensWxPushSwitch(LancensEntity, SwitchEntity):
    def __init__(self, coordinator):
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.uid}_wx_push"
        self._attr_name = f"{coordinator.device_name} 微信推送"
        self._attr_icon = "mdi:wechat"

    @property
    def is_on(self):
        return bool(self.coordinator.data.get("wx_push", {}).get("wx_push")) if self.coordinator.data else None

    async def _async_set_state(self, state):
        try:
            await self.coordinator.client.async_set_wx_push(self.coordinator.uid, state)
            await self.coordinator.async_request_refresh()
        except Exception as err:
            raise HomeAssistantError(f"无法修改设置: {err}") from err

    async def async_turn_on(self): await self._async_set_state(True)
    async def async_turn_off(self): await self._async_set_state(False)