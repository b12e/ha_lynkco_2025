"""Lock platform for Lynk & Co integration."""

import logging

from homeassistant.components.lock import LockEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import LynkCoCoordinator, dig
from .entity import LynkCoEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    entities = []
    for coordinator in data["coordinators"].values():
        entities.append(LynkCoLock(coordinator, data["api"]))
        # The API tells us whether the car has a lockable glovebox (gloveBox is
        # null otherwise); whether the remote command works is per-model knowledge.
        has_glovebox = dig(coordinator.data, "vehicle_data", "gloveBox") is not None
        if (
            has_glovebox
            and coordinator.action_enabled("lock_glovebox")
            and coordinator.action_enabled("unlock_glovebox")
        ):
            entities.append(LynkCoGloveboxLock(coordinator, data["api"]))
    async_add_entities(entities)


class LynkCoLock(LynkCoEntity, LockEntity):
    _data_key = "vehicle_data"

    def __init__(self, coordinator: LynkCoCoordinator, api) -> None:
        super().__init__(coordinator, "lock")
        self._attr_translation_key = "door_lock"
        self._api = api

    @property
    def is_locked(self) -> bool | None:
        status = dig(self.coordinator.data, "vehicle_data", "centralLock", "status")
        if status is None:
            return None
        return status == "LOCKED"

    async def async_lock(self, **kwargs) -> None:
        self.coordinator.require_action("lock_door")
        _LOGGER.info("Locking %s", self.coordinator.vin)
        await self._api.lock_door(self.coordinator.vin)
        self._refresh_vehicle_data()

    async def async_unlock(self, **kwargs) -> None:
        self.coordinator.require_action("unlock_door")
        _LOGGER.info("Unlocking %s", self.coordinator.vin)
        await self._api.unlock_door(self.coordinator.vin)
        self._refresh_vehicle_data()

    def _refresh_vehicle_data(self) -> None:
        self.hass.async_create_task(
            self.coordinator.async_targeted_refresh(
                "vehicle_data", lambda: self._api.get_vehicle_data(self.coordinator.vin)
            )
        )


class LynkCoGloveboxLock(LynkCoEntity, LockEntity):
    _data_key = "vehicle_data"

    def __init__(self, coordinator: LynkCoCoordinator, api) -> None:
        super().__init__(coordinator, "glovebox_lock")
        self._api = api

    @property
    def code_format(self) -> str | None:
        if self.is_locked:
            return None
        return r"^\d{4}$"

    @property
    def is_locked(self) -> bool | None:
        status = dig(self.coordinator.data, "vehicle_data", "gloveBox", "status")
        if status is None:
            return None
        return status == "LOCKED"

    async def async_lock(self, **kwargs) -> None:
        self.coordinator.require_action("lock_glovebox")
        code = kwargs.get("code")
        if not code:
            raise ValueError("A PIN code is required to lock the glovebox")
        _LOGGER.info("Locking glovebox %s", self.coordinator.vin)
        await self._api.lock_glovebox(self.coordinator.vin, code)
        self._refresh_vehicle_data()

    async def async_unlock(self, **kwargs) -> None:
        self.coordinator.require_action("unlock_glovebox")
        _LOGGER.info("Unlocking glovebox %s", self.coordinator.vin)
        await self._api.unlock_glovebox(self.coordinator.vin)
        self._refresh_vehicle_data()

    def _refresh_vehicle_data(self) -> None:
        self.hass.async_create_task(
            self.coordinator.async_targeted_refresh(
                "vehicle_data", lambda: self._api.get_vehicle_data(self.coordinator.vin)
            )
        )
