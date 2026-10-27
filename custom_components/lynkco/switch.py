"""Switch platform for Lynk & Co integration."""

import logging

from homeassistant.components.switch import SwitchDeviceClass, SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import LynkCoCoordinator
from .entity import LynkCoEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    entities = []
    for coordinator in data["coordinators"].values():
        # Not inferable from the API: only where start and stop are confirmed
        if coordinator.action_enabled("start_charging") and coordinator.action_enabled("stop_charging"):
            entities.append(LynkCoChargingSwitch(coordinator, data["api"]))
    async_add_entities(entities)


class LynkCoChargingSwitch(LynkCoEntity, SwitchEntity):
    _data_key = "charge"
    _attr_device_class = SwitchDeviceClass.SWITCH
    _attr_icon = "mdi:ev-station"

    def __init__(self, coordinator: LynkCoCoordinator, api) -> None:
        super().__init__(coordinator, "charging")
        self._api = api

    @property
    def is_on(self) -> bool | None:
        if self.coordinator.data is None:
            return None
        charge = self.coordinator.data.get("charge") or {}
        battery_state = charge.get("batteryState") or {}
        status = battery_state.get("status")
        if status is None:
            return None
        return str(status).upper() == "CHARGING"

    async def async_turn_on(self, **kwargs) -> None:
        self.coordinator.require_action("start_charging")
        _LOGGER.info("Starting charging %s", self.coordinator.vin)
        await self._api.start_charging(self.coordinator.vin)
        self._refresh_charge()

    async def async_turn_off(self, **kwargs) -> None:
        self.coordinator.require_action("stop_charging")
        _LOGGER.info("Stopping charging %s", self.coordinator.vin)
        await self._api.stop_charging(self.coordinator.vin)
        self._refresh_charge()

    def _refresh_charge(self) -> None:
        self.hass.async_create_task(
            self.coordinator.async_targeted_refresh(
                "charge", lambda: self._api.get_charge_state(self.coordinator.vin)
            )
        )
