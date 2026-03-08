"""Number platform for Lancens."""
from __future__ import annotations

from homeassistant.components.number import NumberEntity
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
    """Set up the number platform."""
    coordinator: LancensDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    
    async_add_entities([
        LancensNumber(
            coordinator, 
            "screenon_timeout", 
            "亮屏时间", 
            "mdi:timer-sand",
            min_value=5,
            max_value=120,
            step=1
        )
    ])


class LancensNumber(CoordinatorEntity, NumberEntity):
    """Lancens number entity."""

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
        """Initialize."""
        super().__init__(coordinator)
        self._key = key
        self._attr_unique_id = f"{coordinator.uid}_{key}"
        self._attr_name = name
        self._attr_icon = icon
        self._attr_native_min_value = min_value
        self._attr_native_max_value = max_value
        self._attr_native_step = step

    @property
    def native_value(self) -> float | None:
        """Return the value."""
        settings_list = self.coordinator.data.get("settings", [])
        if settings_list and isinstance(settings_list, list) and len(settings_list) > 0:
            return settings_list[0].get(self._key)
        return None

    async def async_set_native_value(self, value: float) -> None:
        """Set the value."""
        await self.coordinator.client.async_set_screen_settings(self.coordinator.uid, **{self._key: int(value)})
        await self.coordinator.async_request_refresh()
