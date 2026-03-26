"""Lock platform for Lynk & Co integration."""

import asyncio
import logging

from homeassistant.components.lock import LockEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER, MODEL_NAMES
from .coordinator import LynkCoCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    entities = []
    for vin, coordinator in data["coordinators"].items():
        entities.append(LynkCoLock(coordinator, data["api"]))
        entities.append(LynkCoGloveboxLock(coordinator, data["api"]))
    async_add_entities(entities)


class LynkCoLock(CoordinatorEntity, LockEntity):
    _attr_has_entity_name = True
    _attr_translation_key = "door_lock"

    def __init__(self, coordinator: LynkCoCoordinator, api) -> None:
        super().__init__(coordinator)
        self._api = api
        self._attr_unique_id = f"{coordinator.vin}_lock"

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self.coordinator.vin)},
            "name": MODEL_NAMES.get(self.coordinator.model, f"Lynk & Co {self.coordinator.model}"),
            "manufacturer": MANUFACTURER,
            "model": MODEL_NAMES.get(self.coordinator.model, self.coordinator.model),
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

    async def _delayed_refresh(self) -> None:
        await asyncio.sleep(15)
        await self.coordinator.async_request_refresh()

    async def async_lock(self, **kwargs) -> None:
        _LOGGER.info("Locking %s", self.coordinator.vin)
        await self._api.lock_door(self.coordinator.vin)
        self.hass.async_create_task(self._delayed_refresh())

    async def async_unlock(self, **kwargs) -> None:
        _LOGGER.info("Unlocking %s", self.coordinator.vin)
        await self._api.unlock_door(self.coordinator.vin)
        self.hass.async_create_task(self._delayed_refresh())


class LynkCoGloveboxLock(CoordinatorEntity, LockEntity):
    _attr_has_entity_name = True
    _attr_translation_key = "glovebox_lock"

    def __init__(self, coordinator: LynkCoCoordinator, api) -> None:
        super().__init__(coordinator)
        self._api = api
        self._attr_unique_id = f"{coordinator.vin}_glovebox_lock"

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self.coordinator.vin)},
            "name": MODEL_NAMES.get(self.coordinator.model, f"Lynk & Co {self.coordinator.model}"),
            "manufacturer": MANUFACTURER,
            "model": MODEL_NAMES.get(self.coordinator.model, self.coordinator.model),
            "serial_number": self.coordinator.vin,
        }

    @property
    def code_format(self) -> str | None:
        if self.is_locked:
            return None
        return r"^\d{4}$"

    @property
    def is_locked(self) -> bool | None:
        if self.coordinator.data is None:
            return None
        glovebox = self.coordinator.data.get("vehicle_data", {}).get("gloveBox")
        if glovebox is None:
            return None
        status = glovebox.get("status")
        if status is None:
            return None
        return status == "LOCKED"

    async def _delayed_refresh(self) -> None:
        await asyncio.sleep(15)
        await self.coordinator.async_request_refresh()

    async def async_lock(self, **kwargs) -> None:
        code = kwargs.get("code")
        if not code:
            raise ValueError("A PIN code is required to lock the glovebox")
        _LOGGER.info("Locking glovebox %s", self.coordinator.vin)
        await self._api.lock_glovebox(self.coordinator.vin, code)
        self.hass.async_create_task(self._delayed_refresh())

    async def async_unlock(self, **kwargs) -> None:
        _LOGGER.info("Unlocking glovebox %s", self.coordinator.vin)
        await self._api.unlock_glovebox(self.coordinator.vin)
        self.hass.async_create_task(self._delayed_refresh())
