"""Tests for the climate entity: native temperature API and unit handling."""

import importlib
from collections.abc import Callable
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.components.climate import ClimateEntity
from homeassistant.components.climate.const import DOMAIN as CLIMATE_DOMAIN, SERVICE_SET_TEMPERATURE
from homeassistant.const import ATTR_ENTITY_ID, ATTR_TEMPERATURE
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers import entity_registry as er
from homeassistant.util.unit_system import US_CUSTOMARY_SYSTEM
from pytest_homeassistant_custom_component.common import MockConfigEntry, mock_restore_cache

from custom_components.lynkco import climate as climate_module
from custom_components.lynkco.api import LynkCoAPI
from custom_components.lynkco.const import CONF_ACCESS_TOKEN, CONF_DEVICE_ID, CONF_REFRESH_TOKEN, DOMAIN

EMAIL = "user@example.com"
VIN = "TESTVIN0000000001"
VEHICLES = [{"vehicle": {"vin": VIN, "model": "E335"}}]
# The car reports and accepts Celsius, whatever unit the Home Assistant instance shows.
CLIMATE_STATE = {
    "status": "ACTIVE_HEATING",
    "interiorTemperature": 21.5,
    "targetTemperature": 22,
    "minAvailableHvacTemperature": 16,
    "maxAvailableHvacTemperature": 28,
}
OTHER_GETTERS = (
    "get_vehicle_data", "get_location", "get_charge_state",
    "get_doors_windows", "get_vehicle_metadata", "get_fuel_state",
)


@pytest.fixture
def start_conditioning() -> AsyncMock:
    """The patched remote command, so tests can read what was sent to the car."""
    return AsyncMock(return_value={})


@pytest.fixture
def api(start_conditioning: AsyncMock):
    """A reachable account with one car whose climate is heating."""
    with patch.multiple(
        LynkCoAPI,
        validate_session=AsyncMock(return_value=True),
        get_vehicles=AsyncMock(return_value=VEHICLES),
        get_vehicle_guide=AsyncMock(return_value="E335_MORE"),
        get_climate_state=AsyncMock(return_value=dict(CLIMATE_STATE)),
        start_conditioning=start_conditioning,
        **{getter: AsyncMock(return_value={}) for getter in OTHER_GETTERS},
    ):
        yield


@pytest.fixture
def entry(hass: HomeAssistant, make_token: Callable) -> MockConfigEntry:
    """A configured account with fake tokens."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=EMAIL,
        title=f"Lynk & Co ({EMAIL})",
        data={
            CONF_ACCESS_TOKEN: make_token({"email": EMAIL}),
            CONF_REFRESH_TOKEN: "refresh-token",
            CONF_DEVICE_ID: "device-id",
        },
    )
    entry.add_to_hass(hass)
    return entry


async def set_up(hass: HomeAssistant, entry: MockConfigEntry) -> str:
    """Set the entry up and return the climate entity id."""
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    registry = er.async_get(hass)
    return next(
        reg_entry.entity_id
        for reg_entry in er.async_entries_for_config_entry(registry, entry.entry_id)
        if reg_entry.domain == CLIMATE_DOMAIN
    )


@pytest.mark.usefixtures("api")
async def test_reports_the_car_temperatures(hass: HomeAssistant, entry: MockConfigEntry, caplog) -> None:
    entity_id = await set_up(hass, entry)
    state = hass.states.get(entity_id)
    assert state.state == "heat_cool"
    assert state.attributes["hvac_action"] == "heating"
    assert state.attributes["current_temperature"] == 21.5
    assert state.attributes[ATTR_TEMPERATURE] == 22
    assert state.attributes["min_temp"] == 16
    assert state.attributes["max_temp"] == 28
    assert "deprecated" not in caplog.text


@pytest.mark.usefixtures("api")
async def test_converts_to_and_from_fahrenheit_on_a_us_instance(
    hass: HomeAssistant, entry: MockConfigEntry, start_conditioning: AsyncMock
) -> None:
    hass.config.units = US_CUSTOMARY_SYSTEM
    entity_id = await set_up(hass, entry)
    state = hass.states.get(entity_id)
    # Celsius from the car, shown in whole degrees Fahrenheit
    assert state.attributes["current_temperature"] == 71
    assert state.attributes[ATTR_TEMPERATURE] == 72
    assert state.attributes["min_temp"] == 61
    assert state.attributes["max_temp"] == 82

    await hass.services.async_call(
        CLIMATE_DOMAIN,
        SERVICE_SET_TEMPERATURE,
        {ATTR_ENTITY_ID: entity_id, ATTR_TEMPERATURE: 73.4},
        blocking=True,
    )
    # 73.4 F is 23 C: the car gets Celsius
    start_conditioning.assert_awaited_once_with(VIN, 23)


@pytest.mark.usefixtures("api")
@pytest.mark.parametrize(
    ("saved", "expected"),
    [
        ({ATTR_TEMPERATURE: 73.4, "temperature_unit": "°F"}, 23.0),  # unit recorded by newer Home Assistant
        ({ATTR_TEMPERATURE: 22.5}, 22.5),  # older state: the instance's own unit, metric here
    ],
    ids=["fahrenheit with unit", "metric without unit"],
)
async def test_restores_the_target_temperature_in_celsius(
    hass: HomeAssistant, entry: MockConfigEntry, saved: dict, expected: float
) -> None:
    entity_id = await set_up(hass, entry)
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()

    mock_restore_cache(hass, (State(entity_id, "off", saved),))
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).attributes[ATTR_TEMPERATURE] == expected


def test_legacy_temperature_members_exist_only_without_the_native_api(monkeypatch) -> None:
    """Old names only where Home Assistant lacks native_*, so no version logs a deprecation."""
    has_native = hasattr(ClimateEntity, "native_temperature_unit")
    members = vars(climate_module.LynkCoClimate)
    assert "native_current_temperature" in members
    assert "native_target_temperature" in members
    assert ("current_temperature" in members) is (not has_native)
    assert ("target_temperature" in members) is (not has_native)
    assert ("_attr_temperature_unit" in members) is (not has_native)

    if has_native:
        return
    # Pretend the native API is there and check the old names disappear.
    monkeypatch.setattr(ClimateEntity, "native_temperature_unit", None, raising=False)
    try:
        reloaded = importlib.reload(climate_module)
        assert "current_temperature" not in vars(reloaded.LynkCoClimate)
        assert "_attr_temperature_unit" not in vars(reloaded.LynkCoClimate)
        assert "native_current_temperature" in vars(reloaded.LynkCoClimate)
    finally:
        monkeypatch.undo()
        importlib.reload(climate_module)
