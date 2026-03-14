"""Lock platform for Lancens."""
from __future__ import annotations

from typing import Any

from homeassistant.components.lock import LockEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from . import LancensDataUpdateCoordinator

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the lock platform."""
    coordinator: LancensDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    auth_pass = entry.data.get("auth_pass")
    
    async_add_entities([LancensLock(coordinator, auth_pass)])


class LancensLock(CoordinatorEntity, LockEntity):
    """Lancens Lock Entity."""

    def __init__(self, coordinator: LancensDataUpdateCoordinator, auth_pass: str | None) -> None:
        """Initialize the lock."""
        super().__init__(coordinator)
        self._auth_pass = auth_pass
        self._attr_unique_id = f"{coordinator.uid}_lock"
        self._attr_name = "智能门锁"

    @property
    def is_locked(self) -> bool:
        """Return true if lock is locked. Device auto-locks."""
        return True

    async def async_lock(self, **kwargs: Any) -> None:
        """Lock the device. (Hardware locks automatically)"""
        pass

    async def async_unlock(self, **kwargs: Any) -> None:
        """Unlock the device remotely."""
        if not self._auth_pass:
            raise HomeAssistantError("未配置安全密码 (auth_pass)，无法执行远程开锁。请重新配置集成输入密码。")

        push_data = self.coordinator.latest_push_data
        if not push_data:
            raise HomeAssistantError("由于尚未收到访客的门铃呼叫推送，此时无法获取有效的安全开锁凭证。请在门锁上先发起呼叫！")

        event_guid = push_data.get("event_guid")
        user_id = push_data.get("user_id")
        reflash_token = push_data.get("reflash_token")

        if not all([event_guid, user_id, reflash_token]):
            raise HomeAssistantError("长连接收到的推送数据不完整，无法发起开锁。")

        success = await self.coordinator.client.async_unlock(
            uid=self.coordinator.uid,
            event_guid=event_guid,
            user_id=user_id,
            reflash_token=reflash_token,
            auth_pass=self._auth_pass
        )

        if not success:
            raise HomeAssistantError("开锁请求失败，可能是凭证已超时或密码错误。")
        else:
            # Refresh data to reflect the latest unlock log
            await self.coordinator.async_request_refresh()