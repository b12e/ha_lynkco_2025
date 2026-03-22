"""Lock platform for Lynk & Co integration."""

import logging

from homeassistant.components.lock import LockEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER
from .coordinator import LynkCoCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    entities = []
    for vin, coordinator in data["coordinators"].items():
        entities.append(LynkCoLock(coordinator, data["api"]))
    async_add_entities(entities)


class LynkCoLock(CoordinatorEntity, LockEntity):
    _attr_has_entity_name = True
    _attr_name = "Door lock"

    def __init__(self, coordinator: LynkCoCoordinator, api) -> None:
        super().__init__(coordinator)
        self._api = api
        self._attr_unique_id = f"{coordinator.vin}_lock"

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self.coordinator.vin)},
            "name": f"Lynk & Co {self.coordinator.model}",
            "manufacturer": MANUFACTURER,
            "model": self.coordinator.model,
            "serial_number": self.coordinator.vin,
        }

    @property
    def is_locked(self) -> bool | None:
        if self.coordinator.data is None:
            return None
        status = (
            self.coordinator.data.get("vehicle_data", {})
            .get("centralLock", {})
            .get("status")
        )
        if status is None:
            return None
        return status == "LOCKED"

    async def async_lock(self, **kwargs) -> None:
        _LOGGER.info("Locking %s", self.coordinator.vin)
        await self._api.lock_door(self.coordinator.vin)
        await self.coordinator.async_request_refresh()

    async def async_unlock(self, **kwargs) -> None:
        _LOGGER.info("Unlocking %s", self.coordinator.vin)
        await self._api.unlock_door(self.coordinator.vin)
        await self.coordinator.async_request_refresh()
