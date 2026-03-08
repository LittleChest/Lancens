"""Sensor platform for Lancens."""
from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
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
    """Set up the sensor platform."""
    coordinator: LancensDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    
    async_add_entities([LancensLastEventSensor(coordinator)])


class LancensLastEventSensor(CoordinatorEntity, SensorEntity):
    """Representation of a Lancens Last Event Sensor."""

    def __init__(self, coordinator: LancensDataUpdateCoordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.uid}_last_event"
        self._attr_name = "最新事件"
        self._attr_icon = "mdi:history"

    @property
    def native_value(self) -> str | None:
        """Return the state of the sensor."""
        events = self.coordinator.data.get("events", {}).get("resultData", {}).get("eventList", [])
        if events and len(events) > 0:
            # Assume first event is latest
            return events[0].get("event_type", "未知") # Fallback key
        return "无事件"

    @property
    def extra_state_attributes(self) -> dict[str, any]:
        """Return the state attributes."""
        events = self.coordinator.data.get("events", {}).get("resultData", {}).get("eventList", [])
        if events and len(events) > 0:
            event = events[0]
            return {
                "time": event.get("event_time"),
                "user": event.get("user_name"),
                "type": event.get("event_type"),
                "raw_data": event
            }
        return {}
