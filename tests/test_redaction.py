"""Tests that the VIN stays out of log messages and stored endpoint errors.

aiohttp puts the request URL in the text of a ClientResponseError, and the
URL of every vehicle endpoint contains the VIN, so that text has to be
sanitized before it is logged, kept in ``endpoint_errors`` (which the
diagnostics download exports verbatim) or embedded in ``UpdateFailed``.
"""

import logging
from unittest.mock import create_autospec

import aiohttp
import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import UpdateFailed
from multidict import CIMultiDict, CIMultiDictProxy
from pytest_homeassistant_custom_component.common import MockConfigEntry
from yarl import URL

from custom_components.lynkco.api import LynkCoAPI, redact_vin
from custom_components.lynkco.const import DOMAIN
from custom_components.lynkco.coordinator import LynkCoCoordinator
from custom_components.lynkco.features import resolve_features

VIN = "TESTVIN000000ABCD"
REDACTED = "***ABCD"

# data key -> API getter the full poll calls for it
GETTERS = {
    "vehicle_data": "get_vehicle_data",
    "location": "get_location",
    "charge": "get_charge_state",
    "climate": "get_climate_state",
    "doors": "get_doors_windows",
    "fuel": "get_fuel_state",
    "metadata": "get_vehicle_metadata",
}


def response_error(endpoint: str) -> aiohttp.ClientResponseError:
    """A failed vehicle request as aiohttp raises it: the VIN sits in the URL and the message."""
    url = URL(f"https://example.invalid/vehicle/{VIN}/{endpoint}")
    request_info = aiohttp.RequestInfo(
        url=url, method="GET", headers=CIMultiDictProxy(CIMultiDict()), real_url=url
    )
    return aiohttp.ClientResponseError(
        request_info, (), status=500, message=f"Internal server error for {VIN}"
    )


def build_coordinator(hass: HomeAssistant) -> LynkCoCoordinator:
    """Coordinator without data on top of an API mock whose getters all succeed."""
    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.add_to_hass(hass)
    api = create_autospec(LynkCoAPI, instance=True)
    for key, getter in GETTERS.items():
        getattr(api, getter).return_value = {key: True}
    return LynkCoCoordinator(
        hass, entry, api, VIN, "E335", "E335_MORE", resolve_features(None, "E335")
    )


@pytest.mark.parametrize(
    ("vin", "expected"),
    [(VIN, REDACTED), ("", "***"), ("ABC", "***")],
)
def test_redact_vin_keeps_only_the_last_four_characters(vin: str, expected: str) -> None:
    assert redact_vin(vin) == expected


async def test_endpoint_error_is_logged_and_stored_without_the_vin(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    """One getter fails with the VIN in its URL and message; the other endpoints still deliver."""
    coordinator = build_coordinator(hass)
    coordinator.api.get_charge_state.side_effect = response_error("charge_state")
    assert coordinator.log_vin == REDACTED

    with caplog.at_level(logging.DEBUG):
        data = await coordinator._async_fetch_all()

    assert data is not None
    assert set(coordinator.endpoint_errors) == {"charge"}
    for error in coordinator.endpoint_errors.values():
        assert VIN not in error
        # Only the VIN is replaced; the rest of the message stays intact.
        assert f"Internal server error for {REDACTED}" in error
        assert f"/vehicle/{REDACTED}/charge_state" in error
    assert f"Lynk & Co endpoint charge failed for {REDACTED}" in caplog.text
    assert VIN not in caplog.text


async def test_repeat_failure_and_recovery_log_the_redacted_vin(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    """The 'still failing' debug line and the 'recovered' info line use the redacted VIN too."""
    coordinator = build_coordinator(hass)
    coordinator.api.get_charge_state.side_effect = response_error("charge_state")

    with caplog.at_level(logging.DEBUG):
        await coordinator._async_fetch_all()
        await coordinator._async_fetch_all()
        coordinator.api.get_charge_state.side_effect = None
        await coordinator._async_fetch_all()

    assert coordinator.endpoint_errors == {}
    assert f"Lynk & Co endpoint charge still failing for {REDACTED}" in caplog.text
    assert f"Lynk & Co endpoint charge recovered for {REDACTED}" in caplog.text
    assert VIN not in caplog.text


async def test_failed_refresh_keeps_the_vin_out_of_update_failed_and_the_log(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    """Every endpoint fails: UpdateFailed and Home Assistant's own error line inherit the sanitized text."""
    coordinator = build_coordinator(hass)
    coordinator.api.refresh_tokens.return_value = True
    for key, getter in GETTERS.items():
        getattr(coordinator.api, getter).side_effect = response_error(key)

    with caplog.at_level(logging.DEBUG):
        with pytest.raises(UpdateFailed) as excinfo:
            await coordinator._async_update_data()
        await coordinator.async_refresh()

    assert coordinator.last_update_success is False
    assert VIN not in str(excinfo.value)
    assert REDACTED in str(excinfo.value)
    # Home Assistant logs the coordinator name on a failed poll, so it must not carry the VIN either.
    assert f"Error fetching {DOMAIN}_{REDACTED} data" in caplog.text
    assert VIN not in caplog.text
