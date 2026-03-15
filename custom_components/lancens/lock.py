"""Lock platform for Lancens."""
from __future__ import annotations

import asyncio
import base64
import json
import logging
from typing import Any

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
    """Set up the lock platform."""
    coordinators = hass.data[DOMAIN][entry.entry_id]
    auth_pass = entry.data.get("auth_pass")
    
    entities =[LancensLock(coord, auth_pass) for coord in coordinators.values()]
    async_add_entities(entities)


class LancensLock(CoordinatorEntity, LockEntity):
    """Lancens Lock Entity."""

    def __init__(self, coordinator: LancensDataUpdateCoordinator, auth_pass: str | None) -> None:
        """Initialize the lock."""
        super().__init__(coordinator)
        self._auth_pass = auth_pass
        self._attr_unique_id = f"{coordinator.uid}_lock"
        self._attr_name = f"{coordinator.device_name} 开关"
        
        self._lock_state = "locked"  
        self._last_event_id = None
        self._state_task: asyncio.Task | None = None

    @property
    def device_info(self):
        """Return device information about this entity."""
        return {
            "identifiers": {(DOMAIN, self.coordinator.uid)},
            "name": self.coordinator.device_name,
            "manufacturer": "叮叮智能",
            "model": "智能门锁"
        }

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
            if seq_type == "event_unlock":
                # 轮询获取到别人开锁：正在打开1秒 已打开3秒 正在确定(锁定)1秒
                self._lock_state = "unlocking"
                self.async_write_ha_state()
                await asyncio.sleep(1)
                
                self._lock_state = "unlocked"
                self.async_write_ha_state()
                await asyncio.sleep(3)
                
                self._lock_state = "locking"
                self.async_write_ha_state()
                await asyncio.sleep(1)
                
                self._lock_state = "locked"
                self.async_write_ha_state()

            elif seq_type == "remote_unlock":
                # 远程开锁成功：正在解锁1秒 已解锁2秒 正在锁定1秒
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
                
            elif seq_type == "jammed":
                # 冻结：视为卡住 20秒
                self._lock_state = "jammed"
                self.async_write_ha_state()
                await asyncio.sleep(20)
                
                self._lock_state = "locked"
                self.async_write_ha_state()
                
            elif seq_type == "locking":
                # 轮询到已关锁：正在锁定 2.5 秒
                self._lock_state = "locking"
                self.async_write_ha_state()
                await asyncio.sleep(2.5)
                
                self._lock_state = "locked"
                self.async_write_ha_state()
                
        except asyncio.CancelledError:
            pass

    async def async_lock(self, **kwargs: Any) -> None:
        if self._state_task:
            self._state_task.cancel()
        self._lock_state = "locked"
        self.async_write_ha_state()

    async def async_unlock(self, **kwargs: Any) -> None:
        _LOGGER.info("====== 收到 HA 前端开锁请求 ======")
        if not self._auth_pass:
            _LOGGER.error("开锁中止：未在配置流中填写 auth_pass")
            raise HomeAssistantError("未配置安全密码 (auth_pass)，无法执行远程开锁。请重新配置集成输入密码。")

        push_data = self.coordinator.latest_push_data
        _LOGGER.info("当前长轮询抓取到的凭证: %s", push_data)

        if not push_data:
            _LOGGER.error("开锁中止：未能读取到任何轮询凭证。可能尚未在门上按铃。")
            raise HomeAssistantError("由于尚未收到访客的门铃呼叫推送，此时无法获取有效的安全开锁凭证。请在门锁上先发起呼叫！")

        event_guid = push_data.get("event_guid")
        user_id = push_data.get("user_id")
        reflash_token = push_data.get("reflash_token")

        if not all([event_guid, user_id, reflash_token]):
            _LOGGER.error("开锁中止：轮询凭证数据缺失。guid=%s, uid=%s, token=%s", event_guid, user_id, reflash_token)
            raise HomeAssistantError("长连接收到的推送数据不完整，无法发起开锁。")

        _LOGGER.info("即将向服务器提交验证参数...")
        success = await self.coordinator.client.async_unlock(
            uid=self.coordinator.uid,
            event_guid=event_guid,
            user_id=user_id,
            reflash_token=reflash_token,
            auth_pass=self._auth_pass
        )

        if not success:
            _LOGGER.error("服务器返回了非预期的结果，开锁失败。")
            raise HomeAssistantError("开锁请求失败，请检查控制台日志确认错误原因（可能是签名失效或密码错误）。")
        else:
            _LOGGER.info("服务器返回200！开锁指令下发成功，触发前端动画！")
            self._trigger_state_sequence("remote_unlock")
            await self.coordinator.async_request_refresh()