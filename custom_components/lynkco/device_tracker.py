"""Device tracker platform for Lynk & Co integration."""

from homeassistant.components.device_tracker import SourceType
from homeassistant.components.device_tracker.config_entry import TrackerEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER, MODEL_NAMES
from .coordinator import LynkCoCoordinator


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    entities = []
    for vin, coordinator in data["coordinators"].items():
        entities.append(LynkCoDeviceTracker(coordinator))
    async_add_entities(entities)


class LynkCoDeviceTracker(CoordinatorEntity, TrackerEntity):
    _attr_has_entity_name = True
    _attr_translation_key = "location"
    _attr_icon = "mdi:car"

    def __init__(self, coordinator: LynkCoCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.vin}_location"

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
    def source_type(self) -> SourceType:
        return SourceType.GPS

    @property
    def latitude(self) -> float | None:
        if self.coordinator.data is None:
            return None
        loc = self.coordinator.data.get("location", {}).get("vehicleLocation", {})
        coords = loc.get("coordinates", {})
        return coords.get("latitude")

    @property
    def longitude(self) -> float | None:
        if self.coordinator.data is None:
            return None
        loc = self.coordinator.data.get("location", {}).get("vehicleLocation", {})
        coords = loc.get("coordinates", {})
        return coords.get("longitude")
