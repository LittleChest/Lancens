"""Sample API Client."""
import logging
import asyncio
import socket
import aiohttp
import async_timeout

TIMEOUT = 10


_LOGGER = logging.getLogger(__name__)

HEADERS = {
    "Content-type": "application/json; charset=UTF-8",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36 MicroMessenger/7.0.20.1781(0x6700143B) NetType/WIFI MiniProgramEnv/Windows WindowsWechat/WMPF WindowsWechat(0x63090a13) UnifiedPCWindowsWechat(0xf2541739) XWEB/18955",
    "Connection": "close"
}

class LancensApiClient:
    def __init__(
        self, token: str, session: aiohttp.ClientSession
    ) -> None:
        """Sample API Client."""
        self._token = token
        self._session = session
        self._base_url = "https://chniot.lancens.com:6448"

    async def async_get_data(self) -> dict:
        """Get data from the API."""
        return await self._api_wrapper(
            method="get", url=self._base_url + "/v1/api/user/mini/all/device/new"
        )

    async def async_get_events(self, uid: str, time: str = None) -> dict:
        """Get events from the API."""
        url = f"{self._base_url}/v1/api/mini/device/event/info/all?type=main&chooseType=&uid={uid}&page=0&page_number=20"
        if time:
            url += f"&time={time}"
        
        return await self._api_wrapper(method="get", url=url)

    async def async_get_settings(self, uid: str) -> list:
        """Get settings from the API."""
        # /v1/api/device/screen/light?uid=...&entry=mini
        url = f"{self._base_url}/v1/api/device/screen/light?uid={uid}&entry=mini"
        return await self._api_wrapper(method="get", url=url)

    async def async_set_screen_settings(self, uid: str, **kwargs) -> bool:
        """Set screen settings."""
        # POST /v1/api/device/screen/light
        url = f"{self._base_url}/v1/api/device/screen/light"
        data = {
            "uid": uid,
            "entry": "mini"
        }
        data.update(kwargs)
        return await self._api_wrapper(method="post", url=url, data=data)

    async def async_set_screen_timeout(self, uid: str, value: int) -> bool:
        """Set screen timeout."""
        return await self.async_set_screen_settings(uid, screenon_timeout=value)

    async def async_get_wx_push_status(self, uid: str) -> dict:
        """Get push status."""
        # GET /v1/api/device/mini/wx/push/status?uid=...&entry=mini&type=main
        url = f"{self._base_url}/v1/api/device/mini/wx/push/status?uid={uid}&entry=mini&type=main"
        return await self._api_wrapper(method="get", url=url)

    async def async_set_wx_push(self, uid: str, enabled: bool) -> bool:
        """Set push status."""
        # POST /v1/api/device/mini/push
        url = f"{self._base_url}/v1/api/device/mini/push"
        data = {
            "type": "main",
            "uid": uid,
            "wx_push": 1 if enabled else 0
        }
        return await self._api_wrapper(method="post", url=url, data=data)

    async def async_set_battery_display(self, uid: str, enabled: bool) -> bool:
        """Set battery display."""
        # POST /v1/api/device/battery/status
        url = f"{self._base_url}/v1/api/device/battery/status"
        data = {
            "uuid": uid,
            "entry": "mini",
            "bat_display_en": 1 if enabled else 0
        }
        return await self._api_wrapper(method="post", url=url, data=data)

    async def _api_wrapper(
        self, method: str, url: str, data: dict | None = None, headers: dict | None = None
    ) -> any:
        """Get information from the API."""
        if headers is None:
            headers = {}
        headers["token"] = self._token
        headers.update(HEADERS)

        for attempt in range(3):
            try:
                async with async_timeout.timeout(TIMEOUT):
                    if method == "get":
                        response = await self._session.get(url, headers=headers)
                        response.raise_for_status()
                        if response.status == 304:
                             return {} 
                        return await response.json()

                    elif method == "put":
                        response = await self._session.put(url, headers=headers, json=data)
                        response.raise_for_status()
                        return await response.json()

                    elif method == "patch":
                        response = await self._session.patch(url, headers=headers, json=data)
                        response.raise_for_status()
                        return await response.json()

                    elif method == "post":
                        response = await self._session.post(url, headers=headers, json=data)
                        response.raise_for_status()
                        if response.status == 204:
                            return True
                        return await response.json()
            except aiohttp.ServerDisconnectedError as exception:
                if attempt == 2:
                    _LOGGER.error("Server disconnected error fetching information from %s - %s", url, exception)
                    raise
                await asyncio.sleep(0.5)
            except asyncio.TimeoutError as exception:
                _LOGGER.error("Timeout error fetching information from %s - %s", url, exception)
                raise
            except (aiohttp.ClientError, socket.gaierror) as exception:
                _LOGGER.error("Error fetching information from %s - %s", url, exception)
                raise
            except Exception as exception:
                _LOGGER.error("Something really wrong happened! - %s", exception)
                raise
