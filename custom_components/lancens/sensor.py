"""Sensor platform for Lancens."""
from __future__ import annotations

import base64
import json
import logging

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from . import LancensDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

EVENT_TYPE_MAP = {
    "02": "指纹解锁冻结",
    "03": "密码解锁冻结",
    "14": "已关锁",
    "15": "开锁成功", 
    "17": "人脸解锁冻结",
}

UNLOCK_METHOD_MAP = {
    "00": "指纹",
    "08": "人脸",
    "09": "远程"
}

def parse_lancens_event(event: dict) -> tuple[str, str | None]:
    """Helper to parse event text and image URL."""
    event_type_id = str(event.get("type"))
    event_text = f"Type {event_type_id}"
    
    if event_type_id == "1":
        event_text = "门铃呼叫"
    else:
        info_raw = event.get("info")
        if info_raw:
            try:
                info_raw += "=" * ((4 - len(info_raw) % 4) % 4)
                decoded_str = base64.b64decode(info_raw).decode("utf-8")
                info_json = json.loads(decoded_str)

                if event_type_id == "6":
                    device_type = info_json.get("event_device")
                    event_code = info_json.get("event_type")
                    content_code = info_json.get("content")
                    
                    if device_type == "LOCK_PUSH":
                        if event_code == "15":
                            method = UNLOCK_METHOD_MAP.get(content_code, f"未知方式({content_code})")
                            user_id = info_json.get("user_id")
                            user_str = f" (用户{user_id})" if user_id and user_id != "0" else ""
                            event_text = f"{method}开锁{user_str}"
                        elif event_code in EVENT_TYPE_MAP:
                            event_text = EVENT_TYPE_MAP[event_code]
                        elif event_code:
                            event_text = f"门锁推送 - 代码 {event_code}"
                        else:
                            event_text = "门锁推送"
            except Exception:
                pass
                
    img_url = None
    raw_url = event.get("img") or event.get("file_path") or event.get("url")
    if raw_url and str(raw_url).strip() != "":
        if raw_url.startswith("http"):
            img_url = raw_url
        else:
            try:
                raw_url += "=" * ((4 - len(raw_url) % 4) % 4)
                img_url = base64.b64decode(raw_url).decode("utf-8")
            except:
                img_url = raw_url
                
    return event_text, img_url


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
        self._last_event_id = None

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data and fire Home Assistant events."""
        events = self.coordinator.data.get("events", {}).get("resultData", {}).get("eventList",[])
        if events and len(events) > 0:
            latest_event = events[0]
            current_id = latest_event.get("id")
            
            # 检测到新的事件，抛出到 HA 总线，可供自动化使用
            if self._last_event_id is not None and current_id != self._last_event_id:
                for ev in events:
                    if ev.get("id") == self._last_event_id:
                        break
                    
                    event_text, img_url = parse_lancens_event(ev)
                    
                    self.hass.bus.async_fire("lancens_door_event", {
                        "device_uid": self.coordinator.uid,
                        "event_id": ev.get("id"),
                        "event_time": ev.get("time"),
                        "event_text": event_text,
                        "image_url": img_url,
                    })

            self._last_event_id = current_id

        super()._handle_coordinator_update()

    @property
    def native_value(self) -> str | None:
        """Return the state of the sensor."""
        if not self.coordinator.data:
            return "未知"
            
        events = self.coordinator.data.get("events", {}).get("resultData", {}).get("eventList",[])
        if events and len(events) > 0:
            event_text, _ = parse_lancens_event(events[0])
            return event_text
            
        return "无事件"

    @property
    def extra_state_attributes(self) -> dict[str, any]:
        """Return the state attributes."""
        if not self.coordinator.data:
            return {}

        events = self.coordinator.data.get("events", {}).get("resultData", {}).get("eventList",[])
        attrs = {}
        
        if events and len(events) > 0:
            # 存入最新的基本信息
            event_text, img_url = parse_lancens_event(events[0])
            attrs["time"] = events[0].get("time")
            attrs["image_url"] = img_url
            
            # 生成包含动作和图片的“历史记录表”，支持前端直接展示
            history = []
            for ev in events[:20]: # 提取最多最近20条
                text, img = parse_lancens_event(ev)
                history.append({
                    "time": ev.get("time"),
                    "event": text,
                    "image_url": img
                })
            attrs["history"] = history

        return attrs