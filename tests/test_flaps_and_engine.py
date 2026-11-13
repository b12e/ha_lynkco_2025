"""Tests for the flap sensors, the engine status sensor and the per-endpoint timestamps."""

from collections.abc import Callable
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.lynkco.api import LynkCoAPI
from custom_components.lynkco.const import CONF_ACCESS_TOKEN, CONF_DEVICE_ID, CONF_REFRESH_TOKEN, DOMAIN
from custom_components.lynkco.sensor import CLIMATE_ENGINE_STATUS_OPTIONS, _climate_engine_status

EMAIL = "user@example.com"
VIN = "TESTVIN0000000001"
UPDATED_AT = "2026-11-13T10:15:00+00:00"
OTHER_GETTERS = ("get_vehicle_data", "get_location", "get_fuel_state")


def api(model: str, guide_type: str, propulsion: str, doors: dict, climate: dict):
    """A reachable account with one car of the given model and payloads."""
    return patch.multiple(
        LynkCoAPI,
        validate_session=AsyncMock(return_value=True),
        get_vehicles=AsyncMock(return_value=[{"vehicle": {"vin": VIN, "model": model}}]),
        get_vehicle_guide=AsyncMock(return_value=guide_type),
        get_vehicle_metadata=AsyncMock(return_value={"vehicle": {"propulsionType": propulsion}}),
        get_doors_windows=AsyncMock(return_value=doors),
        get_climate_state=AsyncMock(return_value=climate),
        get_charge_state=AsyncMock(return_value={"batteryState": {"updatedAt": UPDATED_AT}}),
        **{getter: AsyncMock(return_value={}) for getter in OTHER_GETTERS},
    )


@pytest.fixture
def entry(hass: HomeAssistant, make_token: Callable) -> MockConfigEntry:
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


async def set_up(hass: HomeAssistant, entry: MockConfigEntry) -> er.EntityRegistry:
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return er.async_get(hass)


def entity_id(registry: er.EntityRegistry, platform: str, key: str) -> str | None:
    return registry.async_get_entity_id(platform, DOMAIN, f"{VIN}_{key}")


