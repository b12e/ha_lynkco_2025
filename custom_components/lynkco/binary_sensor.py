"""Binary sensor platform for Lynk & Co integration."""

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import LynkCoCoordinator
from .entity import LynkCoEntity

# One sensor per group of openings; the individual positions are attributes.
GROUPED_SENSOR_TYPES: list[dict] = [
    {
        "key": "doors",
        "device_class": BinarySensorDeviceClass.DOOR,
        "fields": {
            "front_left": "doorFrontLeftStatus",
            "front_right": "doorFrontRightStatus",
            "rear_left": "doorRearLeftStatus",
            "rear_right": "doorRearRightStatus",
        },
    },
    {
        "key": "windows",
        "device_class": BinarySensorDeviceClass.WINDOW,
        "fields": {
            "front_left": "windowFrontLeftStatus",
            "front_right": "windowFrontRightStatus",
            "rear_left": "windowRearLeftStatus",
            "rear_right": "windowRearRightStatus",
        },
    },
]

DOORS_SENSOR_TYPES: list[dict] = [
    # "entity_key" is looked up in the model feature file (not inferable from the API)
    {"key": "sunroof", "field": "sunroofStatus", "device_class": BinarySensorDeviceClass.WINDOW, "entity_key": "sunroof"},
    {"key": "hood", "field": "hoodStatus", "device_class": BinarySensorDeviceClass.DOOR},
    {"key": "trunk", "field": "trunkStatus", "device_class": BinarySensorDeviceClass.DOOR},
]

VEHICLE_DATA_BINARY_SENSORS: list[dict] = [
    {"key": "car_running", "field": "driveModeEnabled", "device_class": BinarySensorDeviceClass.RUNNING, "icon": "mdi:car"},
]

# Per-door / per-window sensors replaced by the grouped ones; their registry
# entries are removed so no orphaned "restored" entities linger.
RETIRED_KEYS = (
    "door_front_left", "door_front_right", "door_rear_left", "door_rear_right",
    "window_front_left", "window_front_right", "window_rear_left", "window_rear_right",
)


def _remove_retired_entities(hass: HomeAssistant, entry: ConfigEntry) -> None:
    registry = er.async_get(hass)
    for reg_entry in er.async_entries_for_config_entry(registry, entry.entry_id):
        if reg_entry.domain != "binary_sensor":
            continue
        if any(reg_entry.unique_id.endswith(f"_{key}") for key in RETIRED_KEYS):
            registry.async_remove(reg_entry.entity_id)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    _remove_retired_entities(hass, entry)
    data = hass.data[DOMAIN][entry.entry_id]
    entities = []
    for coordinator in data["coordinators"].values():
        for sensor_type in GROUPED_SENSOR_TYPES:
            entities.append(LynkCoGroupedBinarySensor(coordinator, sensor_type))
        for sensor_type in DOORS_SENSOR_TYPES:
            entity_key = sensor_type.get("entity_key")
            if entity_key and not coordinator.features.entity_enabled(entity_key):
                continue
            entities.append(LynkCoBinarySensor(coordinator, sensor_type))
        for sensor_type in VEHICLE_DATA_BINARY_SENSORS:
            entities.append(LynkCoVehicleDataBinarySensor(coordinator, sensor_type))
    async_add_entities(entities)


def _is_open(value) -> bool | None:
    if value is None:
        return None
    return value != "CLOSED"


class LynkCoGroupedBinarySensor(LynkCoEntity, BinarySensorEntity):
    """On when any opening in the group is not closed; attributes show each one."""

    _data_key = "doors"

    def __init__(self, coordinator: LynkCoCoordinator, sensor_type: dict) -> None:
        super().__init__(coordinator, sensor_type["key"])
        self._fields: dict[str, str] = sensor_type["fields"]
        self._attr_device_class = sensor_type["device_class"]

    def _states(self) -> dict[str, bool | None]:
        doors = (self.coordinator.data or {}).get("doors") or {}
        return {name: _is_open(doors.get(field)) for name, field in self._fields.items()}

    @property
    def is_on(self) -> bool | None:
        states = self._states()
        known = [state for state in states.values() if state is not None]
        if not known:
            return None
        return any(known)

    @property
    def extra_state_attributes(self) -> dict[str, str]:
        return {
            name: "unknown" if state is None else ("open" if state else "closed")
            for name, state in self._states().items()
        }


class LynkCoBinarySensor(LynkCoEntity, BinarySensorEntity):
    _data_key = "doors"

    def __init__(self, coordinator: LynkCoCoordinator, sensor_type: dict) -> None:
        super().__init__(coordinator, sensor_type["key"])
        self._field = sensor_type["field"]
        self._attr_device_class = sensor_type["device_class"]

    @property
    def is_on(self) -> bool | None:
        doors = (self.coordinator.data or {}).get("doors") or {}
        return _is_open(doors.get(self._field))


class LynkCoVehicleDataBinarySensor(LynkCoEntity, BinarySensorEntity):
    _data_key = "vehicle_data"

    def __init__(self, coordinator: LynkCoCoordinator, sensor_type: dict) -> None:
        super().__init__(coordinator, sensor_type["key"])
        self._field = sensor_type["field"]
        self._attr_device_class = sensor_type["device_class"]
        if "icon" in sensor_type:
            self._attr_icon = sensor_type["icon"]

    @property
    def is_on(self) -> bool | None:
        vehicle_data = (self.coordinator.data or {}).get("vehicle_data") or {}
        return vehicle_data.get(self._field)
