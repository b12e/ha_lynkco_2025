"""Shared entity base for the Lynk & Co integration."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import LynkCoCoordinator


class LynkCoEntity(CoordinatorEntity[LynkCoCoordinator]):
    """Coordinator entity tied to one API endpoint.

    ``_data_key`` names the coordinator data key (``charge``, ``climate``,
    ``doors``, ...) this entity reads. When that endpoint failed on the last
    poll the entity reports unavailable while entities fed by other endpoints
    keep working.
    """

    _attr_has_entity_name = True
    _data_key: str | None = None

    def __init__(self, coordinator: LynkCoCoordinator, key: str, data_key: str | None = None) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.vin}_{key}"
        self._attr_translation_key = key
        if data_key is not None:
            self._data_key = data_key

    @property
    def device_info(self) -> DeviceInfo:
        return self.coordinator.device_info

    @property
    def available(self) -> bool:
        if not super().available:
            return False
        return self._data_key is None or self._data_key not in self.coordinator.endpoint_errors
