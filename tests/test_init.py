"""Tests for the config entry setup: retries, reauth and one entry per car.

Home Assistant often boots before the network is up; the setup then has to
end in SETUP_RETRY (tried again with backoff) rather than failing until a
manual reload, and only a refresh token the token endpoint rejects for good
may send the user through the browser login again.

A car shared with a second Lynk & Co account is listed by both entries; the
entity unique ids are "<vin>_<key>", so only one entry may serve it.
"""

import logging
from collections.abc import Callable
from unittest.mock import AsyncMock, patch

import aiohttp
import pytest
from homeassistant.config_entries import SOURCE_REAUTH, ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import issue_registry as ir
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.lynkco.api import LynkCoAPI, LynkCoAuthError, LynkCoTransientError
from custom_components.lynkco.const import (
    CONF_ACCESS_TOKEN,
    CONF_DEVICE_ID,
    CONF_REFRESH_TOKEN,
    DOMAIN,
)

EMAIL = "user@example.com"
VIN = "TESTVIN0000000001"
VEHICLES = [{"vehicle": {"vin": VIN, "model": "E335"}}]
# every getter the first (full) poll calls
FULL_POLL_GETTERS = (
    "get_vehicle_data", "get_location", "get_charge_state", "get_climate_state",
    "get_doors_windows", "get_fuel_state", "get_vehicle_metadata",
)


