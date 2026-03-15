"""The Lancens integration."""
from __future__ import annotations

import asyncio
import time
from datetime import timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)

from .api import LancensApiClient
from .const import DOMAIN, CONF_TOKEN

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] =[
    Platform.SENSOR, 
    Platform.SWITCH, 
    Platform.NUMBER, 
    Platform.IMAGE,
    Platform.LOCK
]

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Lancens from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    token = entry.data[CONF_TOKEN]

    session = async_get_clientsession(hass)
    client = LancensApiClient(token=token, session=session)

    try:
        devices = await client.async_get_data()
        device_list = devices.get("deviceList",[]) if isinstance(devices, dict) else (devices if isinstance(devices, list) else[])
        if not device_list:
            _LOGGER.error("叮叮智能：未发现任何设备，加载失败。")
            return False
    except Exception as err:
        _LOGGER.error("叮叮智能：拉取设备列表失败，%s", err)
        return False

    coordinators = {}
    for dev in device_list:
        uid = dev.get("uid") or dev.get("uuid") or dev.get("id")
        name = dev.get("name", "智能锁")
        if uid:
            _LOGGER.info("发现叮叮设备: %s (UID: %s)", name, uid)
            coord = LancensDataUpdateCoordinator(hass, client, str(uid), name)
            await coord.async_setup()
            await coord.async_config_entry_first_refresh()
            coordinators[str(uid)] = coord

    if not coordinators:
        return False

    hass.data[DOMAIN][entry.entry_id] = coordinators
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    coordinators = hass.data[DOMAIN].get(entry.entry_id, {})
    for coord in coordinators.values():
        if getattr(coord, "push_task", None):
            coord.push_task.cancel()
        if getattr(coord, "event_task", None):
            coord.event_task.cancel()

    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok


class LancensDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching Lancens data."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: LancensApiClient,
        uid: str,
        device_name: str,
    ) -> None:
        """Initialize."""
        self.client = client
        self.uid = uid
        self.device_name = device_name
        self.event_interval = 3  # 固定高频事件轮询时间为 3 秒
        self.data = {}
        self.latest_push_data = {}
        
        self.doorbell_window_end = 0.0
        
        self.push_task: asyncio.Task | None = None
        self.event_task: asyncio.Task | None = None
        
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{uid}",
            update_interval=timedelta(seconds=30),
        )

    async def async_setup(self):
        """Setup background event poller."""
        self.event_task = self.hass.loop.create_task(self._async_event_poller())

    def trigger_doorbell_window(self):
        """收到门铃事件时调用，创建 60 秒窗口期并拉取凭证"""
        _LOGGER.info("[%s] 收到门铃呼叫！开启 60 秒开锁窗口期，开始获取安全凭证", self.device_name)
        self.doorbell_window_end = time.time() + 60
        self.latest_push_data = {}
        
        if self.push_task and not self.push_task.done():
            self.push_task.cancel()
        self.push_task = self.hass.loop.create_task(self._async_push_listener())

    async def _async_push_listener(self):
        """窗口期内的凭证长轮询任务"""
        url = f"{self.client._base_url}/v1/api/mini/push/event/new"
        headers = {"token": self.client._token, "Content-Type": "application/json"}
        payload = {"event_guid": ""}
        
        while time.time() < self.doorbell_window_end:
            try:
                async with self.client._session.post(url, headers=headers, json=payload, timeout=65) as response:
                    if response.status == 200:
                        data = await response.json(content_type=None)
                        if data and "reflash_token" in data:
                            data["received_time"] = time.time()
                            self.latest_push_data = data
                            _LOGGER.debug("[%s] 成功获取到开锁凭证！将在窗口期内待命...", self.device_name)
                            break 
            except asyncio.CancelledError:
                break
            except Exception:
                await asyncio.sleep(2)

        if time.time() >= self.doorbell_window_end:
            _LOGGER.info("[%s] 60 秒开锁窗口期已结束，停止长轮询并作废凭证。", self.device_name)
            self.latest_push_data = {}

    async def _async_event_poller(self):
        """独立的高频事件轮询任务 (3秒)"""
        await asyncio.sleep(2)
        while True:
            try:
                await asyncio.sleep(self.event_interval)
                events = await self.client.async_get_events(self.uid)
                if self.data is not None:
                    old_events = self.data.get("events", {})
                    old_list = old_events.get("resultData", {}).get("eventList",[]) if isinstance(old_events, dict) else[]
                    new_list = events.get("resultData", {}).get("eventList",[]) if isinstance(events, dict) else[]
                    
                    old_id = old_list[0].get("id") if old_list else None
                    new_id = new_list[0].get("id") if new_list else None
                    
                    if old_id != new_id:
                        _LOGGER.debug("[%s] 轮询到新事件！", self.device_name)
                        
                        if new_list:
                            latest_event = new_list[0]
                            if str(latest_event.get("type")) == "1":
                                self.trigger_doorbell_window()
                        
                        new_data = dict(self.data)
                        new_data["events"] = events
                        self.async_set_updated_data(new_data)
            except asyncio.CancelledError:
                break
            except Exception:
                pass

    async def _async_update_data(self):
        """HA 常规基础数据拉取 (30s)"""
        try:
            settings = await self.client.async_get_settings(self.uid)
            wx_push = await self.client.async_get_wx_push_status(self.uid)
            events = self.data.get("events", {}) if self.data else await self.client.async_get_events(self.uid)
            
            return {
                "events": events,
                "settings": settings,
                "wx_push": wx_push
            }
        except Exception as err:
            raise UpdateFailed(f"Error communicating with API: {err}") from err