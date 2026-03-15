"""Sample API Client."""
import logging
import asyncio
import socket
import aiohttp
import async_timeout

TIMEOUT = 15

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
        url = f"{self._base_url}/v1/api/mini/device/event/info/all?type=main&chooseType=&uid={uid}&page=0&page_number=20"
        if time:
            url += f"&time={time}"
        return await self._api_wrapper(method="get", url=url)

    async def async_get_settings(self, uid: str) -> list:
        url = f"{self._base_url}/v1/api/device/screen/light?uid={uid}&entry=mini"
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
        """Send remote unlock request."""
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
        
        _LOGGER.info("API 准备发送远程开锁请求, URL: %s", url)
        _LOGGER.info("API 开锁 Payload 数据: %s", data)
        try:
            res = await self._api_wrapper(method="post", url=url, data=data)
            _LOGGER.info("API 远程开锁服务器响应结果: %s", res)
            
            # Post-notify
            try:
                await self._api_wrapper(method="post", url=f"{self._base_url}/v1/api/mini/lock/event", data={"uid": uid})
                _LOGGER.info("API 开锁后状态通知成功发送")
            except Exception as ev_err:
                _LOGGER.warning("API 开锁后状态通知发送失败 (不影响开门): %s", ev_err)
                
            return True
        except Exception as e:
            _LOGGER.error("API 开锁过程中发生异常: %s", e)
            return False

    async def _api_wrapper(
        self, method: str, url: str, data: dict | None = None, headers: dict | None = None
    ) -> any:
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
                        return await response.json(content_type=None)
                    elif method == "post":
                        response = await self._session.post(url, headers=headers, json=data)
                        response.raise_for_status()
                        if response.status == 204:
                            return True
                        return await response.json(content_type=None)
            except aiohttp.ServerDisconnectedError:
                if attempt == 2:
                    raise
                await asyncio.sleep(0.5)
            except Exception as exception:
                raise