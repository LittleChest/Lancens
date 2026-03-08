"""Switch platform for Lancens."""
from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
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
    coordinator: LancensDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    
    entities = []
    
    # Settings from 'settings' endpoint (list of dicts)
    # [{"screenon_timeout":5,"time_zone":"480","bat_display_en":0,"call_screen_on":1,"standby_mode":1}]
    # We assume first item.
    
    entities.append(LancensSettingSwitch(coordinator, "bat_display_en", "电量显示", "mdi:battery"))
    entities.append(LancensSettingSwitch(coordinator, "call_screen_on", "呼叫唤醒", "mdi:video"))
    entities.append(LancensSettingSwitch(coordinator, "standby_mode", "待机模式", "mdi:power-sleep"))
    
    # WX Push
    entities.append(LancensWxPushSwitch(coordinator))
    
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
        """Initialize the switch."""
        super().__init__(coordinator)
        self._key = key
        self._attr_unique_id = f"{coordinator.uid}_{key}"
        self._attr_name = name
        self._attr_icon = icon

    @property
    def is_on(self) -> bool | None:
        """Return true if switch is on."""
        settings_list = self.coordinator.data.get("settings", [])
        if settings_list and isinstance(settings_list, list) and len(settings_list) > 0:
            val = settings_list[0].get(self._key)
            return bool(val)
        return None

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on."""
        if self._key == "bat_display_en":
             await self.coordinator.client.async_set_battery_display(self.coordinator.uid, True)
        else:
             await self.coordinator.client.async_set_screen_settings(self.coordinator.uid, **{self._key: 1})
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off."""
        if self._key == "bat_display_en":
             await self.coordinator.client.async_set_battery_display(self.coordinator.uid, False)
        else:
             await self.coordinator.client.async_set_screen_settings(self.coordinator.uid, **{self._key: 0})
        await self.coordinator.async_request_refresh()

class LancensWxPushSwitch(CoordinatorEntity, SwitchEntity):
    """Switch for WX Push."""

    def __init__(self, coordinator: LancensDataUpdateCoordinator) -> None:
        """Initialize."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.uid}_wx_push"
        self._attr_name = "微信推送"
        self._attr_icon = "mdi:wechat"

    @property
    def is_on(self) -> bool | None:
        """Return true if on."""
        # {"wx_push":1,"wet_play":-1}
        data = self.coordinator.data.get("wx_push", {})
        return bool(data.get("wx_push"))

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on."""
        await self.coordinator.client.async_set_wx_push(self.coordinator.uid, True)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off."""
        await self.coordinator.client.async_set_wx_push(self.coordinator.uid, False)
        await self.coordinator.async_request_refresh()
