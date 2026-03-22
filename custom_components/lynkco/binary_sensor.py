"""Binary sensor platform for Lynk & Co integration."""

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER
from .coordinator import LynkCoCoordinator

BINARY_SENSOR_TYPES: list[dict] = [
    {"key": "door_front_left", "name": "Front left door", "field": "doorFrontLeftStatus", "device_class": BinarySensorDeviceClass.DOOR},
    {"key": "door_front_right", "name": "Front right door", "field": "doorFrontRightStatus", "device_class": BinarySensorDeviceClass.DOOR},
    {"key": "door_rear_left", "name": "Rear left door", "field": "doorRearLeftStatus", "device_class": BinarySensorDeviceClass.DOOR},
    {"key": "door_rear_right", "name": "Rear right door", "field": "doorRearRightStatus", "device_class": BinarySensorDeviceClass.DOOR},
    {"key": "window_front_left", "name": "Front left window", "field": "windowFrontLeftStatus", "device_class": BinarySensorDeviceClass.WINDOW},
    {"key": "window_front_right", "name": "Front right window", "field": "windowFrontRightStatus", "device_class": BinarySensorDeviceClass.WINDOW},
    {"key": "window_rear_left", "name": "Rear left window", "field": "windowRearLeftStatus", "device_class": BinarySensorDeviceClass.WINDOW},
    {"key": "window_rear_right", "name": "Rear right window", "field": "windowRearRightStatus", "device_class": BinarySensorDeviceClass.WINDOW},
    {"key": "sunroof", "name": "Sunroof", "field": "sunroofStatus", "device_class": BinarySensorDeviceClass.WINDOW},
    {"key": "hood", "name": "Hood", "field": "hoodStatus", "device_class": BinarySensorDeviceClass.DOOR},
    {"key": "trunk", "name": "Trunk", "field": "trunkStatus", "device_class": BinarySensorDeviceClass.DOOR},
]


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    entities = []
    for vin, coordinator in data["coordinators"].items():
        for sensor_type in BINARY_SENSOR_TYPES:
            entities.append(LynkCoBinarySensor(coordinator, sensor_type))
    async_add_entities(entities)


class LynkCoBinarySensor(CoordinatorEntity, BinarySensorEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator: LynkCoCoordinator, sensor_type: dict) -> None:
        super().__init__(coordinator)
        self._sensor_type = sensor_type
        self._attr_unique_id = f"{coordinator.vin}_{sensor_type['key']}"
        self._attr_name = sensor_type["name"]
        self._attr_device_class = sensor_type["device_class"]

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
    def is_on(self) -> bool | None:
        if self.coordinator.data is None:
            return None
        doors = self.coordinator.data.get("doors", {})
        value = doors.get(self._sensor_type["field"])
        if value is None:
            return None
        return value != "CLOSED"
