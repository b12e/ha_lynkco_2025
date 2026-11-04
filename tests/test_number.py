"""Tests for the charge limit number entity."""

from collections.abc import Callable
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.components.number import ATTR_VALUE, DOMAIN as NUMBER_DOMAIN, SERVICE_SET_VALUE
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.lynkco.api import LynkCoAPI
from custom_components.lynkco.const import CONF_ACCESS_TOKEN, CONF_DEVICE_ID, CONF_REFRESH_TOKEN, DOMAIN

EMAIL = "user@example.com"
VIN = "TESTVIN0000000001"
CHARGE_STATE = {"batteryState": {"chargeLimit": {"value": 90, "min": 50, "max": 100, "suggestedLimit": 90}}}
OTHER_GETTERS = (
    "get_vehicle_data", "get_location", "get_climate_state",
    "get_doors_windows", "get_vehicle_metadata", "get_fuel_state",
)


@pytest.fixture
def set_charge_limit() -> AsyncMock:
    return AsyncMock(return_value={})


def api(model: str, guide_type: str | None, set_charge_limit: AsyncMock):
    """A reachable account with one car of the given model."""
    return patch.multiple(
        LynkCoAPI,
        validate_session=AsyncMock(return_value=True),
        get_vehicles=AsyncMock(return_value=[{"vehicle": {"vin": VIN, "model": model}}]),
        get_vehicle_guide=AsyncMock(return_value=guide_type),
        get_charge_state=AsyncMock(return_value=dict(CHARGE_STATE)),
        set_charge_limit=set_charge_limit,
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


async def number_entity_ids(hass: HomeAssistant, entry: MockConfigEntry) -> list[str]:
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    registry = er.async_get(hass)
    return [
        reg_entry.entity_id
        for reg_entry in er.async_entries_for_config_entry(registry, entry.entry_id)
        if reg_entry.domain == NUMBER_DOMAIN
    ]


async def test_charge_limit_is_adjustable_within_the_range_the_car_reports(
    hass: HomeAssistant, entry: MockConfigEntry, set_charge_limit: AsyncMock
) -> None:
    with api("E335", "E335_MORE", set_charge_limit):
        (entity_id,) = await number_entity_ids(hass, entry)
        state = hass.states.get(entity_id)
        assert state.state == "90"
        assert state.attributes["min"] == 50
        assert state.attributes["max"] == 100
        assert state.attributes["step"] == 5
        assert state.attributes["unit_of_measurement"] == "%"

        await hass.services.async_call(
            NUMBER_DOMAIN, SERVICE_SET_VALUE, {ATTR_ENTITY_ID: entity_id, ATTR_VALUE: 80}, blocking=True
        )
        set_charge_limit.assert_awaited_once_with(VIN, 80)


async def test_no_charge_limit_entity_on_an_unconfirmed_model(
    hass: HomeAssistant, entry: MockConfigEntry, set_charge_limit: AsyncMock
) -> None:
    with api("XY99", None, set_charge_limit):
        assert await number_entity_ids(hass, entry) == []
