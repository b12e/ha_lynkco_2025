"""Sensor platform for Lynk & Co integration."""

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfEnergy, UnitOfLength, UnitOfPower, UnitOfTemperature, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER, MODEL_NAMES
from .coordinator import LynkCoCoordinator


SENSOR_TYPES: list[dict] = [
    {
        "key": "battery_level",
        "name": "Battery level",
        "icon": "mdi:battery",
        "device_class": SensorDeviceClass.BATTERY,
        "unit": PERCENTAGE,
        "state_class": SensorStateClass.MEASUREMENT,
        "value_fn": lambda d: _pct(d.get("charge", {}).get("batteryState", {}).get("stateOfCharge")),
    },
    {
        "key": "battery_range",
        "name": "Electric range",
        "icon": "mdi:map-marker-distance",
        "device_class": SensorDeviceClass.DISTANCE,
        "unit": UnitOfLength.KILOMETERS,
        "state_class": SensorStateClass.MEASUREMENT,
        "value_fn": lambda d: d.get("charge", {}).get("batteryState", {}).get("remainingRange"),
    },
    {
        "key": "charging_status",
        "name": "Charging status",
        "icon": "mdi:ev-station",
        "device_class": SensorDeviceClass.ENUM,
        "unit": None,
        "state_class": None,
        "value_fn": lambda d: _lower(d.get("charge", {}).get("batteryState", {}).get("status")),
    },
    {
        "key": "charging_speed",
        "name": "Charging speed",
        "icon": "mdi:flash",
        "device_class": SensorDeviceClass.POWER,
        "unit": UnitOfPower.KILO_WATT,
        "state_class": SensorStateClass.MEASUREMENT,
        "value_fn": lambda d: (d.get("charge", {}).get("batteryState", {}).get("chargingSpeed") or {}).get("kW"),
    },
    {
        "key": "charging_time_remaining",
        "name": "Charging time remaining",
        "icon": "mdi:timer-sand",
        "device_class": SensorDeviceClass.DURATION,
        "unit": UnitOfTime.MINUTES,
        "state_class": SensorStateClass.MEASUREMENT,
        "value_fn": lambda d: d.get("charge", {}).get("batteryState", {}).get("remainingChargingTime"),
    },
    {
        "key": "charge_limit",
        "name": "Charge limit",
        "icon": "mdi:battery-lock",
        "device_class": None,
        "unit": PERCENTAGE,
        "state_class": SensorStateClass.MEASUREMENT,
        "value_fn": lambda d: (d.get("charge", {}).get("batteryState", {}).get("chargeLimit") or {}).get("value"),
    },
    {
        "key": "interior_temperature",
        "name": "Interior temperature",
        "icon": "mdi:thermometer",
        "device_class": SensorDeviceClass.TEMPERATURE,
        "unit": UnitOfTemperature.CELSIUS,
        "state_class": SensorStateClass.MEASUREMENT,
        "value_fn": lambda d: d.get("climate", {}).get("interiorTemperature"),
    },
    {
        "key": "target_temperature",
        "name": "Target temperature",
        "icon": "mdi:thermometer-auto",
        "device_class": SensorDeviceClass.TEMPERATURE,
        "unit": UnitOfTemperature.CELSIUS,
        "state_class": SensorStateClass.MEASUREMENT,
        "value_fn": lambda d: d.get("climate", {}).get("targetTemperature"),
    },
    {
        "key": "climate_status",
        "name": "Climate status",
        "icon": "mdi:air-conditioner",
        "device_class": SensorDeviceClass.ENUM,
        "unit": None,
        "state_class": None,
        "value_fn": lambda d: _lower(d.get("climate", {}).get("status")),
    },
    {
        "key": "lock_status",
        "name": "Central lock",
        "icon": "mdi:car-door-lock",
        "device_class": SensorDeviceClass.ENUM,
        "unit": None,
        "state_class": None,
        "value_fn": lambda d: _lower(d.get("vehicle_data", {}).get("centralLock", {}).get("status")),
    },
    {
        "key": "address",
        "name": "Address",
        "icon": "mdi:map-marker",
        "device_class": None,
        "unit": None,
        "state_class": None,
        "value_fn": lambda d: (d.get("location", {}).get("vehicleLocation") or {}).get("longAddress"),
    },
    {
        "key": "fuel_level",
        "name": "Fuel level",
        "icon": "mdi:gas-station",
        "device_class": None,
        "unit": PERCENTAGE,
        "state_class": SensorStateClass.MEASUREMENT,
        "value_fn": lambda d: _pct(d.get("fuel", {}).get("fuelState", {}).get("percentageOfRemainingFuel")),
        "fuel_only": True,
    },
    {
        "key": "fuel_range",
        "name": "Fuel range",
        "icon": "mdi:gas-station-outline",
        "device_class": SensorDeviceClass.DISTANCE,
        "unit": UnitOfLength.KILOMETERS,
        "state_class": SensorStateClass.MEASUREMENT,
        "value_fn": lambda d: d.get("fuel", {}).get("fuelState", {}).get("remainingRange"),
        "fuel_only": True,
    },
    {
        "key": "fuel_consumption",
        "name": "Average fuel consumption",
        "icon": "mdi:fuel",
        "device_class": None,
        "unit": "L/100km",
        "state_class": SensorStateClass.MEASUREMENT,
        "value_fn": lambda d: d.get("fuel", {}).get("fuelState", {}).get("averageConsumption"),
        "fuel_only": True,
    },
    {
        "key": "fuel_type",
        "name": "Fuel type",
        "icon": "mdi:gas-station",
        "device_class": SensorDeviceClass.ENUM,
        "unit": None,
        "state_class": None,
        "value_fn": lambda d: _lower(d.get("fuel", {}).get("fuelInfo", {}).get("fuelType")),
        "fuel_only": True,
    },
    {
        "key": "odometer",
        "name": "Odometer",
        "icon": "mdi:counter",
        "device_class": SensorDeviceClass.DISTANCE,
        "unit": UnitOfLength.KILOMETERS,
        "state_class": SensorStateClass.TOTAL_INCREASING,
        "value_fn": lambda d: d.get("metadata", {}).get("vehicle", {}).get("odometer"),
    },
    {
        "key": "battery_capacity",
        "name": "Battery capacity",
        "icon": "mdi:battery-high",
        "device_class": None,
        "unit": UnitOfEnergy.KILO_WATT_HOUR,
        "state_class": SensorStateClass.MEASUREMENT,
        "value_fn": lambda d: _round(d.get("metadata", {}).get("batteryInfo", {}).get("batteryCapacity")),
    },
    {
        "key": "battery_energy",
        "name": "Battery energy",
        "icon": "mdi:battery-charging",
        "device_class": None,
        "unit": UnitOfEnergy.KILO_WATT_HOUR,
        "state_class": SensorStateClass.MEASUREMENT,
        "value_fn": lambda d: _battery_kwh(d),
    },
]


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

