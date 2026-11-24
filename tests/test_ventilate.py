"""Tests for the ventilation and close windows actions and their live permission check."""

from collections.abc import Callable
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.lynkco.api import LynkCoAPI
from custom_components.lynkco.const import CONF_ACCESS_TOKEN, CONF_DEVICE_ID, CONF_REFRESH_TOKEN, DOMAIN
from custom_components.lynkco.coordinator import LynkCoCoordinator

EMAIL = "user@example.com"
VIN = "TESTVIN0000000001"
OTHER_GETTERS = (
    "get_vehicle_data", "get_location", "get_charge_state",
    "get_climate_state", "get_vehicle_metadata", "get_fuel_state",
)
# What a car reports in each state (seen on an 01 and an 02). The two "State"
# objects are about which action is available, not about the windows' position.
CLOSED = {"windowVentilateState": {"enabled": True}, "windowState": {"enabled": False}}
ONE_WINDOW_OPEN = {"windowVentilateState": {"enabled": True}, "windowState": {"enabled": True}}
VENTILATING = {"windowVentilateState": {"enabled": False}, "windowState": {"enabled": True}}


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


@pytest.fixture
def commands() -> dict[str, AsyncMock]:
    """The two remote commands, so tests can see what reached the API."""
    return {"start_ventilate": AsyncMock(return_value={}), "close_windows": AsyncMock(return_value={})}


def car(doors: dict, commands: dict[str, AsyncMock]):
    """A reachable account with one 02 whose doors endpoint reports ``doors``."""
    return patch.multiple(
        LynkCoAPI,
        validate_session=AsyncMock(return_value=True),
        get_vehicles=AsyncMock(return_value=[{"vehicle": {"vin": VIN, "model": "E335"}}]),
        get_vehicle_guide=AsyncMock(return_value="E335_MORE"),
        get_doors_windows=AsyncMock(return_value=doors),
        **commands,
        **{getter: AsyncMock(return_value={}) for getter in OTHER_GETTERS},
    )


async def call(hass: HomeAssistant, entry: MockConfigEntry, action: str) -> None:
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    # The follow-up refresh waits seconds between tries; it is not what is tested here
    with patch.object(LynkCoCoordinator, "async_targeted_refresh", AsyncMock()):
        await hass.services.async_call(DOMAIN, action, {}, blocking=True)
        await hass.async_block_till_done()


@pytest.mark.parametrize("doors", [VENTILATING, ONE_WINDOW_OPEN, CLOSED], ids=["ventilating", "one window open", "closed"])
async def test_close_windows_always_reaches_the_car(
    hass: HomeAssistant, entry: MockConfigEntry, commands: dict[str, AsyncMock], doors: dict
) -> None:
    # While ventilating the car reports that ventilation cannot be started;
    # that must not stop the windows from being closed again (issue 69)
    with car(doors, commands):
        await call(hass, entry, "close_windows")
    commands["close_windows"].assert_awaited_once_with(VIN)


async def test_the_stop_ventilate_action_is_gone(
    hass: HomeAssistant, entry: MockConfigEntry, commands: dict[str, AsyncMock]
) -> None:
    # The app dropped the car's ventilate_stop command for window_close, so
    # the action that sent it was replaced by close_windows
    with car(VENTILATING, commands):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    assert hass.services.has_service(DOMAIN, "close_windows")
    assert not hass.services.has_service(DOMAIN, "stop_ventilate")


@pytest.mark.parametrize("doors", [CLOSED, ONE_WINDOW_OPEN, {}], ids=["closed", "one window open", "nothing reported"])
async def test_start_ventilate_is_sent_when_the_car_allows_it(
    hass: HomeAssistant, entry: MockConfigEntry, commands: dict[str, AsyncMock], doors: dict
) -> None:
    with car(doors, commands):
        await call(hass, entry, "start_ventilate")
    commands["start_ventilate"].assert_awaited_once_with(VIN)


async def test_start_ventilate_is_refused_while_the_car_is_already_ventilating(
    hass: HomeAssistant, entry: MockConfigEntry, commands: dict[str, AsyncMock]
) -> None:
    with car(VENTILATING, commands):
        with pytest.raises(ServiceValidationError) as raised:
            await call(hass, entry, "start_ventilate")
    assert raised.value.translation_key == "action_not_permitted"
    commands["start_ventilate"].assert_not_awaited()
