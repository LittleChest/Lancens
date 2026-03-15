"""Lock platform for Lancens."""
from __future__ import annotations

import asyncio
import base64
import json
import time
import logging

from homeassistant.components.lock import LockEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
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
    coordinators = hass.data[DOMAIN][entry.entry_id]
    auth_pass = entry.data.get("auth_pass")
    
    entities =[LancensLock(coord, auth_pass) for coord in coordinators.values()]
    async_add_entities(entities)


class LancensLock(CoordinatorEntity, LockEntity):
    def __init__(self, coordinator: LancensDataUpdateCoordinator, auth_pass: str | None) -> None:
        super().__init__(coordinator)
        self._auth_pass = auth_pass
        self._attr_unique_id = f"{coordinator.uid}_lock"
        self._attr_name = f"{coordinator.device_name} 开关"
        
        self._lock_state = "locked"  
        self._last_event_id = None
        self._active_seq = None
        
        self._state_task: asyncio.Task | None = None
        self._wait_task: asyncio.Task | None = None

    @property
    def device_info(self):
        info = {
            "identifiers": {(DOMAIN, self.coordinator.uid)},
            "name": self.coordinator.device_name,
            "manufacturer": "深圳市揽胜科技有限公司",
            "model": self.coordinator.uid
        }
        if self.coordinator.sw_version:
            info["sw_version"] = self.coordinator.sw_version
        return info

    @property
    def is_locked(self) -> bool:
        return self._lock_state == "locked"

    @property
    def is_unlocking(self) -> bool:
        return self._lock_state == "unlocking"

    @property
    def is_locking(self) -> bool:
        return self._lock_state == "locking"

    @property
    def is_jammed(self) -> bool:
        return self._lock_state == "jammed"

    @callback
    def _handle_coordinator_update(self) -> None:
        super()._handle_coordinator_update()
        self._check_latest_event()

    def _check_latest_event(self):
        if not self.coordinator.data:
            return

        events = self.coordinator.data.get("events")
        if not events or not isinstance(events, dict):
            return
            
        event_list = events.get("resultData", {}).get("eventList",[])
        if not event_list:
            return
            
        latest_event = event_list[0]
        event_id = latest_event.get("id")
        
        if not event_id:
            return

        if self._last_event_id is None:
            self._last_event_id = event_id
            return
            
        if self._last_event_id == event_id:
            return  
            
        self._last_event_id = event_id
        
        event_type_id = str(latest_event.get("type"))
        if event_type_id == "6":
            info_raw = latest_event.get("info")
            if info_raw:
                try:
                    info_raw += "=" * ((4 - len(info_raw) % 4) % 4)
                    decoded_str = base64.b64decode(info_raw).decode("utf-8")
                    info_json = json.loads(decoded_str)
                    
                    device_type = info_json.get("event_device")
                    event_code = info_json.get("event_type")
                    
                    if device_type == "LOCK_PUSH":
                        if self._active_seq == "remote_unlock":
                            return
                            
                        if event_code == "15":
                            self._trigger_state_sequence("event_unlock")
                        elif event_code == "14":
                            self._trigger_state_sequence("locking")
                        else:
                            self._trigger_state_sequence("jammed")
                except Exception:
                    pass

    def _trigger_state_sequence(self, seq_type: str):
        if self._state_task:
            self._state_task.cancel()
        self._state_task = self.hass.async_create_task(self._async_state_sequence(seq_type))

    async def _async_state_sequence(self, seq_type: str):
        try:
            self._active_seq = seq_type
            
            if seq_type == "remote_unlock":
                # 远程开锁：正在解锁1s -> 已解锁2s -> 正在锁定1s -> 已锁定
                self._lock_state = "unlocking"
                self.async_write_ha_state()
                await asyncio.sleep(1)
                
                self._lock_state = "unlocked"
                self.async_write_ha_state()
                await asyncio.sleep(2)
                
                self._lock_state = "locking"
                self.async_write_ha_state()
                await asyncio.sleep(1)
                
                self._lock_state = "locked"
                self.async_write_ha_state()
                
            elif seq_type == "event_unlock":
                # 其他方式开锁事件：正在解锁1s -> 已锁定
                self._lock_state = "unlocking"
                self.async_write_ha_state()
                await asyncio.sleep(1)
                
                self._lock_state = "locked"
                self.async_write_ha_state()
                
            elif seq_type == "locking":
                # 关门事件：正在锁定1s -> 已锁定
                self._lock_state = "locking"
                self.async_write_ha_state()
                await asyncio.sleep(1)
                
                self._lock_state = "locked"
                self.async_write_ha_state()

            elif seq_type == "jammed":
                self._lock_state = "jammed"
                self.async_write_ha_state()
                # 冻结事件：卡住20s -> 已锁定
                await asyncio.sleep(20)
                
                self._lock_state = "locked"
                self.async_write_ha_state()
                
        except asyncio.CancelledError:
            pass
        finally:
            if self._active_seq == seq_type:
                self._active_seq = None

    async def async_lock(self) -> None:
        if self._state_task:
            self._state_task.cancel()
        if self._wait_task:
            self._wait_task.cancel()
            
        self._lock_state = "locked"
        self._active_seq = None
        self.async_write_ha_state()

    async def async_unlock(self) -> None:
        if not self._auth_pass:
            raise HomeAssistantError("尚未配置安全密码。")

        if time.time() > self.coordinator.doorbell_window_end:
            raise HomeAssistantError("请重新按下门铃按钮。")

        if self._wait_task:
            self._wait_task.cancel()
        if self._state_task:
            self._state_task.cancel()
        
        self._lock_state = "unlocking"
        self._active_seq = "wait_unlock"
        self.async_write_ha_state()

        self._wait_task = self.hass.async_create_task(self._async_wait_and_unlock())

    async def _async_wait_and_unlock(self):
        try:
            success = False
            while time.time() < self.coordinator.doorbell_window_end:
                push_data = self.coordinator.latest_push_data
                
                if push_data and "reflash_token" in push_data:
                    received_time = push_data.get("received_time", 0)
                    
                    if time.time() - received_time <= 60:
                        event_guid = push_data.get("event_guid")
                        user_id = push_data.get("user_id")
                        reflash_token = push_data.get("reflash_token")
                        
                        if event_guid and reflash_token:
                            success = await self.coordinator.client.async_unlock(
                                uid=self.coordinator.uid,
                                event_guid=event_guid,
                                user_id=user_id,
                                reflash_token=reflash_token,
                                auth_pass=self._auth_pass
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
                    "未能获取解锁凭据或密码错误。",
                    title=f"{self._attr_name} 开锁失败",
                    notification_id=f"{self.unique_id}_unlock_failed"
                )
                self._lock_state = "locked"
                self._active_seq = None
                self.async_write_ha_state()

        except asyncio.CancelledError:
            pass
        except Exception as e:
            _LOGGER.error("无法拉取解锁凭据: %s", e)
            self._lock_state = "locked"
            self._active_seq = None
            self.async_write_ha_state()