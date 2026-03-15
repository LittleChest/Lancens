
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .const import DOMAIN

class LancensEntity(CoordinatorEntity):
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
    def _latest_event(self):
        if not self.coordinator.data:
            return None
        return next(iter(self.coordinator.data.get("events", {}).get("resultData", {}).get("eventList",[])), None)