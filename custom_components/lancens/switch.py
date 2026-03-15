"""Switch platform for Lancens."""
from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from . import LancensDataUpdateCoordinator

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the switch platform."""
    coordinators = hass.data[DOMAIN][entry.entry_id]
    
    entities =[]
    for coord in coordinators.values():
        entities.append(LancensSettingSwitch(coord, "bat_display_en", "电量显示", "mdi:battery"))
        entities.append(LancensSettingSwitch(coord, "call_screen_on", "呼叫唤醒", "mdi:video"))
        entities.append(LancensSettingSwitch(coord, "standby_mode", "待机模式", "mdi:power-sleep"))
        entities.append(LancensWxPushSwitch(coord))
    
    async_add_entities(entities)


class LancensSettingSwitch(CoordinatorEntity, SwitchEntity):
    """Switch for device settings."""

    def __init__(
        self,
        coordinator: LancensDataUpdateCoordinator,
        key: str,
        name: str,
        icon: str,
    ) -> None:
        super().__init__(coordinator)
        self._key = key
        self._attr_unique_id = f"{coordinator.uid}_{key}"
        self._attr_name = f"{coordinator.device_name} {name}"
        self._attr_icon = icon

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self.coordinator.uid)},
            "name": self.coordinator.device_name,
            "manufacturer": "叮叮智能",
            "model": "智能门锁"
        }

    @property
    def is_on(self) -> bool | None:
        if not self.coordinator.data:
            return None
            
        settings_list = self.coordinator.data.get("settings",[])
        if settings_list and isinstance(settings_list, list) and len(settings_list) > 0:
            val = settings_list[0].get(self._key)
            return bool(val)
        return None

    def _get_current_screenon_timeout(self) -> int:
        if self.coordinator.data:
            settings_list = self.coordinator.data.get("settings",[])
            if settings_list and isinstance(settings_list, list) and len(settings_list) > 0:
                return settings_list[0].get("screenon_timeout", 5)
        return 5

    async def async_turn_on(self, **kwargs: Any) -> None:
        try:
            if self._key == "bat_display_en":
                 await self.coordinator.client.async_set_battery_display(self.coordinator.uid, True)
            else:
                 payload = {self._key: 1, "screenon_timeout": self._get_current_screenon_timeout()}
                 await self.coordinator.client.async_set_screen_settings(self.coordinator.uid, **payload)
            await self.coordinator.async_request_refresh()
        except Exception as err:
            raise HomeAssistantError(f"Failed to turn on: {err}") from err

    async def async_turn_off(self, **kwargs: Any) -> None:
        try:
            if self._key == "bat_display_en":
                 await self.coordinator.client.async_set_battery_display(self.coordinator.uid, False)
            else:
                 payload = {self._key: 0, "screenon_timeout": self._get_current_screenon_timeout()}
                 await self.coordinator.client.async_set_screen_settings(self.coordinator.uid, **payload)
            await self.coordinator.async_request_refresh()
        except Exception as err:
            raise HomeAssistantError(f"Failed to turn off: {err}") from err

class LancensWxPushSwitch(CoordinatorEntity, SwitchEntity):
    """Switch for WX Push."""

    def __init__(self, coordinator: LancensDataUpdateCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.uid}_wx_push"
        self._attr_name = f"{coordinator.device_name} 微信推送"
        self._attr_icon = "mdi:wechat"

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self.coordinator.uid)},
            "name": self.coordinator.device_name,
            "manufacturer": "叮叮智能",
            "model": "智能门锁"
        }

    @property
    def is_on(self) -> bool | None:
        if not self.coordinator.data:
            return None
            
        data = self.coordinator.data.get("wx_push")
        if not data or not isinstance(data, dict):
            return None
            
        return bool(data.get("wx_push"))

    async def async_turn_on(self, **kwargs: Any) -> None:
        try:
            await self.coordinator.client.async_set_wx_push(self.coordinator.uid, True)
            await self.coordinator.async_request_refresh()
        except Exception as err:
            raise HomeAssistantError(f"Failed to turn on: {err}") from err

    async def async_turn_off(self, **kwargs: Any) -> None:
        try:
            await self.coordinator.client.async_set_wx_push(self.coordinator.uid, False)
            await self.coordinator.async_request_refresh()
        except Exception as err:
            raise HomeAssistantError(f"Failed to turn off: {err}") from err