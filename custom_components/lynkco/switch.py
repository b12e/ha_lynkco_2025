"""Switch platform for Lynk & Co integration."""

import logging

from homeassistant.components.switch import SwitchDeviceClass, SwitchEntity
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
        entities.append(LynkCoChargingSwitch(coordinator, data["api"]))
    async_add_entities(entities)


class LynkCoChargingSwitch(CoordinatorEntity, SwitchEntity):
    _attr_has_entity_name = True
    _attr_translation_key = "charging"
    _attr_device_class = SwitchDeviceClass.SWITCH
    _attr_icon = "mdi:ev-station"

    def __init__(self, coordinator: LynkCoCoordinator, api) -> None:
        super().__init__(coordinator)
        self._api = api
        self._attr_unique_id = f"{coordinator.vin}_charging"

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
        _LOGGER.info("Starting charging %s", self.coordinator.vin)
        await self._api.start_charging(self.coordinator.vin)
        self.hass.async_create_task(
            self.coordinator.async_targeted_refresh(
                "charge", lambda: self._api.get_charge_state(self.coordinator.vin)
            )
        )

    async def async_turn_off(self, **kwargs) -> None:
        _LOGGER.info("Stopping charging %s", self.coordinator.vin)
        await self._api.stop_charging(self.coordinator.vin)
        self.hass.async_create_task(
            self.coordinator.async_targeted_refresh(
                "charge", lambda: self._api.get_charge_state(self.coordinator.vin)
            )
        )
