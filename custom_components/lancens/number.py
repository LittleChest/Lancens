"""Number platform for Lancens."""
from __future__ import annotations

from homeassistant.components.number import NumberEntity
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
    coordinators = hass.data[DOMAIN][entry.entry_id]
    
    entities =[]
    for coord in coordinators.values():
        entities.append(LancensNumber(
            coord, 
            "screenon_timeout", 
            "亮屏时间", 
            "mdi:timer-sand",
            min_value=5,
            max_value=120,
            step=1
        ))
    async_add_entities(entities)


class LancensNumber(CoordinatorEntity, NumberEntity):
    def __init__(
        self,
        coordinator: LancensDataUpdateCoordinator,
        key: str,
        name: str,
        icon: str,
        min_value: float,
        max_value: float,
        step: float,
    ) -> None:
        super().__init__(coordinator)
        self._key = key
        self._attr_unique_id = f"{coordinator.uid}_{key}"
        self._attr_name = f"{coordinator.device_name} {name}"
        self._attr_icon = icon
        self._attr_native_min_value = min_value
        self._attr_native_max_value = max_value
        self._attr_native_step = step

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self.coordinator.uid)},
            "name": self.coordinator.device_name,
            "manufacturer": "叮叮智能",
            "model": "智能门锁"
        }

    @property
    def native_value(self) -> float | None:
        if not self.coordinator.data:
            return None
            
        settings_list = self.coordinator.data.get("settings",[])
        if settings_list and isinstance(settings_list, list) and len(settings_list) > 0:
            return settings_list[0].get(self._key)
        return None

    async def async_set_native_value(self, value: float) -> None:
        try:
            await self.coordinator.client.async_set_screen_settings(self.coordinator.uid, **{self._key: int(value)})
            await self.coordinator.async_request_refresh()
        except Exception as err:
            raise HomeAssistantError(f"Failed to set value: {err}") from err