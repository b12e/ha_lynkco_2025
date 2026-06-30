"""Button platform for Lynk & Co integration."""

import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, MANUFACTURER, MODEL_NAMES
from .coordinator import LynkCoCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    entities = []
    for vin, coordinator in data["coordinators"].items():
        entities.append(LynkCoRefreshButton(coordinator))
    async_add_entities(entities)


class LynkCoRefreshButton(ButtonEntity):
    """Button that forces an immediate data refresh.

    Deliberately not a CoordinatorEntity so it stays available even after a
    failed poll — that's exactly when a manual refresh is most useful.
    """

    _attr_has_entity_name = True
    _attr_translation_key = "refresh"
    _attr_icon = "mdi:refresh"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: LynkCoCoordinator) -> None:
        self.coordinator = coordinator
        self._attr_unique_id = f"{coordinator.vin}_refresh"

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self.coordinator.vin)},
            "name": MODEL_NAMES.get(self.coordinator.model, f"Lynk & Co {self.coordinator.model}"),
            "manufacturer": MANUFACTURER,
            "model": MODEL_NAMES.get(self.coordinator.model, self.coordinator.model),
            "serial_number": self.coordinator.vin,
        }

    async def async_press(self) -> None:
        _LOGGER.info("Manual refresh requested for %s", self.coordinator.vin)
        await self.coordinator.async_request_refresh()
