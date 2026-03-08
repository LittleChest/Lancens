"""Image platform for Lancens."""
from __future__ import annotations

import base64
import binascii
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
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36 MicroMessenger/7.0.20.1781(0x6700143B) NetType/WIFI MiniProgramEnv/Windows WindowsWechat/WMPF WindowsWechat(0x63090a13) UnifiedPCWindowsWechat(0xf2541739) XWEB/18955",
    "Referer": "https://servicewechat.com/wx70441541e13a229d/87/page-frame.html"
}

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the image platform."""
    coordinator: LancensDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    
    async_add_entities([LancensLastEventImage(hass, coordinator)])


class LancensLastEventImage(CoordinatorEntity, ImageEntity):
    """Representation of a Lancens Last Event Image."""

    def __init__(self, hass: HomeAssistant, coordinator: LancensDataUpdateCoordinator) -> None:
        """Initialize the image."""
        super().__init__(coordinator)
        ImageEntity.__init__(self, hass)
        self._attr_unique_id = f"{coordinator.uid}_last_event_image"
        self._attr_name = "最新事件抓拍"

    @property
    def image_url(self) -> str | None:
        """Return URL of image."""
        if not self.coordinator.data:
            return None
        
        events = self.coordinator.data.get("events")
        if not events or not isinstance(events, dict):
             return None

        event_list = events.get("resultData", {}).get("eventList", [])
        if event_list and len(event_list) > 0:
            event = event_list[0]
            raw_url = event.get("img") or event.get("file_path") or event.get("url")
            
            if not raw_url:
                return None
            if raw_url.startswith("http"):
                return raw_url
            else:
                try:
                    decoded_bytes = base64.b64decode(raw_url)
                    return decoded_bytes.decode("utf-8")
                except (binascii.Error, UnicodeDecodeError):
                    _LOGGER.warning("Image URL decode failed, using raw value")
                    return raw_url
                    
        return None
    
    @property
    def image_last_updated(self) -> dt_util.dt.datetime | None:
        """The time when the image was last updated."""
        if self.coordinator.data:
            events = self.coordinator.data.get("events")
            event_list = events.get("resultData", {}).get("eventList", [])
            if event_list and len(event_list) > 0:
                time_str = event_list[0].get("time")
                if time_str:
                    return dt_util.parse_datetime(time_str)
        return self._attr_image_last_updated

    async def async_image(self) -> bytes | None:
        """Fetch image from URL with specific headers to bypass hotlink protection."""
        url = self.image_url
        if not url:
            return None
            
        try:
            session = async_get_clientsession(self.hass)
            async with session.get(url, headers=IMAGE_HEADERS, timeout=15) as response:
                response.raise_for_status()
                return await response.read()
        except Exception as err:
            _LOGGER.error("Error downloading image: %s", err)
            return None
