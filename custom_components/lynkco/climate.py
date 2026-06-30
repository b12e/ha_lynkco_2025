"""Climate platform for Lynk & Co integration."""

import logging

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER, MODEL_NAMES
from .coordinator import LynkCoCoordinator

_LOGGER = logging.getLogger(__name__)

DEFAULT_MIN_TEMP = 16
DEFAULT_MAX_TEMP = 28
DEFAULT_TARGET_TEMP = 21


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    entities = []
    for vin, coordinator in data["coordinators"].items():
        entities.append(LynkCoClimate(coordinator, data["api"]))
    async_add_entities(entities)


class LynkCoClimate(CoordinatorEntity, RestoreEntity, ClimateEntity):
    _attr_has_entity_name = True
    _attr_translation_key = "climate"
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_target_temperature_step = 1
    _attr_hvac_modes = [HVACMode.OFF, HVACMode.HEAT_COOL]
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.TURN_ON
        | ClimateEntityFeature.TURN_OFF
    )
    _enable_turn_on_off_backwards_compatibility = False

    def __init__(self, coordinator: LynkCoCoordinator, api) -> None:
        super().__init__(coordinator)
        self._api = api
        self._attr_unique_id = f"{coordinator.vin}_climate"
        # The API's targetTemperature reflects the in-car setting, not the
        # temperature sent with a remote start_conditioning, so we remember
        # the last value we set ourselves (restored across restarts below).
        self._target_temp: float | None = None

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state and last_state.attributes.get("temperature") is not None:
            try:
                self._target_temp = float(last_state.attributes["temperature"])
            except (ValueError, TypeError):
                self._target_temp = None

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
    def _climate(self) -> dict:
        if self.coordinator.data is None:
            return {}
        return self.coordinator.data.get("climate") or {}

    @property
    def current_temperature(self) -> float | None:
        return self._climate.get("interiorTemperature")

    @property
    def target_temperature(self) -> float | None:
        if self._target_temp is not None:
            return self._target_temp
        return self._climate.get("targetTemperature")

    @property
    def min_temp(self) -> float:
        return self._climate.get("minAvailableHvacTemperature") or DEFAULT_MIN_TEMP

    @property
    def max_temp(self) -> float:
        return self._climate.get("maxAvailableHvacTemperature") or DEFAULT_MAX_TEMP

    @property
    def hvac_mode(self) -> HVACMode | None:
        status = self._climate.get("status")
        if status is None:
            return None
        # Running states are ACTIVE_COOLING / ACTIVE_HEATING; everything else
        # (INACTIVE, DISABLED_UNLOCKED_CAR, DRIVE_MODE_ENABLED, ...) is off.
        if str(status).upper().startswith("ACTIVE"):
            return HVACMode.HEAT_COOL
        return HVACMode.OFF

    @property
    def hvac_action(self) -> HVACAction | None:
        status = self._climate.get("status")
        if status is None:
            return None
        status = str(status).upper()
        if "COOLING" in status:
            return HVACAction.COOLING
        if "HEATING" in status:
            return HVACAction.HEATING
        return HVACAction.OFF

    async def async_set_temperature(self, **kwargs) -> None:
        temp = kwargs.get(ATTR_TEMPERATURE)
        if temp is None:
            return
        _LOGGER.info("Setting climate temperature to %s for %s", temp, self.coordinator.vin)
        self._target_temp = float(temp)
        self.async_write_ha_state()
        await self._api.start_conditioning(self.coordinator.vin, int(round(temp)))
        self._refresh_climate()

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        if hvac_mode == HVACMode.OFF:
            await self.async_turn_off()
        else:
            await self.async_turn_on()

    async def async_turn_on(self) -> None:
        temp = self.target_temperature or DEFAULT_TARGET_TEMP
        _LOGGER.info("Starting climate for %s", self.coordinator.vin)
        await self._api.start_conditioning(self.coordinator.vin, int(round(temp)))
        self._refresh_climate()

    async def async_turn_off(self) -> None:
        _LOGGER.info("Stopping climate for %s", self.coordinator.vin)
        await self._api.stop_conditioning(self.coordinator.vin)
        self._refresh_climate()

    def _refresh_climate(self) -> None:
        self.hass.async_create_task(
            self.coordinator.async_targeted_refresh(
                "climate", lambda: self._api.get_climate_state(self.coordinator.vin)
            )
        )
