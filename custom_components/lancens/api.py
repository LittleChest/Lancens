import aiohttp
import async_timeout

class LancensApiClient:
    def __init__(
        self, token: str, session: aiohttp.ClientSession
    ) -> None:
        self._token = token
        self._session = session
        self._base_url = "https://chniot.lancens.com:6448"

    async def async_get_data(self) -> dict:
        return await self._api_wrapper(
            method="get", url=self._base_url + "/v1/api/user/mini/all/device/new"
        )

    async def async_get_events(self, uid: str, time: str = None) -> dict:
        url = f"{self._base_url}/v1/api/mini/device/event/info/all?type=main&chooseType=&uid={uid}&page=0&page_number=20"
        if time:
            url += f"&time={time}"
        return await self._api_wrapper(method="get", url=url)

    async def async_get_settings(self, uid: str) -> list:
        url = f"{self._base_url}/v1/api/device/screen/light?uid={uid}&entry=mini"
        return await self._api_wrapper(method="get", url=url)

    async def async_get_version(self, uid: str) -> list:
        """Get firmware version info."""
        url = f"{self._base_url}/v1/api/mini/upgrad/version?uid={uid}"
        return await self._api_wrapper(method="get", url=url)

    async def async_set_screen_settings(self, uid: str, **kwargs) -> bool:
        url = f"{self._base_url}/v1/api/device/screen/light"
        data = {"uid": uid, "entry": "mini"}
        data.update(kwargs)
        return await self._api_wrapper(method="post", url=url, data=data)

    async def async_get_wx_push_status(self, uid: str) -> dict:
        url = f"{self._base_url}/v1/api/device/mini/wx/push/status?uid={uid}&entry=mini&type=main"
        return await self._api_wrapper(method="get", url=url)

    async def async_set_wx_push(self, uid: str, enabled: bool) -> bool:
        url = f"{self._base_url}/v1/api/device/mini/push"
        data = {"type": "main", "uid": uid, "wx_push": 1 if enabled else 0}
        return await self._api_wrapper(method="post", url=url, data=data)

    async def async_set_battery_display(self, uid: str, enabled: bool) -> bool:
        url = f"{self._base_url}/v1/api/device/battery/status"
        data = {"uuid": uid, "entry": "mini", "bat_display_en": 1 if enabled else 0}
        return await self._api_wrapper(method="post", url=url, data=data)

    async def async_unlock(self, uid: str, event_guid: str, user_id: str, reflash_token: str, auth_pass: str) -> bool:
        url = f"{self._base_url}/v1/api/server/open/lock"
        sign = "92efcc26007c2faa730d212cb4e7c57a7ee821dd" 
        data = {
            "authPass": auth_pass,
            "uid": uid,
            "event_guid": event_guid,
            "user_id": str(user_id),
            "reflash_token": reflash_token,
            "authType": "safePass",
            "entry": "mini",
            "sign": sign
        }
        return await self._api_wrapper(method="post", url=url, data=data)

    async def _api_wrapper(
        self, method: str, url: str, data: dict | None = None, headers: dict | None = None
    ) -> any:
        if headers is None:
            headers = {}
        headers["token"] = self._token
        headers.update({
    "Content-type": "application/json",
})

        async with async_timeout.timeout(3):
            if method == "get":
                response = await self._session.get(url, headers=headers)
                response.raise_for_status()
                if response.status == 304:
                    return {}
                return await response.json(content_type=None)
            elif method == "post":
                response = await self._session.post(url, headers=headers, json=data)
                response.raise_for_status()
                if response.status == 204:
                    return True
                return await response.json(content_type=None)