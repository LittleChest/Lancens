
class LancensApiClient:
    def __init__(self, token, session):
        self._token = token
        self._session = session
        self._base_url = "https://chniot.lancens.com:6448"

    async def async_get_data(self):
        return await self._req("get", f"{self._base_url}/v1/api/user/mini/all/device/new")

    async def async_get_events(self, uid, time=None):
        url = f"{self._base_url}/v1/api/mini/device/event/info/all?type=main&chooseType=&uid={uid}&page=0&page_number=20"
        return await self._req("get", f"{url}&time={time}" if time else url)

    async def async_get_settings(self, uid):
        return await self._req("get", f"{self._base_url}/v1/api/device/screen/light?uid={uid}&entry=mini")

    async def async_get_version(self, uid):
        return await self._req("get", f"{self._base_url}/v1/api/mini/upgrad/version?uid={uid}")

    async def async_set_screen_settings(self, uid, **kwargs):
        return await self._req("post", f"{self._base_url}/v1/api/device/screen/light", {"uid": uid, "entry": "mini", **kwargs})

    async def async_get_wx_push_status(self, uid):
        return await self._req("get", f"{self._base_url}/v1/api/device/mini/wx/push/status?uid={uid}&entry=mini&type=main")

    async def async_set_wx_push(self, uid, enabled):
        return await self._req("post", f"{self._base_url}/v1/api/device/mini/push", {"type": "main", "uid": uid, "wx_push": 1 if enabled else 0})

    async def async_set_battery_display(self, uid, enabled):
        return await self._req("post", f"{self._base_url}/v1/api/device/battery/status", {"uuid": uid, "entry": "mini", "bat_display_en": 1 if enabled else 0})

    async def async_unlock(self, uid, event_guid, user_id, reflash_token, auth_pass):
        data = {"authPass": auth_pass, "uid": uid, "event_guid": event_guid, "user_id": str(user_id), "reflash_token": reflash_token, "authType": "safePass", "entry": "mini", "sign": "92efcc26007c2faa730d212cb4e7c57a7ee821dd"}
        return await self._req("post", f"{self._base_url}/v1/api/server/open/lock", data)

    async def _req(self, method, url, data=None):
        headers = {"token": self._token, "Content-type": "application/json"}
        async with getattr(self._session, method)(url, headers=headers, json=data, timeout=3) as res:
            res.raise_for_status()
            return {} if res.status == 304 else (True if res.status == 204 else await res.json(content_type=None))