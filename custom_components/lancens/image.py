"""Image platform for Lancens."""
from __future__ import annotations

import httpx

from homeassistant.components.image import ImageEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from . import LancensDataUpdateCoordinator

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
            # Assume key is 'file_path' or 'img_url' or 'url'
            event = event_list[0]
            url = event.get("file_path") or event.get("img_url") or event.get("url") or event.get("image")
            return url
        return None
    
    @property
    def image_last_updated(self) -> dt_util.dt.datetime | None:
        """The time when the image was last updated."""
        if not self.coordinator.data:
            return self._attr_image_last_updated
            
        return self._attr_image_last_updated

    async def async_image(self) -> bytes | None:
        """Fetch image from URL."""
        url = self.image_url
        if not url:
            return None
            
        try:
            session = self.hass.helpers.aiohttp_client.async_get_clientsession(self.hass)
            async with session.get(url, timeout=10) as response:
                response.raise_for_status()
                return await response.read()
        except Exception:
            return None