def _battery_kwh(d):
    capacity = d.get("metadata", {}).get("batteryInfo", {}).get("batteryCapacity")
    soc = d.get("charge", {}).get("batteryState", {}).get("stateOfCharge")
    if capacity is not None and soc is not None:
        return round(capacity * soc, 1)
    return None


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    entities = []
    for vin, coordinator in data["coordinators"].items():
        is_bev = coordinator.propulsion == "BEV"
        for sensor_type in SENSOR_TYPES:
            if sensor_type.get("fuel_only") and is_bev:
                continue
            entities.append(LynkCoSensor(coordinator, sensor_type))
    async_add_entities(entities)


class LynkCoSensor(CoordinatorEntity, SensorEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator: LynkCoCoordinator, sensor_type: dict) -> None:
        super().__init__(coordinator)
        self._sensor_type = sensor_type
        self._attr_unique_id = f"{coordinator.vin}_{sensor_type['key']}"
        self._attr_name = sensor_type["name"]
        self._attr_icon = sensor_type["icon"]
        self._attr_device_class = sensor_type.get("device_class")
        self._attr_native_unit_of_measurement = sensor_type.get("unit")
        self._attr_state_class = sensor_type.get("state_class")

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
    def native_value(self):
        if self.coordinator.data is None:
            return None
        return self._sensor_type["value_fn"](self.coordinator.data)
