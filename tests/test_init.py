"""Tests for the config entry setup: retry while the API is unreachable, reauth once the session is dead.

Home Assistant often boots before the network is up; the setup then has to
end in SETUP_RETRY (tried again with backoff) rather than failing until a
manual reload, and only a refresh token the token endpoint rejects for good
may send the user through the browser login again.
"""

from collections.abc import Callable
from unittest.mock import patch

import aiohttp
import pytest
from homeassistant.config_entries import SOURCE_REAUTH, ConfigEntryState
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.lynkco.api import LynkCoAPI, LynkCoAuthError, LynkCoTransientError
from custom_components.lynkco.const import (
    CONF_ACCESS_TOKEN,
    CONF_DEVICE_ID,
    CONF_REFRESH_TOKEN,
    DOMAIN,
)

EMAIL = "user@example.com"


@pytest.fixture
def entry(hass: HomeAssistant, make_token: Callable) -> MockConfigEntry:
    """A configured account with fake tokens."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=EMAIL,
        data={
            CONF_ACCESS_TOKEN: make_token({"email": EMAIL}),
            CONF_REFRESH_TOKEN: "refresh-token",
            CONF_DEVICE_ID: "device-id",
        },
    )
    entry.add_to_hass(hass)
    return entry


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
