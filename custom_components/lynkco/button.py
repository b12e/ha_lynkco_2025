"""Button platform for Lynk & Co integration."""

import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import LynkCoCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    entities = []
    for coordinator in data["coordinators"].values():
        entities.append(LynkCoRefreshButton(coordinator))
        # Not inferable from the API: only on models where it is confirmed to work
        if coordinator.action_enabled("request_location"):
            entities.append(LynkCoRequestLocationButton(coordinator))
    async_add_entities(entities)


class LynkCoButton(ButtonEntity):
    """Base for the integration's buttons.

    Deliberately not a CoordinatorEntity so buttons stay available even after a
    failed poll - that's exactly when they're most useful.
    """

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _key: str

    def __init__(self, coordinator: LynkCoCoordinator) -> None:
        self.coordinator = coordinator
        self._attr_unique_id = f"{coordinator.vin}_{self._key}"
        self._attr_translation_key = self._key

    @property
    def device_info(self) -> DeviceInfo:
        return self.coordinator.device_info


class LynkCoRefreshButton(LynkCoButton):
    """Button that forces an immediate data refresh."""

    _attr_icon = "mdi:refresh"
    _key = "refresh"

    async def async_press(self) -> None:
        _LOGGER.info("Manual refresh requested for %s", self.coordinator.vin)
        await self.coordinator.async_request_refresh()


class LynkCoRequestLocationButton(LynkCoButton):
    """Button that asks the vehicle to report a fresh position."""

    _attr_icon = "mdi:crosshairs-gps"
    _key = "request_location"

    async def async_press(self) -> None:
        self.coordinator.require_action("request_location")
        _LOGGER.info("Location update requested for %s", self.coordinator.vin)
        await self.coordinator.api.request_location(self.coordinator.vin)
        # The car acknowledges immediately but pushes the position a few seconds
        # later, so chase it in the background instead of blocking the press.
        self.hass.async_create_task(
            self.coordinator.async_targeted_refresh(
                "location", lambda: self.coordinator.api.get_location(self.coordinator.vin)
            )
        )
