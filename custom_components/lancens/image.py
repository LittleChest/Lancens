import base64
import logging
from homeassistant.components.image import ImageEntity
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.util import dt as dt_util
from .const import DOMAIN
from .entity import LancensEntity

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([LancensLastEventImage(hass, c) for c in hass.data[DOMAIN][entry.entry_id].values()])

class LancensLastEventImage(LancensEntity, ImageEntity):
    def __init__(self, hass, coordinator):
        super().__init__(coordinator)
        ImageEntity.__init__(self, hass)
        self._attr_unique_id = f"{coordinator.uid}_last_event_image"
        self._attr_name = f"{coordinator.device_name} 最新事件抓拍"

    @property
    def image_url(self):
        if event := self._latest_event:
            if raw_url := (event.get("img") or event.get("file_path") or event.get("url")):
                try:
                    return base64.b64decode(raw_url).decode("utf-8")
                except Exception as err:
                    _LOGGER.error("无法解析图片: %s", err)
                    return raw_url
        return None
    
    @property
    def image_last_updated(self):
        if (event := self._latest_event) and (time_str := event.get("time")):
            return dt_util.parse_datetime(time_str)
        return self._attr_image_last_updated

    async def async_image(self):
        if not (url := self.image_url):
            return None
        try:
            headers = {"Referer": "https://servicewechat.com/wx70441541e13a229d/87/page-frame.html"}
            async with async_get_clientsession(self.hass).get(url, headers=headers, timeout=5) as res:
                res.raise_for_status()
                return await res.read()
        except Exception as err:
            _LOGGER.error("无法下载图片: %s", err)
            return None