"""The Lancens integration."""
from __future__ import annotations

import asyncio
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
from .const import DOMAIN, CONF_TOKEN, CONF_UID

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
    uid = entry.data.get(CONF_UID)

    session = async_get_clientsession(hass)
    client = LancensApiClient(token=token, session=session)

    # If UID is missing, try to discover it
    if not uid:
        try:
             _LOGGER.info("UID not provided, attempting discovery...")
             devices = await client.async_get_data()
             
             device_list =[]
             if isinstance(devices, dict):
                 device_list = devices.get("deviceList",[])
             elif isinstance(devices, list):
                 device_list = devices

             if device_list and len(device_list) > 0:
                 first_device = device_list[0]
                 uid = first_device.get("uid") or first_device.get("uuid") or first_device.get("id")
                 if uid:
                     _LOGGER.info("Discovered device with UID: %s", uid)
                 else:
                     _LOGGER.error("Could not find UID in device data: %s", first_device)
                     return False
             else:
                 _LOGGER.error("Device list is empty or invalid format: %s", devices)
                 return False
                 
        except Exception as err:
             _LOGGER.error("Failed to discover devices: %s", err)
             return False

    if not uid:
        _LOGGER.error("No UID found or provided. Setup failed.")
        return False

    # Create the coordinator
    coordinator = LancensDataUpdateCoordinator(hass, client, str(uid))
    await coordinator.async_setup()  # Start the background task for long-polling
    await coordinator.async_config_entry_first_refresh()

    hass.data[DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    coordinator = hass.data[DOMAIN].get(entry.entry_id)
    if coordinator and coordinator.push_task:
        coordinator.push_task.cancel()

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
    ) -> None:
        """Initialize."""
        self.client = client
        self.uid = uid
        self.data = {}
        self.latest_push_data = {}
        self.push_task = None
        
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=30),
        )

    async def async_setup(self):
        """Setup background task for realtime push events."""
        self.push_task = self.hass.loop.create_task(self._async_push_listener())

    async def _async_push_listener(self):
        """Long polling for push events to capture unlock credentials."""
        url = f"{self.client._base_url}/v1/api/mini/push/event/new"
        headers = {"token": self.client._token, "Content-Type": "application/json"}
        payload = {"event_guid": ""}
        
        while True:
            try:
                async with self.client._session.post(url, headers=headers, json=payload, timeout=65) as response:
                    if response.status == 200:
                        data = await response.json(content_type=None)
                        if data and "reflash_token" in data:
                            self.latest_push_data = data
                            _LOGGER.info("Received new unlock credentials via push data: %s", data)
                            await self.async_request_refresh()
                    elif response.status == 204:
                        # Timeout/no event, just continue
                        pass
            except asyncio.CancelledError:
                break
            except Exception as e:
                _LOGGER.debug("Push listener error (reconnecting in 5s): %s", e)
                await asyncio.sleep(5)

    async def _async_update_data(self):
        """Fetch data from API endpoint."""
        try:
            # 1. Events (for last unlock)
            try:
                events = await self.client.async_get_events(self.uid)
            except Exception as e:
                _LOGGER.warning("Error fetching events: %s", e)
                events = {}

            # 2. Settings (Screen/Light)
            try:
                settings = await self.client.async_get_settings(self.uid)
            except Exception as e:
                _LOGGER.warning("Error fetching settings: %s", e)
                settings =[]

            # 3. WX Push Status
            try:
                wx_push = await self.client.async_get_wx_push_status(self.uid)
            except Exception as e:
                _LOGGER.warning("Error fetching wx_push: %s", e)
                wx_push = {}
            
            return {
                "events": events,
                "settings": settings,
                "wx_push": wx_push
            }

        except Exception as err:
            raise UpdateFailed(f"Error communicating with API: {err}") from err