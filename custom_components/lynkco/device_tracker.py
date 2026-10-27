"""Device tracker platform for Lynk & Co integration."""

from homeassistant.components.device_tracker import SourceType, TrackerEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import LynkCoCoordinator, dig
from .entity import LynkCoEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    entities = []
    for coordinator in data["coordinators"].values():
        entities.append(LynkCoDeviceTracker(coordinator))
    async_add_entities(entities)


class LynkCoDeviceTracker(LynkCoEntity, TrackerEntity):
    _data_key = "location"
    _attr_icon = "mdi:car"

    def __init__(self, coordinator: LynkCoCoordinator) -> None:
        super().__init__(coordinator, "location")

    @property
    def source_type(self) -> SourceType:
        return SourceType.GPS

    def _coordinates(self) -> dict:
        return dig(self.coordinator.data, "location", "vehicleLocation", "coordinates") or {}

    @property
    def latitude(self) -> float | None:
        return self._coordinates().get("latitude")

    @property
    def longitude(self) -> float | None:
        return self._coordinates().get("longitude")
