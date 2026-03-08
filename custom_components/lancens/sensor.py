"""Sensor platform for Lancens."""
from __future__ import annotations

import base64
import json
import logging

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from . import LancensDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

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
        if not self.coordinator.data:
            return "未知"
            
        events = self.coordinator.data.get("events")
        if not events or not isinstance(events, dict):
            return "未知"
            
        event_list = events.get("resultData", {}).get("eventList", [])
        if event_list and len(event_list) > 0:
            event = event_list[0]

            info_raw = event.get("info")
            if info_raw:
                try:
                    decoded_str = base64.b64decode(info_raw).decode("utf-8")
                    info_json = json.loads(decoded_str)

                    device_type = info_json.get("event_device")
                    event_type = info_json.get("event_type")

                    if device_type == "LOCK_PUSH":
                        return "门锁推送"
                    if event_type:
                        return f"事件代码 {event_type}"
                        
                except Exception as e:
                    _LOGGER.warning("Failed to decode event info: %s", e)

            return f"Type {event.get('type', 'Unknown')}"
            
        return "无事件"

    @property
    def extra_state_attributes(self) -> dict[str, any]:
        """Return the state attributes."""
        if not self.coordinator.data:
            return {}

        events = self.coordinator.data.get("events")
        if not events or not isinstance(events, dict):
            return {}

        event_list = events.get("resultData", {}).get("eventList", [])
        if event_list and len(event_list) > 0:
            event = event_list[0]
            attrs = {
                "time": event.get("time"),
                "type_code": event.get("type"),
                "event_guid": event.get("event_guid")
            }

            info_raw = event.get("info")
            if info_raw:
                try:
                    decoded_str = base64.b64decode(info_raw).decode("utf-8")
                    attrs["decoded_info"] = json.loads(decoded_str)
                except:
                    pass
            
            return attrs
        return {}
