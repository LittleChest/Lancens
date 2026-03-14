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

# 根据真实抓包数据和时间线推导出的精确事件映射字典
EVENT_TYPE_MAP = {
    "02": "指纹解锁冻结",
    "03": "密码解锁冻结",
    "14": "已关锁",
    "15": "开锁成功",  # 具体方式由 content 决定
    "17": "人脸解锁冻结",
}

# 开锁方式映射 (当 event_type == "15" 时生效)
UNLOCK_METHOD_MAP = {
    "00": "指纹",
    "08": "人脸",
    "09": "远程"
}

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
            
        event_list = events.get("resultData", {}).get("eventList",[])
        if event_list and len(event_list) > 0:
            event = event_list[0]
            event_type_id = str(event.get("type"))
            
            # Type 1 永远是门铃呼叫
            if event_type_id == "1":
                return "门铃呼叫"
                
            info_raw = event.get("info")
            if info_raw:
                try:
                    # 补齐 Base64 填充并解码
                    info_raw += "=" * ((4 - len(info_raw) % 4) % 4)
                    decoded_str = base64.b64decode(info_raw).decode("utf-8")
                    info_json = json.loads(decoded_str)

                    # Type 6 是门锁状态推送
                    if event_type_id == "6":
                        device_type = info_json.get("event_device")
                        event_code = info_json.get("event_type")
                        content_code = info_json.get("content")
                        
                        if device_type == "LOCK_PUSH":
                            # 解析开锁动作 (15)
                            if event_code == "15":
                                method = UNLOCK_METHOD_MAP.get(content_code, f"未知方式({content_code})")
                                user_id = info_json.get("user_id")
                                user_str = f" (用户{user_id})" if user_id and user_id != "0" else ""
                                return f"{method}开锁{user_str}"
                            
                            # 解析其他已知动作 (冻结、关锁等)
                            elif event_code in EVENT_TYPE_MAP:
                                return EVENT_TYPE_MAP[event_code]

                            elif event_code:
                                return f"门锁推送 - 未知代码 {event_code}"
                            
                            return "门锁推送"
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

        event_list = events.get("resultData", {}).get("eventList",[])
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
                    info_raw += "=" * ((4 - len(info_raw) % 4) % 4)
                    decoded_str = base64.b64decode(info_raw).decode("utf-8")
                    attrs["decoded_info"] = json.loads(decoded_str)
                except:
                    pass
            
            return attrs
        return {}