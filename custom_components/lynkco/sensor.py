"""Sensor platform for Lynk & Co integration."""

from datetime import datetime

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfEnergy, UnitOfLength, UnitOfPower, UnitOfTemperature, UnitOfTime, UnitOfVolume
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .coordinator import LynkCoCoordinator
from .entity import LynkCoEntity


SENSOR_TYPES: list[dict] = [
    {
        "key": "battery_level",
        "data_key": "charge",
        "name": "Battery level",
        "icon": "mdi:battery",
        "device_class": SensorDeviceClass.BATTERY,
        "unit": PERCENTAGE,
        "state_class": SensorStateClass.MEASUREMENT,
        "value_fn": lambda d: _pct(_dig(d, "charge", "batteryState", "stateOfCharge")),
    },
    {
        "key": "battery_range",
        "data_key": "charge",
        "name": "Electric range",
        "icon": "mdi:map-marker-distance",
        "device_class": SensorDeviceClass.DISTANCE,
        "unit": UnitOfLength.KILOMETERS,
        "state_class": SensorStateClass.MEASUREMENT,
        "value_fn": lambda d: _dig(d, "charge", "batteryState", "remainingRange"),
    },
    {
        "key": "charging_status",
        "data_key": "charge",
        "name": "Charging status",
        "icon": "mdi:ev-station",
        "device_class": SensorDeviceClass.ENUM,
        "unit": None,
        "state_class": None,
        "value_fn": lambda d: _lower(_dig(d, "charge", "batteryState", "status")),
    },
    {
        "key": "charging_speed",
        "data_key": "charge",
        "name": "Charging speed",
        "icon": "mdi:flash",
        "device_class": SensorDeviceClass.POWER,
        "unit": UnitOfPower.KILO_WATT,
        "state_class": SensorStateClass.MEASUREMENT,
        "value_fn": lambda d: _dig(d, "charge", "batteryState", "chargingSpeed", "kW"),
    },
    {
        "key": "charging_time_remaining",
        "data_key": "charge",
        "name": "Charging time remaining",
        "icon": "mdi:timer-sand",
        "device_class": SensorDeviceClass.DURATION,
        "unit": UnitOfTime.MINUTES,
        "state_class": SensorStateClass.MEASUREMENT,
        "value_fn": lambda d: _dig(d, "charge", "batteryState", "remainingChargingTime"),
    },
    {
        "key": "charge_limit",
        "data_key": "charge",
        "name": "Charge limit",
        "icon": "mdi:battery-lock",
        "device_class": None,
        "unit": PERCENTAGE,
        "state_class": SensorStateClass.MEASUREMENT,
        "value_fn": lambda d: _dig(d, "charge", "batteryState", "chargeLimit", "value"),
    },
    {
        "key": "power_consumption",
        "data_key": "charge",
        "name": "Average electric consumption",
        "icon": "mdi:meter-electric",
        "device_class": None,
        "unit": "kWh/100km",
        "state_class": SensorStateClass.MEASUREMENT,
        "value_fn": lambda d: _dig(d, "charge", "batteryState", "powerAverageConsumption"),
    },
    {
        "key": "interior_temperature",
        "data_key": "climate",
        "name": "Interior temperature",
        "icon": "mdi:thermometer",
        "device_class": SensorDeviceClass.TEMPERATURE,
        "unit": UnitOfTemperature.CELSIUS,
        "state_class": SensorStateClass.MEASUREMENT,
        "value_fn": lambda d: _dig(d, "climate", "interiorTemperature"),
    },
    {
        "key": "target_temperature",
        "data_key": "climate",
        "name": "Target temperature",
        "icon": "mdi:thermometer-auto",
        "device_class": SensorDeviceClass.TEMPERATURE,
        "unit": UnitOfTemperature.CELSIUS,
        "state_class": SensorStateClass.MEASUREMENT,
        "value_fn": lambda d: _dig(d, "climate", "targetTemperature"),
    },
    {
        "key": "climate_status",
        "data_key": "climate",
        "name": "Climate status",
        "icon": "mdi:air-conditioner",
        "device_class": SensorDeviceClass.ENUM,
        "unit": None,
        "state_class": None,
        "value_fn": lambda d: _lower(_dig(d, "climate", "status")),
    },
    {
        "key": "heater_steering_wheel",
        "data_key": "climate",
        "name": "Steering wheel heater",
        "icon": "mdi:steering",
        "device_class": SensorDeviceClass.ENUM,
        "unit": None,
        "state_class": None,
        "value_fn": lambda d: _heater_status(d, "steeringWheel"),
        "heater_key": "steeringWheel",
    },
    {
        "key": "heater_windshield",
        "data_key": "climate",
        "heater_key": "windshield",
        "name": "Windshield heater",
        "icon": "mdi:car-defrost-front",
        "device_class": SensorDeviceClass.ENUM,
        "unit": None,
        "state_class": None,
        "value_fn": lambda d: _heater_status(d, "windshield"),
    },
    {
        "key": "heater_front_left_seat",
        "data_key": "climate",
        "heater_key": "frontLeftSeat",
        "name": "Front left seat heater",
        "icon": "mdi:car-seat-heater",
        "device_class": SensorDeviceClass.ENUM,
        "unit": None,
        "state_class": None,
        "value_fn": lambda d: _heater_status(d, "frontLeftSeat"),
    },
    {
        "key": "heater_front_right_seat",
        "data_key": "climate",
        "heater_key": "frontRightSeat",
        "name": "Front right seat heater",
        "icon": "mdi:car-seat-heater",
        "device_class": SensorDeviceClass.ENUM,
        "unit": None,
        "state_class": None,
        "value_fn": lambda d: _heater_status(d, "frontRightSeat"),
    },
    {
        "key": "heater_rear_left_seat",
        "data_key": "climate",
        "name": "Rear left seat heater",
        "icon": "mdi:car-seat-heater",
        "device_class": SensorDeviceClass.ENUM,
        "unit": None,
        "state_class": None,
        "value_fn": lambda d: _heater_status(d, "rearLeftSeat"),
        "heater_key": "rearLeftSeat",
    },
    {
        "key": "heater_rear_center_seat",
        "data_key": "climate",
        "name": "Rear center seat heater",
        "icon": "mdi:car-seat-heater",
        "device_class": SensorDeviceClass.ENUM,
        "unit": None,
        "state_class": None,
        "value_fn": lambda d: _heater_status(d, "rearCenterSeat"),
        "heater_key": "rearCenterSeat",
    },
    {
        "key": "heater_rear_right_seat",
        "data_key": "climate",
        "name": "Rear right seat heater",
        "icon": "mdi:car-seat-heater",
        "device_class": SensorDeviceClass.ENUM,
        "unit": None,
        "state_class": None,
        "value_fn": lambda d: _heater_status(d, "rearRightSeat"),
        "heater_key": "rearRightSeat",
    },
    {
        "key": "lock_status",
        "data_key": "vehicle_data",
        "name": "Central lock",
        "icon": "mdi:car-door-lock",
        "device_class": SensorDeviceClass.ENUM,
        "unit": None,
        "state_class": None,
        "value_fn": lambda d: _lower(_dig(d, "vehicle_data", "centralLock", "status")),
    },
    {
        "key": "address",
        "data_key": "location",
        "name": "Address",
        "icon": "mdi:map-marker",
        "device_class": None,
        "unit": None,
        "state_class": None,
        "value_fn": lambda d: _dig(d, "location", "vehicleLocation", "longAddress"),
    },
    {
        "key": "fuel_level",
        "data_key": "fuel",
        "name": "Fuel level",
        "icon": "mdi:gas-station",
        "device_class": None,
        "unit": PERCENTAGE,
        "state_class": SensorStateClass.MEASUREMENT,
        "value_fn": lambda d: _pct(_dig(d, "fuel", "fuelState", "percentageOfRemainingFuel")),
        "fuel_only": True,
    },
    {
        "key": "fuel_range",
        "data_key": "fuel",
        "name": "Fuel range",
        "icon": "mdi:gas-station-outline",
        "device_class": SensorDeviceClass.DISTANCE,
        "unit": UnitOfLength.KILOMETERS,
        "state_class": SensorStateClass.MEASUREMENT,
        "value_fn": lambda d: _dig(d, "fuel", "fuelState", "remainingRange"),
        "fuel_only": True,
    },
    {
        "key": "fuel_consumption",
        "data_key": "fuel",
        "name": "Average fuel consumption",
        "icon": "mdi:fuel",
        "device_class": None,
        "unit": "L/100km",
        "state_class": SensorStateClass.MEASUREMENT,
        "value_fn": lambda d: _dig(d, "fuel", "fuelState", "averageConsumption"),
        "fuel_only": True,
    },
    {
        "key": "fuel_type",
        "data_key": "fuel",
        "name": "Fuel type",
        "icon": "mdi:gas-station",
        "device_class": SensorDeviceClass.ENUM,
        "unit": None,
        "state_class": None,
        "value_fn": lambda d: _lower(_dig(d, "fuel", "fuelInfo", "fuelType")),
        "fuel_only": True,
    },
    {
        "key": "odometer",
        "data_key": "metadata",
        "name": "Odometer",
        "icon": "mdi:counter",
        "device_class": SensorDeviceClass.DISTANCE,
        "unit": UnitOfLength.KILOMETERS,
        "state_class": SensorStateClass.TOTAL_INCREASING,
        "value_fn": lambda d: _dig(d, "metadata", "vehicle", "odometer"),
    },
    {
        "key": "battery_capacity",
        "data_key": "metadata",
        "name": "Battery capacity",
        "icon": "mdi:battery-high",
        "device_class": None,
        "unit": UnitOfEnergy.KILO_WATT_HOUR,
        "state_class": SensorStateClass.MEASUREMENT,
        "value_fn": lambda d: _round(_dig(d, "metadata", "batteryInfo", "batteryCapacity")),
    },
    {
        "key": "battery_energy",
        "data_key": "charge",
        "name": "Battery energy",
        "icon": "mdi:battery-charging",
        "device_class": None,
        "unit": UnitOfEnergy.KILO_WATT_HOUR,
        "state_class": SensorStateClass.MEASUREMENT,
        "value_fn": lambda d: _battery_kwh(d),
    },
    {
        "key": "tank_capacity",
        "data_key": "metadata",
        "name": "Tank capacity",
        "icon": "mdi:gas-station",
        "device_class": None,
        "unit": UnitOfVolume.LITERS,
        "state_class": SensorStateClass.MEASUREMENT,
        "value_fn": lambda d: _dig(d, "metadata", "fuelInfo", "tankCapacity"),
        "fuel_only": True,
    },
    {
        "key": "fuel_level_liters",
        "data_key": "fuel",
        "name": "Fuel level",
        "icon": "mdi:gas-station",
        "device_class": None,
        "unit": UnitOfVolume.LITERS,
        "state_class": SensorStateClass.MEASUREMENT,
        "value_fn": lambda d: _fuel_liters(d),
        "fuel_only": True,
    },
    {
        "key": "last_updated",
        "name": "Last updated",
        "icon": "mdi:clock-outline",
        "device_class": SensorDeviceClass.TIMESTAMP,
        "unit": None,
        "state_class": None,
        "value_fn": lambda d: d.get("last_updated"),
        "entity_category": EntityCategory.DIAGNOSTIC,
        "entity_registry_enabled_default": False,
    },
    {
        "key": "last_updated_fuel",
        "data_key": "fuel",
        "name": "Last updated (fuel)",
        "icon": "mdi:clock-outline",
        "device_class": SensorDeviceClass.TIMESTAMP,
        "unit": None,
        "state_class": None,
        "value_fn": lambda d: _parse_ts(_dig(d, "fuel", "fuelState", "updatedAt")),
        "fuel_only": True,
        "entity_category": EntityCategory.DIAGNOSTIC,
        "entity_registry_enabled_default": False,
    },
    {
        "key": "last_updated_location",
        "data_key": "location",
        "name": "Last updated (location)",
        "icon": "mdi:clock-outline",
        "device_class": SensorDeviceClass.TIMESTAMP,
        "unit": None,
        "state_class": None,
        "value_fn": lambda d: _parse_ts(_dig(d, "location", "vehicleLocation", "updatedAt")),
        "entity_category": EntityCategory.DIAGNOSTIC,
        "entity_registry_enabled_default": False,
    },
    {
        "key": "last_updated_climate",
        "data_key": "climate",
        "name": "Last updated (climate)",
        "icon": "mdi:clock-outline",
        "device_class": SensorDeviceClass.TIMESTAMP,
        "unit": None,
        "state_class": None,
        "value_fn": lambda d: _parse_ts(_dig(d, "climate", "updatedAt")),
        "entity_category": EntityCategory.DIAGNOSTIC,
        "entity_registry_enabled_default": False,
    },
]


