from __future__ import annotations

import base64
import logging

from homeassistant.components.image import ImageEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from . import LancensDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

IMAGE_HEADERS = {
    "Referer": "https://servicewechat.com/wx70441541e13a229d/87/page-frame.html"
}

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinators = hass.data[DOMAIN][entry.entry_id]
    entities =[LancensLastEventImage(hass, coord) for coord in coordinators.values()]
    async_add_entities(entities)


class LancensLastEventImage(CoordinatorEntity, ImageEntity):
    def __init__(self, hass: HomeAssistant, coordinator: LancensDataUpdateCoordinator) -> None:
        super().__init__(coordinator)
        ImageEntity.__init__(self, hass)
        self._attr_unique_id = f"{coordinator.uid}_last_event_image"
        self._attr_name = f"{coordinator.device_name} 最新事件抓拍"

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
    def image_url(self) -> str | None:
        if not self.coordinator.data:
            return None
        
        events = self.coordinator.data.get("events")
        if not events or not isinstance(events, dict):
             return None

        event_list = events.get("resultData", {}).get("eventList",[])
        if event_list and len(event_list) > 0:
            event = event_list[0]
            raw_url = event.get("img") or event.get("file_path") or event.get("url")
            
            if not raw_url:
                return None
            else:
                try:
                    decoded_bytes = base64.b64decode(raw_url)
                    return decoded_bytes.decode("utf-8")
                except Exception as err:
                    _LOGGER.error("无法解析图片: %s", err)
                    return raw_url
        return None
    
    @property
    def image_last_updated(self) -> dt_util.dt.datetime | None:
        if self.coordinator.data:
            events = self.coordinator.data.get("events")
            event_list = events.get("resultData", {}).get("eventList",[])
            if event_list and len(event_list) > 0:
                time_str = event_list[0].get("time")
                if time_str:
                    return dt_util.parse_datetime(time_str)
        return self._attr_image_last_updated

    async def async_image(self) -> bytes | None:
        url = self.image_url
        if not url:
            return None
        try:
            session = async_get_clientsession(self.hass)
            async with session.get(url, headers=IMAGE_HEADERS, timeout=5) as response:
                response.raise_for_status()
                return await response.read()
        except Exception as err:
            _LOGGER.error("无法下载图片: %s", err)
            return None