async def test_08_gets_both_flaps(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    doors = {"tankFlapStatus": "CLOSED", "chargeLidStatus": "OPEN", "updatedAt": UPDATED_AT}
    with api("DX11", "DX11_MORE", "PHEV", doors, {"engineStatus": "OFF"}):
        registry = await set_up(hass, entry)
        assert hass.states.get(entity_id(registry, "binary_sensor", "fuel_flap")).state == "off"
        charge_flap = hass.states.get(entity_id(registry, "binary_sensor", "charge_flap"))
        assert charge_flap.state == "on"
        assert charge_flap.attributes["device_class"] == "door"


async def test_01_without_a_charge_lid_sensor_only_gets_the_fuel_flap(
    hass: HomeAssistant, entry: MockConfigEntry
) -> None:
    doors = {"tankFlapStatus": "CLOSED", "chargeLidStatus": None}
    with api("CX11_A3", "CX11_MORE", "PHEV", doors, {"engineStatus": "OFF"}):
        registry = await set_up(hass, entry)
        assert entity_id(registry, "binary_sensor", "fuel_flap") is not None
        assert entity_id(registry, "binary_sensor", "charge_flap") is None


@pytest.mark.parametrize(
    ("model", "guide_type"),
    [("CX11_A3", "CX11_MORE"), ("CX11_A1", "CX11_2023"), ("XY99", "XY99_MORE")],
    ids=["01", "pre-2025 01", "unknown model"],
)
async def test_charge_flap_follows_the_api_on_any_model(
    hass: HomeAssistant, entry: MockConfigEntry, model: str, guide_type: str
) -> None:
    # Whether the car has the sensor is read from the payload, not from the model
    doors = {"tankFlapStatus": "CLOSED", "chargeLidStatus": "CLOSED"}
    with api(model, guide_type, "PHEV", doors, {"engineStatus": "OFF"}):
        registry = await set_up(hass, entry)
        assert hass.states.get(entity_id(registry, "binary_sensor", "charge_flap")).state == "off"


async def test_02_gets_its_charge_flap_but_no_fuel_flap_or_climate_engine_status(
    hass: HomeAssistant, entry: MockConfigEntry
) -> None:
    doors = {"tankFlapStatus": "CLOSED", "chargeLidStatus": "CLOSED"}
    with api("E335", "E335_MORE", "BEV", doors, {"engineStatus": "NOT_APPLICABLE"}):
        registry = await set_up(hass, entry)
        assert entity_id(registry, "binary_sensor", "charge_flap") is not None
        assert entity_id(registry, "binary_sensor", "fuel_flap") is None
        assert entity_id(registry, "sensor", "climate_engine_status") is None


async def test_02_without_a_charge_lid_sensor_gets_no_flaps(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    with api("E335", "E335_MORE", "BEV", {"chargeLidStatus": None}, {}):
        registry = await set_up(hass, entry)
        assert entity_id(registry, "binary_sensor", "charge_flap") is None
        assert entity_id(registry, "binary_sensor", "fuel_flap") is None


@pytest.mark.parametrize(
    ("climate", "expected"),
    [
        ({"engineStatus": "RUNNING", "status": "ACTIVE_HEATING"}, "started"),
        ({"engineStatus": "RUNNING", "status": "DRIVE_MODE_ENABLED", "isEngineStartedWhenActive": False}, "started"),
        ({"engineStatus": "OFF", "status": "ACTIVE_HEATING", "isEngineStartedWhenActive": True}, "not_started"),
        ({"engineStatus": "OFF", "status": "INACTIVE", "isEngineStartedWhenActive": True}, "will_start"),
        ({"engineStatus": "OFF", "status": "INACTIVE", "isEngineStartedWhenActive": False}, "will_not_start"),
        ({"engineStatus": "OFF", "status": "INACTIVE"}, "not_started"),  # no forecast reported
        ({"engineStatus": "NOT_APPLICABLE", "status": "INACTIVE"}, None),
        ({"engineStatus": "UNKNOWN"}, None),
        ({}, None),
    ],
)
def test_climate_engine_status_combines_the_engine_state_with_the_forecast(climate, expected) -> None:
    assert _climate_engine_status({"climate": climate}) == expected
    assert expected is None or expected in CLIMATE_ENGINE_STATUS_OPTIONS
    assert _climate_engine_status({"climate": None}) is None


async def test_climate_engine_status_entity_on_a_hybrid(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    climate = {
        "engineStatus": "OFF", "status": "INACTIVE",
        "isEngineStartedWhenActive": False, "engineStartingForLowBattery": True,
    }
    with api("DX11", "DX11_MORE", "PHEV", {}, climate):
        registry = await set_up(hass, entry)
        state = hass.states.get(entity_id(registry, "sensor", "climate_engine_status"))
        assert state.state == "will_not_start"
        assert state.attributes["options"] == CLIMATE_ENGINE_STATUS_OPTIONS
        assert state.attributes["starts_when_climate_active"] is False
        assert state.attributes["starts_for_low_battery"] is True


@pytest.mark.parametrize("climate", [{"status": "INACTIVE"}, {"engineStatus": "NOT_APPLICABLE"}])
async def test_no_climate_engine_status_entity_when_the_car_has_none_to_report(
    hass: HomeAssistant, entry: MockConfigEntry, climate: dict
) -> None:
    with api("CX11_A1", "CX11_2023", "PHEV", {}, climate):
        registry = await set_up(hass, entry)
        assert entity_id(registry, "sensor", "climate_engine_status") is None


async def test_a_flap_the_car_cannot_tell_is_unknown_rather_than_open(
    hass: HomeAssistant, entry: MockConfigEntry
) -> None:
    doors = {"tankFlapStatus": "UNKNOWN", "chargeLidStatus": "UNKNOWN", "hoodStatus": "UNKNOWN"}
    with api("DX11", "DX11_MORE", "PHEV", doors, {"engineStatus": "OFF"}):
        registry = await set_up(hass, entry)
        for key in ("fuel_flap", "charge_flap", "hood"):
            assert hass.states.get(entity_id(registry, "binary_sensor", key)).state == "unknown", key


async def test_door_and_charging_timestamps_are_diagnostic_and_off_by_default(
    hass: HomeAssistant, entry: MockConfigEntry
) -> None:
    with api("DX11", "DX11_MORE", "PHEV", {"updatedAt": UPDATED_AT}, {"engineStatus": "OFF"}):
        registry = await set_up(hass, entry)
        for key in ("last_updated_doors", "last_updated_charging"):
            reg_entry = registry.async_get(entity_id(registry, "sensor", key))
            assert reg_entry.disabled_by is er.RegistryEntryDisabler.INTEGRATION, key
            assert reg_entry.entity_category == "diagnostic", key

        # Enabled by the user, they report the timestamp of their endpoint
        for key in ("last_updated_doors", "last_updated_charging"):
            registry.async_update_entity(entity_id(registry, "sensor", key), disabled_by=None)
        await hass.config_entries.async_reload(entry.entry_id)
        await hass.async_block_till_done()
        for key in ("last_updated_doors", "last_updated_charging"):
            assert hass.states.get(entity_id(registry, "sensor", key)).state == UPDATED_AT, key
