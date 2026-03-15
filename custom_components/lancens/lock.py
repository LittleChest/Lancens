"""Lock platform for Lancens."""
from __future__ import annotations

import asyncio
import base64
import json
import time
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
    coordinators = hass.data[DOMAIN][entry.entry_id]
    auth_pass = entry.data.get("auth_pass")
    
    entities =[LancensLock(coord, auth_pass) for coord in coordinators.values()]
    async_add_entities(entities)


class LancensLock(CoordinatorEntity, LockEntity):
    """Lancens Lock Entity."""

    def __init__(self, coordinator: LancensDataUpdateCoordinator, auth_pass: str | None) -> None:
        super().__init__(coordinator)
        self._auth_pass = auth_pass
        self._attr_unique_id = f"{coordinator.uid}_lock"
        self._attr_name = f"{coordinator.device_name} 开关"
        
        self._lock_state = "locked"  
        self._last_event_id = None
        self._state_task: asyncio.Task | None = None

    @property
    def device_info(self):
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
                            self._trigger_state_sequence("unlock_success")
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
            if seq_type == "unlock_success":
                # 获取到成功开门：正在打开1秒 已打开2秒 正在锁定1秒
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
                # 被冻结：卡住 20 秒
                self._lock_state = "jammed"
                self.async_write_ha_state()
                await asyncio.sleep(20)
                
                self._lock_state = "locked"
                self.async_write_ha_state()
                
            elif seq_type == "locking":
                # 收到已锁定：正在锁定 2.5 秒
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
        """从前端发起远程开锁命令"""
        if not self._auth_pass:
            raise HomeAssistantError("未配置安全密码 (auth_pass)，无法执行远程开锁。请重新配置集成。")

        # 判断窗口期是否过期或根本没触发
        if time.time() > self.coordinator.doorbell_window_end:
            _LOGGER.error("拒绝开锁：没有收到门铃呼叫或窗口期已超时！")
            raise HomeAssistantError("拒绝开锁：未收到门铃呼叫，或 60 秒安全窗口已超时失效。")

        _LOGGER.info("====== 允许下发，进入 60 秒凭证轮询等待队列 ======")

        # 中断可能正在运行的其它动画协程
        if self._state_task:
            self._state_task.cancel()
        
        # 立即将 UI 置为解锁中并维持
        self._lock_state = "unlocking"
        self.async_write_ha_state()

        # 启动后台轮询执行任务，立即返回让前端顺畅显示动画
        self._state_task = self.hass.async_create_task(self._async_wait_and_unlock())

    async def _async_wait_and_unlock(self):
        """后台窗口期轮询拦截"""
        try:
            success = False
            # 持续轮询直至超过窗口期截止时间
            while time.time() < self.coordinator.doorbell_window_end:
                push_data = self.coordinator.latest_push_data
                
                if push_data and "reflash_token" in push_data:
                    event_guid = push_data.get("event_guid")
                    user_id = push_data.get("user_id")
                    reflash_token = push_data.get("reflash_token")
                    
                    _LOGGER.info("捕获到有效开锁凭证！正在立即下发 HTTP 请求...")
                    success = await self.coordinator.client.async_unlock(
                        uid=self.coordinator.uid,
                        event_guid=event_guid,
                        user_id=user_id,
                        reflash_token=reflash_token,
                        auth_pass=self._auth_pass
                    )
                    # 清空本次成功拦截到的凭证防重用
                    self.coordinator.latest_push_data = {}
                    break
                
                # 每隔 1 秒进行检查
                await asyncio.sleep(1)

            if success:
                _LOGGER.info("开锁成功！播放成功状态帧。")
                # 远程开锁：正在解锁1秒 已解锁2秒 正在锁定1秒 (前置已由 async_unlock 触发，此处补齐)
                await asyncio.sleep(1)
                
                self._lock_state = "unlocked"
                self.async_write_ha_state()
                await asyncio.sleep(2)
                
                self._lock_state = "locking"
                self.async_write_ha_state()
                await asyncio.sleep(1)
                
                self._lock_state = "locked"
                self.async_write_ha_state()
                
                await self.coordinator.async_request_refresh()
            else:
                _LOGGER.error("开锁失败！窗口期耗尽或密码验证未通过。")
                self.hass.components.persistent_notification.async_create(
                    "安全窗口期 60 秒内未能捕获有效凭证，或因密码错误等原因遭到门锁系统拦截。\n\n已被重置回锁定状态。",
                    title=f"{self._attr_name} 开锁失败",
                    notification_id=f"{self.unique_id}_unlock_failed"
                )
                self._lock_state = "locked"
                self.async_write_ha_state()

        except asyncio.CancelledError:
            pass
        except Exception as e:
            _LOGGER.error("等待执行开锁流时发生异常: %s", e)
            self._lock_state = "locked"
            self.async_write_ha_state()