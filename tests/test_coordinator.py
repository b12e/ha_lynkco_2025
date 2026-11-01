"""Tests for the coordinator's fast poll (driving / climate active).

Regression test for issue #45: the fast poll used to call the API getters
without the VIN, so every fast-polled endpoint failed and its entities went
unavailable while driving or while the climate was running.
"""

from datetime import timedelta
from unittest.mock import create_autospec

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.lynkco.api import LynkCoAPI
from custom_components.lynkco.const import CONF_DRIVING_INTERVAL, DOMAIN
from custom_components.lynkco.coordinator import DATA_KEYS, LynkCoCoordinator
from custom_components.lynkco.features import resolve_features

VIN = "TESTVIN0000000001"

# data key -> API getter the fast poll has to call for it
GETTERS = {
    "vehicle_data": "get_vehicle_data",
    "location": "get_location",
    "charge": "get_charge_state",
    "climate": "get_climate_state",
}


def snapshot(driving: bool, climate: str) -> dict:
    """A full-poll result (every data key) in the given drive and climate state."""
    data = {key: {} for key in DATA_KEYS}
    data["vehicle_data"] = {"driveModeEnabled": driving}
    data["climate"] = {"status": climate}
    data["last_updated"] = dt_util.now()
    return data


def build_coordinator(hass: HomeAssistant, data: dict, options: dict | None = None) -> LynkCoCoordinator:
    """Coordinator holding ``data`` on top of a signature-checking API mock.

    ``create_autospec`` enforces the real getter signatures, so a getter
    awaited without the VIN raises TypeError just like the real client. Each
    getter returns the key's current value plus a ``fresh`` marker, which keeps
    the car driving and the climate active across ticks.
    """
    entry = MockConfigEntry(domain=DOMAIN, data={}, options=options or {})
    entry.add_to_hass(hass)
    api = create_autospec(LynkCoAPI, instance=True)
    for key, getter in GETTERS.items():
        getattr(api, getter).return_value = {**data[key], "fresh": True}
    coordinator = LynkCoCoordinator(
        hass, entry, api, VIN, "E335", "E335_MORE", resolve_features(None, "E335")
    )
    coordinator.data = data
    return coordinator


async def test_fast_poll_passes_vin_to_every_due_getter(hass: HomeAssistant) -> None:
    """Driving with climate active: all four endpoints are fetched with the VIN."""
    coordinator = build_coordinator(hass, snapshot(driving=True, climate="ACTIVE"))

    await coordinator._async_fast_poll(dt_util.utcnow())

    for key, getter in GETTERS.items():
        mock = getattr(coordinator.api, getter)
        mock.assert_awaited_once_with(VIN)
        assert coordinator.data[key] == mock.return_value
    assert coordinator.endpoint_errors == {}


async def test_fast_poll_is_idle_when_parked_with_climate_off(hass: HomeAssistant) -> None:
    """Nothing active: the fast poll does not touch the API."""
    coordinator = build_coordinator(hass, snapshot(driving=False, climate="INACTIVE"))

    await coordinator._async_fast_poll(dt_util.utcnow())

    for getter in GETTERS.values():
        getattr(coordinator.api, getter).assert_not_awaited()


async def test_fast_poll_cadence_follows_driving_interval(hass: HomeAssistant) -> None:
    """vehicle_data and climate poll every tick; location and charge wait for the driving interval."""
    coordinator = build_coordinator(
        hass, snapshot(driving=True, climate="ACTIVE"), options={CONF_DRIVING_INTERVAL: 5}
    )
    first_tick = dt_util.utcnow()

    await coordinator._async_fast_poll(first_tick)
    await coordinator._async_fast_poll(first_tick + timedelta(seconds=60))

    api = coordinator.api
    assert api.get_vehicle_data.await_count == 2
    assert api.get_climate_state.await_count == 2
    assert api.get_location.await_count == 1
    assert api.get_charge_state.await_count == 1
