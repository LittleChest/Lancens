import asyncio
import base64
import json
import time
import logging
from homeassistant.components.lock import LockEntity
from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError
from .const import DOMAIN
from .entity import LancensEntity

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, entry, async_add_entities):
    auth_pass = entry.data.get("auth_pass")
    async_add_entities([LancensLock(c, auth_pass) for c in hass.data[DOMAIN][entry.entry_id].values()])

class LancensLock(LancensEntity, LockEntity):
    def __init__(self, coordinator, auth_pass):
        super().__init__(coordinator)
        self._auth_pass = auth_pass
        self._attr_unique_id = f"{coordinator.uid}_lock"
        self._attr_name = f"{coordinator.device_name} 开关"
        self._lock_state = "locked"
        self._last_event_id = None
        self._active_seq = None
        self._state_task = None
        self._wait_task = None

    @property
    def is_locked(self): return self._lock_state == "locked"
    @property
    def is_unlocking(self): return self._lock_state == "unlocking"
    @property
    def is_locking(self): return self._lock_state == "locking"
    @property
    def is_jammed(self): return self._lock_state == "jammed"

    @callback
    def _handle_coordinator_update(self):
        super()._handle_coordinator_update()
        self._check_latest_event()

    def _check_latest_event(self):
        if not (event := self._latest_event) or not (event_id := event.get("id")): return
        if self._last_event_id == event_id: return
        
        is_initial = self._last_event_id is None
        self._last_event_id = event_id
        if is_initial: return
        
        if str(event.get("type")) == "6" and (info_raw := event.get("info")):
            try:
                info_raw += "=" * ((4 - len(info_raw) % 4) % 4)
                info_json = json.loads(base64.b64decode(info_raw).decode("utf-8"))
                if info_json.get("event_device") == "LOCK_PUSH" and self._active_seq != "remote_unlock":
                    code = info_json.get("event_type")
                    self._trigger_state_sequence("event_unlock" if code == "15" else "locking" if code == "14" else "jammed")
            except Exception:
                pass

    def _trigger_state_sequence(self, seq_type):
        if self._state_task: self._state_task.cancel()
        self._state_task = self.hass.async_create_task(self._async_state_sequence(seq_type))

    async def _async_state_sequence(self, seq_type):
        try:
            self._active_seq = seq_type
            states = []
            if seq_type == "remote_unlock": states =[("unlocking", 1), ("unlocked", 2), ("locking", 1), ("locked", 0)]
            elif seq_type == "event_unlock": states =[("unlocking", 1), ("locked", 0)]
            elif seq_type == "locking": states =[("locking", 1), ("locked", 0)]
            elif seq_type == "jammed": states =[("jammed", 20), ("locked", 0)]
            
            for state, delay in states:
                self._lock_state = state
                self.async_write_ha_state()
                if delay > 0: await asyncio.sleep(delay)
        except asyncio.CancelledError:
            pass
        finally:
            if self._active_seq == seq_type:
                self._active_seq = None

    async def async_lock(self):
        for task in (self._state_task, self._wait_task):
            if task: task.cancel()
        self._lock_state, self._active_seq = "locked", None
        self.async_write_ha_state()

    async def async_unlock(self):
        if not self._auth_pass: raise HomeAssistantError("尚未配置安全密码。")
        if time.time() > self.coordinator.doorbell_window_end: raise HomeAssistantError("请重新按下门铃按钮。")

        for task in (self._state_task, self._wait_task):
            if task: task.cancel()
        
        self._lock_state, self._active_seq = "unlocking", "wait_unlock"
        self.async_write_ha_state()
        self._wait_task = self.hass.async_create_task(self._async_wait_and_unlock())

    async def _async_wait_and_unlock(self):
        try:
            success = False
            while time.time() < self.coordinator.doorbell_window_end:
                if (push := self.coordinator.latest_push_data) and time.time() - push.get("received_time", 0) <= 60:
                    if push.get("event_guid") and push.get("reflash_token"):
                        success = await self.coordinator.client.async_unlock(
                            self.coordinator.uid, push["event_guid"], push.get("user_id"),
                            push["reflash_token"], self._auth_pass
                        )
                        self.coordinator.latest_push_data = {}
                        if success:
                            self.coordinator.close_doorbell_window()
                            break
                else:
                    self.coordinator.latest_push_data = {}
                await asyncio.sleep(1)

            if success:
                self._trigger_state_sequence("remote_unlock")
                await self.coordinator.async_request_refresh()
            else:
                self.hass.components.persistent_notification.async_create(
                    "未能获取解锁凭据或密码错误。", title=f"{self._attr_name} 开锁失败", notification_id=f"{self.unique_id}_failed"
                )
                await self.async_lock()
        except asyncio.CancelledError:
            pass
        except Exception as e:
            _LOGGER.error("无法获取解锁凭据: %s", e)
            await self.async_lock()