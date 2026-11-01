"""Tests for the coordinator's fast poll (driving / climate active) and its error handling.

Regression test for issue #45: the fast poll used to call the API getters
without the VIN, so every fast-polled endpoint failed and its entities went
unavailable while driving or while the climate was running. The bug stayed
hidden because every exception from a getter was recorded as an API failure,
so the second half checks what is isolated per endpoint and what propagates,
and that the fast poll pauses after a failed full poll and never overlaps.
"""

import asyncio
from datetime import timedelta
from unittest.mock import create_autospec

import aiohttp
import pytest
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import UpdateFailed
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.lynkco.api import LynkCoAPI, LynkCoAuthError, LynkCoTransientError
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
# every getter the full poll calls
FULL_POLL_GETTERS = (*GETTERS.values(), "get_doors_windows", "get_fuel_state", "get_vehicle_metadata")


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


async def test_fast_poll_pauses_while_the_last_full_poll_failed(hass: HomeAssistant) -> None:
    """A pending login or a failed backstop poll: the fast poll leaves the API alone until it recovers."""
    coordinator = build_coordinator(hass, snapshot(driving=True, climate="ACTIVE"))
    coordinator.last_update_success = False

    await coordinator._async_fast_poll(dt_util.utcnow())

    for getter in GETTERS.values():
        getattr(coordinator.api, getter).assert_not_awaited()

    coordinator.last_update_success = True
    await coordinator._async_fast_poll(dt_util.utcnow())

    for getter in GETTERS.values():
        getattr(coordinator.api, getter).assert_awaited_once_with(VIN)


async def test_fast_poll_ticks_do_not_overlap(hass: HomeAssistant) -> None:
    """A tick that fires while the previous one is still waiting for the API is skipped."""
    coordinator = build_coordinator(hass, snapshot(driving=True, climate="ACTIVE"))
    api = coordinator.api
    release = asyncio.Event()

    async def slow_vehicle_data(vin: str) -> dict:
        await release.wait()
        return {"driveModeEnabled": True, "fresh": True}

    api.get_vehicle_data.side_effect = slow_vehicle_data
    first_tick = dt_util.utcnow()

    first = hass.async_create_task(coordinator._async_fast_poll(first_tick))
    await asyncio.sleep(0)  # the first tick is now waiting for vehicle_data
    await coordinator._async_fast_poll(first_tick + timedelta(seconds=60))
    assert api.get_climate_state.await_count == 0  # the second tick did nothing

    release.set()
    await first

    for getter in GETTERS.values():
        getattr(api, getter).assert_awaited_once_with(VIN)


@pytest.mark.parametrize(
    "error",
    [
        aiohttp.ClientConnectionError("connection reset"),
        TimeoutError(),
        ValueError("not JSON"),
        LynkCoTransientError("Token refresh failed temporarily (503)"),
    ],
    ids=lambda error: type(error).__name__,
)
async def test_api_failure_in_a_getter_is_recorded(hass: HomeAssistant, error: Exception) -> None:
    """Unreachable, timed out, a malformed body or a failed token refresh: only this endpoint fails."""
    coordinator = build_coordinator(hass, snapshot(driving=False, climate="INACTIVE"))
    coordinator.api.get_charge_state.side_effect = error

    value = await coordinator._fetch_endpoint("charge", lambda: coordinator.api.get_charge_state(VIN))

    assert value is None
    assert set(coordinator.endpoint_errors) == {"charge"}
    assert coordinator.endpoint_errors["charge"]  # a message even for an empty TimeoutError


async def test_programming_error_in_a_getter_propagates(hass: HomeAssistant) -> None:
    """Anything that is not an API failure is a bug and must surface, not count as an outage."""
    coordinator = build_coordinator(hass, snapshot(driving=False, climate="INACTIVE"))
    coordinator.api.get_charge_state.side_effect = TypeError("missing 1 required positional argument: 'vin'")

    with pytest.raises(TypeError):
        await coordinator._fetch_endpoint("charge", lambda: coordinator.api.get_charge_state(VIN))

    assert coordinator.endpoint_errors == {}


async def test_failed_full_poll_with_a_transient_refresh_error_is_update_failed(hass: HomeAssistant) -> None:
    """Every endpoint down and the token endpoint too: this cycle fails, no new login is asked for."""
    coordinator = build_coordinator(hass, snapshot(driving=False, climate="INACTIVE"))
    for getter in FULL_POLL_GETTERS:
        getattr(coordinator.api, getter).side_effect = aiohttp.ClientConnectionError("network is down")
    coordinator.api.refresh_tokens.side_effect = LynkCoTransientError("Token refresh failed temporarily (503)")

    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()


async def test_failed_full_poll_with_a_rejected_refresh_token_is_auth_failed(hass: HomeAssistant) -> None:
    """Every endpoint failing because the session is dead: Home Assistant asks for a new login."""
    coordinator = build_coordinator(hass, snapshot(driving=False, climate="INACTIVE"))
    for getter in FULL_POLL_GETTERS:
        getattr(coordinator.api, getter).side_effect = aiohttp.ClientConnectionError("network is down")
    coordinator.api.refresh_tokens.side_effect = LynkCoAuthError("The refresh token was rejected (400 invalid_grant)")

    with pytest.raises(ConfigEntryAuthFailed):
        await coordinator._async_update_data()