def add_account(hass: HomeAssistant, make_token: Callable, email: str) -> MockConfigEntry:
    """A configured account with fake tokens, titled the way the config flow titles it."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=email,
        title=f"Lynk & Co ({email})",
        data={
            CONF_ACCESS_TOKEN: make_token({"email": email}),
            CONF_REFRESH_TOKEN: "refresh-token",
            CONF_DEVICE_ID: "device-id",
        },
    )
    entry.add_to_hass(hass)
    return entry


@pytest.fixture
def entry(hass: HomeAssistant, make_token: Callable) -> MockConfigEntry:
    """A configured account with fake tokens."""
    return add_account(hass, make_token, EMAIL)


def healthy_api(vehicles: list[dict]):
    """The API client of a reachable account that lists ``vehicles`` and answers every poll."""
    return patch.multiple(
        LynkCoAPI,
        validate_session=AsyncMock(return_value=True),
        get_vehicles=AsyncMock(return_value=vehicles),
        get_vehicle_guide=AsyncMock(return_value="E335_MORE"),
        **{getter: AsyncMock(return_value={}) for getter in FULL_POLL_GETTERS},
    )


@pytest.mark.parametrize(
    "error",
    [aiohttp.ClientConnectionError("network is down"), TimeoutError()],
    ids=["connection error", "timeout"],
)
async def test_unreachable_api_retries_the_setup(
    hass: HomeAssistant, entry: MockConfigEntry, error: Exception
) -> None:
    """No answer from the API: the setup is retried later and no new login is asked for."""
    with patch.object(LynkCoAPI, "validate_session", side_effect=error):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.SETUP_RETRY
    assert hass.config_entries.flow.async_progress_by_handler(DOMAIN) == []


async def test_transient_token_refresh_failure_retries_the_setup(
    hass: HomeAssistant, entry: MockConfigEntry
) -> None:
    """A session that needs a refresh while the token endpoint is down: retried, no new login."""
    with (
        patch.object(LynkCoAPI, "validate_session", return_value=False),
        patch.object(
            LynkCoAPI,
            "refresh_tokens",
            side_effect=LynkCoTransientError("Token refresh failed temporarily (503)"),
        ),
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.SETUP_RETRY
    assert hass.config_entries.flow.async_progress_by_handler(DOMAIN) == []


async def test_rejected_refresh_token_starts_the_reauth_flow(
    hass: HomeAssistant, entry: MockConfigEntry
) -> None:
    """A dead refresh token: the entry fails and Home Assistant asks for a new login."""
    with (
        patch.object(LynkCoAPI, "validate_session", return_value=False),
        patch.object(
            LynkCoAPI,
            "refresh_tokens",
            side_effect=LynkCoAuthError("The refresh token was rejected (400 invalid_grant)"),
        ),
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.SETUP_ERROR
    flows = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert [flow["context"]["source"] for flow in flows] == [SOURCE_REAUTH]
    assert flows[0]["context"]["entry_id"] == entry.entry_id


async def test_a_car_shared_with_a_second_account_is_served_once(
    hass: HomeAssistant, make_token: Callable, caplog: pytest.LogCaptureFixture
) -> None:
    """One car on two accounts: the first entry keeps it, the second skips it with a Repairs notice.

    A second entry serving the same car used to log "does not generate unique
    IDs" for every entity and to attach itself to the car's device. Unloading
    the first entry releases the car, so a reload of the second picks it up.
    """
    owner = add_account(hass, make_token, "owner@example.com")
    issues = ir.async_get(hass)

    with healthy_api(VEHICLES):
        await hass.config_entries.async_setup(owner.entry_id)
        await hass.async_block_till_done()

        # The car is shared with a second account, which is added later
        shared = add_account(hass, make_token, "shared@example.com")
        issue_id = f"duplicate_vehicle_{shared.entry_id}_{VIN}"
        await hass.config_entries.async_setup(shared.entry_id)
        await hass.async_block_till_done()

        assert owner.state is ConfigEntryState.LOADED
        assert shared.state is ConfigEntryState.LOADED
        assert VIN in hass.data[DOMAIN][owner.entry_id]["coordinators"]
        assert hass.data[DOMAIN][shared.entry_id]["coordinators"] == {}
        assert "does not generate unique IDs" not in caplog.text
        devices = dr.async_get(hass)
        assert len(devices.async_get_devices(identifiers={(DOMAIN, VIN)})) == 1
        assert devices.async_get_device_by_identifier((DOMAIN, VIN), owner.entry_id) is not None
        issue = issues.async_get_issue(DOMAIN, issue_id)
        assert issue is not None
        assert issue.translation_placeholders == {
            "vin": "***0001", "entry": shared.title, "other_entry": owner.title
        }
        warning = next(
            record.getMessage() for record in caplog.records
            if record.name == "custom_components.lynkco" and record.levelno == logging.WARNING
        )
        assert owner.title in warning and "***0001" in warning and VIN not in warning

        # Unloading the duplicate entry takes its notice with it
        assert await hass.config_entries.async_unload(shared.entry_id)
        await hass.async_block_till_done()
        assert issues.async_get_issue(DOMAIN, issue_id) is None

        # Once the owning entry is gone, the other account may serve the car
        assert await hass.config_entries.async_unload(owner.entry_id)
        await hass.config_entries.async_reload(shared.entry_id)
        await hass.async_block_till_done()

        assert shared.state is ConfigEntryState.LOADED
        assert VIN in hass.data[DOMAIN][shared.entry_id]["coordinators"]
        assert issues.async_get_issue(DOMAIN, issue_id) is None


async def test_concurrent_startup_gives_a_shared_car_to_one_entry(
    hass: HomeAssistant, make_token: Callable
) -> None:
    """Both accounts configured at startup: the entries are set up at once, one of them gets the car."""
    entries = [add_account(hass, make_token, f"{name}@example.com") for name in ("owner", "shared")]

    with healthy_api(VEHICLES):
        # Setting up the component sets up every entry of the domain concurrently
        assert await async_setup_component(hass, DOMAIN, {})
        await hass.async_block_till_done()

    assert all(entry.state is ConfigEntryState.LOADED for entry in entries)
    serving = [entry for entry in entries if VIN in hass.data[DOMAIN][entry.entry_id]["coordinators"]]
    assert len(serving) == 1
    skipped = next(entry for entry in entries if entry is not serving[0])
    assert hass.data[DOMAIN][skipped.entry_id]["coordinators"] == {}
    assert ir.async_get(hass).async_get_issue(DOMAIN, f"duplicate_vehicle_{skipped.entry_id}_{VIN}")
