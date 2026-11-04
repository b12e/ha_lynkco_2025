"""Number platform for Lynk & Co integration."""

import logging

from homeassistant.components.number import NumberDeviceClass, NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import LynkCoCoordinator, dig
from .entity import LynkCoEntity

_LOGGER = logging.getLogger(__name__)

DEFAULT_MIN_CHARGE_LIMIT = 50
DEFAULT_MAX_CHARGE_LIMIT = 100


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    entities = []
    for coordinator in data["coordinators"].values():
        # Not inferable from the API: only on models where the command is confirmed
        if coordinator.action_enabled("set_charge_limit"):
            entities.append(LynkCoChargeLimit(coordinator, data["api"]))
    async_add_entities(entities)


class LynkCoChargeLimit(LynkCoEntity, NumberEntity):
    """The battery charge limit, adjustable the way the app's slider is."""

    _data_key = "charge"
    _attr_device_class = NumberDeviceClass.BATTERY
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_native_step = 5
    _attr_mode = NumberMode.SLIDER
    _attr_icon = "mdi:battery-lock"

    def __init__(self, coordinator: LynkCoCoordinator, api) -> None:
        super().__init__(coordinator, "charge_limit")
        self._api = api

    @property
    def _limit(self) -> dict:
        return dig(self.coordinator.data, "charge", "batteryState", "chargeLimit") or {}

    @property
    def native_value(self) -> float | None:
        return self._limit.get("value")

    @property
    def native_min_value(self) -> float:
        # The API tells the range the car accepts (50 to 100 on the cars seen so far)
        return self._limit.get("min") or DEFAULT_MIN_CHARGE_LIMIT

    @property
    def native_max_value(self) -> float:
        return self._limit.get("max") or DEFAULT_MAX_CHARGE_LIMIT

    async def async_set_native_value(self, value: float) -> None:
        self.coordinator.require_action("set_charge_limit")
        percent = int(round(value))
        _LOGGER.info("Setting charge limit to %s%% for %s", percent, self.coordinator.log_vin)
        await self._api.set_charge_limit(self.coordinator.vin, percent)
        self.hass.async_create_task(
            self.coordinator.async_targeted_refresh(
                "charge", lambda: self._api.get_charge_state(self.coordinator.vin)
            )
        )