def _dig(data, *keys):
    """Safely traverse nested dicts, tolerating None or missing keys at any level."""
    for key in keys:
        if not isinstance(data, dict):
            return None
        data = data.get(key)
    return data

def _pct(val):
    if val is not None:
        return round(val * 100, 1)
    return None

def _round(val):
    if val is not None:
        return round(val, 1)
    return None

def _lower(val):
    if val is not None:
        return str(val).lower()
    return None

def _heater_status(d, key):
    return _lower(_dig(d, "climate", "heaters", key, "status"))

def _battery_kwh(d):
    capacity = _dig(d, "metadata", "batteryInfo", "batteryCapacity")
    soc = _dig(d, "charge", "batteryState", "stateOfCharge")
    if capacity is not None and soc is not None:
        return round(capacity * soc, 1)
    return None

def _parse_ts(val):
    if val is None:
        return None
    if isinstance(val, datetime):
        return val
    try:
        return dt_util.parse_datetime(val)
    except (ValueError, TypeError):
        return None

def _fuel_liters(d):
    capacity = _dig(d, "metadata", "fuelInfo", "tankCapacity")
    pct = _dig(d, "fuel", "fuelState", "percentageOfRemainingFuel")
    if capacity is not None and pct is not None:
        return round(capacity * pct, 1)
    return None


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    entities = []
    for coordinator in data["coordinators"].values():
        is_bev = coordinator.propulsion == "BEV"
        heaters = _dig(coordinator.data, "climate", "heaters") or {}
        for sensor_type in SENSOR_TYPES:
            # Both inferable from the API: a BEV has no fuel state, and a heater
            # zone the car lacks is reported as null.
            if sensor_type.get("fuel_only") and is_bev:
                continue
            heater_key = sensor_type.get("heater_key")
            if heater_key and heaters.get(heater_key) is None:
                continue
            entities.append(LynkCoSensor(coordinator, sensor_type))
    async_add_entities(entities)


class LynkCoSensor(LynkCoEntity, SensorEntity):
    def __init__(self, coordinator: LynkCoCoordinator, sensor_type: dict) -> None:
        super().__init__(coordinator, sensor_type["key"], sensor_type.get("data_key"))
        self._sensor_type = sensor_type
        self._attr_icon = sensor_type["icon"]
        self._attr_device_class = sensor_type.get("device_class")
        self._attr_native_unit_of_measurement = sensor_type.get("unit")
        self._attr_state_class = sensor_type.get("state_class")
        if "entity_registry_enabled_default" in sensor_type:
            self._attr_entity_registry_enabled_default = sensor_type["entity_registry_enabled_default"]
        if "entity_category" in sensor_type:
            self._attr_entity_category = sensor_type["entity_category"]

    @property
    def native_value(self):
        if self.coordinator.data is None:
            return None
        return self._sensor_type["value_fn"](self.coordinator.data)
