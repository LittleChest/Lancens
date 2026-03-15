import asyncio
import time
from datetime import timedelta
import logging
from homeassistant.const import Platform
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from .api import LancensApiClient
from .const import DOMAIN, CONF_TOKEN

_LOGGER = logging.getLogger(__name__)
PLATFORMS = [Platform.SENSOR, Platform.SWITCH, Platform.NUMBER, Platform.IMAGE, Platform.LOCK]

async def async_setup_entry(hass, entry):
    hass.data.setdefault(DOMAIN, {})
    client = LancensApiClient(entry.data[CONF_TOKEN], async_get_clientsession(hass))

    try:
        devices = await client.async_get_data()
        dev_list = devices.get("deviceList",[]) if isinstance(devices, dict) else (devices if isinstance(devices, list) else[])
        if not dev_list:
            _LOGGER.error("此账户尚未绑定任何设备")
            return False
    except Exception as err:
        _LOGGER.error("无法加载设备列表，%s", err)
        return False

    coordinators = {}
    for dev in dev_list:
        if uid := str(dev.get("uid") or dev.get("uuid") or dev.get("id")):
            coord = LancensDataUpdateCoordinator(hass, client, uid, dev.get("name") or uid)
            await coord.async_setup()
            await coord.async_config_entry_first_refresh()
            coordinators[uid] = coord

    if not coordinators: return False
    hass.data[DOMAIN][entry.entry_id] = coordinators
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True

async def async_unload_entry(hass, entry):
    for coord in hass.data[DOMAIN].get(entry.entry_id, {}).values():
        for task in ("push_task", "event_task"):
            if t := getattr(coord, task, None): t.cancel()
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok

class LancensDataUpdateCoordinator(DataUpdateCoordinator):
    def __init__(self, hass, client, uid, device_name):
        self.client = client
        self.uid = uid
        self.device_name = device_name
        self.latest_push_data = {}
        self.sw_version = None
        self.doorbell_window_end = 0.0
        self.push_task = None
        self.event_task = None
        super().__init__(hass, _LOGGER, name=f"{DOMAIN}_{uid}", update_interval=timedelta(seconds=30))

    async def async_setup(self):
        self.event_task = self.hass.loop.create_task(self._async_event_poller())

    def trigger_doorbell_window(self):
        self.doorbell_window_end = time.time() + 60
        self.latest_push_data = {}
        if self.push_task and not self.push_task.done(): self.push_task.cancel()
        self.push_task = self.hass.loop.create_task(self._async_push_listener())

    def close_doorbell_window(self):
        self.doorbell_window_end = 0.0
        self.latest_push_data = {}
        if self.push_task and not self.push_task.done(): self.push_task.cancel()

    async def _async_push_listener(self):
        url, headers = f"{self.client._base_url}/v1/api/mini/push/event/new", {"token": self.client._token, "Content-Type": "application/json"}
        while time.time() < self.doorbell_window_end:
            try:
                async with self.client._session.post(url, headers=headers, json={"event_guid": ""}, timeout=60) as res:
                    if res.status == 200 and (data := await res.json()) and "reflash_token" in data:
                        data["received_time"] = time.time()
                        self.latest_push_data = data
            except asyncio.CancelledError: break
            except Exception: await asyncio.sleep(2)
        if time.time() >= self.doorbell_window_end > 0.0:
            self.latest_push_data = {}

    async def _async_event_poller(self):
        await asyncio.sleep(2)
        while True:
            try:
                await asyncio.sleep(1)
                events = await self.client.async_get_events(self.uid)
                if self.data:
                    old_list = self.data.get("events", {}).get("resultData", {}).get("eventList",[])
                    new_list = events.get("resultData", {}).get("eventList", [])
                    if (old_list[0].get("id") if old_list else None) != (new_list[0].get("id") if new_list else None):
                        if new_list and str(new_list[0].get("type")) == "1":
                            self.trigger_doorbell_window()
                        self.async_set_updated_data({**self.data, "events": events})
            except asyncio.CancelledError: break
            except Exception: pass

    async def _async_update_data(self):
        try:
            settings, wx_push = await asyncio.gather(
                self.client.async_get_settings(self.uid),
                self.client.async_get_wx_push_status(self.uid)
            )
            events = self.data.get("events") or await self.client.async_get_events(self.uid)
            if not self.sw_version:
                try:
                    if ver_data := await self.client.async_get_version(self.uid):
                        self.sw_version = ver_data[0].get("current_version")
                except Exception: pass
            return {"events": events, "settings": settings, "wx_push": wx_push}
        except Exception as err:
            raise UpdateFailed(f"无法连接到服务器: {err}") from err