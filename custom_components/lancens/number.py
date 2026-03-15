from homeassistant.components.number import NumberEntity
from homeassistant.exceptions import HomeAssistantError
from .const import DOMAIN
from .entity import LancensEntity

async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([
        LancensNumber(c, "screenon_timeout", "亮屏时间", "mdi:timer-sand", 5, 60, 1)
        for c in hass.data[DOMAIN][entry.entry_id].values()
    ])

class LancensNumber(LancensEntity, NumberEntity):
    def __init__(self, coordinator, key, name, icon, min_val, max_val, step):
        super().__init__(coordinator)
        self._key = key
        self._attr_unique_id = f"{coordinator.uid}_{key}"
        self._attr_name = f"{coordinator.device_name} {name}"
        self._attr_icon = icon
        self._attr_native_min_value = min_val
        self._attr_native_max_value = max_val
        self._attr_native_step = step

    @property
    def native_value(self):
        if self.coordinator.data and (settings := self.coordinator.data.get("settings")):
            return settings[0].get(self._key)
        return None

    async def async_set_native_value(self, value):
        try:
            await self.coordinator.client.async_set_screen_settings(self.coordinator.uid, **{self._key: int(value)})
            await self.coordinator.async_request_refresh()
        except Exception as err:
            raise HomeAssistantError(f"无法修改设置: {err}") from err