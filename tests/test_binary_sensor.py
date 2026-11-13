"""Tests for the door, window, hood, trunk and sunroof sensors."""

from collections.abc import Callable
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.lynkco.api import LynkCoAPI
from custom_components.lynkco.binary_sensor import _is_open
from custom_components.lynkco.const import CONF_ACCESS_TOKEN, CONF_DEVICE_ID, CONF_REFRESH_TOKEN, DOMAIN

EMAIL = "user@example.com"
VIN = "TESTVIN0000000001"
OTHER_GETTERS = (
    "get_vehicle_data", "get_location", "get_charge_state",
    "get_climate_state", "get_vehicle_metadata", "get_fuel_state",
)


@pytest.mark.parametrize(
    ("value", "expected"),
    [("OPEN", True), ("CLOSED", False), ("UNKNOWN", None), (None, None), ("SOMETHING_NEW", None)],
)
def test_only_open_and_closed_say_anything(value, expected) -> None:
    assert _is_open(value) is expected


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


async def test_an_opening_the_car_cannot_tell_is_unknown_rather_than_open(
    hass: HomeAssistant, entry: MockConfigEntry
) -> None:
    doors = {
        "hoodStatus": "UNKNOWN",
        "trunkStatus": "OPEN",
        # a group is open as soon as one known opening is; the unknown one stays visible
        "doorFrontLeftStatus": "UNKNOWN", "doorFrontRightStatus": "CLOSED",
        "doorRearLeftStatus": "CLOSED", "doorRearRightStatus": "CLOSED",
        # nothing known at all
        "windowFrontLeftStatus": "UNKNOWN", "windowFrontRightStatus": "UNKNOWN",
        "windowRearLeftStatus": "UNKNOWN", "windowRearRightStatus": "UNKNOWN",
    }
    with patch.multiple(
        LynkCoAPI,
        validate_session=AsyncMock(return_value=True),
        get_vehicles=AsyncMock(return_value=[{"vehicle": {"vin": VIN, "model": "DX11"}}]),
        get_vehicle_guide=AsyncMock(return_value="DX11_MORE"),
        get_doors_windows=AsyncMock(return_value=doors),
        **{getter: AsyncMock(return_value={}) for getter in OTHER_GETTERS},
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    registry = er.async_get(hass)

    def state(key: str):
        return hass.states.get(registry.async_get_entity_id("binary_sensor", DOMAIN, f"{VIN}_{key}"))

    assert state("hood").state == "unknown"
    assert state("trunk").state == "on"
    assert state("doors").state == "off"
    assert state("doors").attributes["front_left"] == "unknown"
    assert state("windows").state == "unknown"
