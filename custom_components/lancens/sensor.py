import base64
import json
from homeassistant.components.sensor import SensorEntity
from .const import DOMAIN
from .entity import LancensEntity

EVENT_TYPE_MAP = {"02": "指纹", "03": "密码", "04": "卡片", "14": "已关锁", "15": "开锁成功", "17": "人脸或掌静脉"}
UNLOCK_METHOD_MAP = {"00": "指纹", "01": "密码", "02": "卡片", "06": "掌静脉", "08": "人脸", "09": "远程"}

async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([LancensLastEventSensor(c) for c in hass.data[DOMAIN][entry.entry_id].values()])

class LancensLastEventSensor(LancensEntity, SensorEntity):
    def __init__(self, coordinator):
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.uid}_last_event"
        self._attr_name = f"{coordinator.device_name} 最新事件"
        self._attr_icon = "mdi:history"

    @property
    def native_value(self):
        if not (event := self._latest_event):
            return "未知" if not self.coordinator.data else "无事件"
        
        event_type_id = str(event.get("type"))
        if event_type_id == "1":
            return "门铃呼叫"
            
        if info_raw := event.get("info"):
            try:
                info_raw += "=" * ((4 - len(info_raw) % 4) % 4)
                info_json = json.loads(base64.b64decode(info_raw).decode("utf-8"))
                if event_type_id == "6" and info_json.get("event_device") == "LOCK_PUSH":
                    event_code = info_json.get("event_type")
                    if event_code == "15":
                        method = UNLOCK_METHOD_MAP.get(info_json.get("content"), f"未知({info_json.get('content')})")
                        uid = info_json.get("user_id")
                        return f"{method}开锁{f' (用户{uid})' if uid and uid != '0' else ''}"
                    if event_code == "14":
                        return "已关锁"
                    return f"门锁已冻结 - {EVENT_TYPE_MAP.get(event_code, f'代码 {event_code}')}"
            except Exception:
                pass
        return f"Type {event.get('type', 'Unknown')}"

    @property
    def extra_state_attributes(self):
        if not (event := self._latest_event):
            return {}
        attrs = {"time": event.get("time"), "type_code": event.get("type"), "event_guid": event.get("event_guid")}
        if info_raw := event.get("info"):
            try:
                info_raw += "=" * ((4 - len(info_raw) % 4) % 4)
                attrs["decoded_info"] = json.loads(base64.b64decode(info_raw).decode("utf-8"))
            except Exception:
                pass
        return attrs
