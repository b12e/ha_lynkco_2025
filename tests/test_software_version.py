"""Tests for the software version: the sensor and the device page's firmware field."""

from collections.abc import Callable
from unittest.mock import AsyncMock, patch

import aiohttp
import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.lynkco.api import LynkCoAPI
from custom_components.lynkco.const import CONF_ACCESS_TOKEN, CONF_DEVICE_ID, CONF_REFRESH_TOKEN, DOMAIN

EMAIL = "user@example.com"
VIN = "TESTVIN0000000001"
OTHER_GETTERS = (
    "get_vehicle_data", "get_location", "get_charge_state",
    "get_climate_state", "get_doors_windows", "get_fuel_state",
)


def car(vehicle_metadata: dict):
    return patch.multiple(
        LynkCoAPI,
        validate_session=AsyncMock(return_value=True),
        get_vehicles=AsyncMock(return_value=[{"vehicle": {"vin": VIN, "model": "CX11_A3"}}]),
        get_vehicle_guide=AsyncMock(return_value="CX11_MORE"),
        get_vehicle_metadata=AsyncMock(return_value={"vehicle": vehicle_metadata}),
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


async def test_software_version_is_a_diagnostic_sensor_that_is_off_by_default(
    hass: HomeAssistant, entry: MockConfigEntry
) -> None:
    with car({"propulsionType": "PHEV", "softwareVersion": "1.4.4"}):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        registry = er.async_get(hass)
        entity_id = registry.async_get_entity_id("sensor", DOMAIN, f"{VIN}_software_version")
        reg_entry = registry.async_get(entity_id)
        assert reg_entry.disabled_by is er.RegistryEntryDisabler.INTEGRATION
        assert reg_entry.entity_category == "diagnostic"

        # Enabled by the user, it reports what the car says
        registry.async_update_entity(entity_id, disabled_by=None)
        await hass.config_entries.async_reload(entry.entry_id)
        await hass.async_block_till_done()
        assert hass.states.get(entity_id).state == "1.4.4"


async def test_no_software_version_sensor_for_a_car_that_does_not_report_one(
    hass: HomeAssistant, entry: MockConfigEntry
) -> None:
    with car({"propulsionType": "PHEV"}):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    assert er.async_get(hass).async_get_entity_id("sensor", DOMAIN, f"{VIN}_software_version") is None


def firmware(hass: HomeAssistant, entry: MockConfigEntry) -> str | None:
    """What the car's device page shows as firmware."""
    (device,) = dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id)
    return device.sw_version


async def test_device_page_shows_the_software_version_and_follows_an_update(
    hass: HomeAssistant, entry: MockConfigEntry
) -> None:
    with car({"propulsionType": "PHEV", "softwareVersion": "1.4.4"}):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        coordinator = hass.data[DOMAIN][entry.entry_id]["coordinators"][VIN]
        assert firmware(hass, entry) == "1.4.4"

        # The car was updated over the air: the next poll shows it, no restart needed
        LynkCoAPI.get_vehicle_metadata.return_value = {"vehicle": {"propulsionType": "PHEV", "softwareVersion": "1.5.0"}}
        await coordinator.async_refresh()
        assert firmware(hass, entry) == "1.5.0"

        # A poll in which the endpoint fails keeps the last known version
        LynkCoAPI.get_vehicle_metadata.side_effect = aiohttp.ClientConnectionError("network is down")
        await coordinator.async_refresh()
        assert firmware(hass, entry) == "1.5.0"


async def test_device_page_has_no_firmware_for_a_car_that_does_not_report_one(
    hass: HomeAssistant, entry: MockConfigEntry
) -> None:
    with car({"propulsionType": "PHEV"}):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    assert firmware(hass, entry) is None
