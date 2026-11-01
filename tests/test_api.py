"""Tests for the API client: token refresh classification, the 401 retry, the 403 session re-claim and code extraction.

The client talks to the shared Home Assistant session, which the
``aioclient_mock`` fixture serves, so every test registers the answers of the
token endpoint and of the vehicle endpoint it needs.
"""

import asyncio
import logging
from collections.abc import Callable
from unittest.mock import Mock

import aiohttp
import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMocker,
    AiohttpClientMockResponse,
)

from custom_components.lynkco.api import LynkCoAPI, LynkCoAuthError, LynkCoTransientError
from custom_components.lynkco.const import IAM_BASE, LOGIN_B2C_URL, LOVE_BASE

VIN = "TESTVIN0000000001"
EMAIL = "user@example.com"
TOKEN_URL = f"{LOGIN_B2C_URL}oauth2/v2.0/token"
VEHICLE_DATA_URL = f"{LOVE_BASE}/vehicle/{VIN}/vehicle_data"
VEHICLE_DATA = {"driveModeEnabled": False}
LOCATION_URL = f"{LOVE_BASE}/vehicle/{VIN}/location_state"
LOCATION = {"vehicleUpdatedAt": "2026-11-01T12:00:00Z"}
VALIDATE_SESSION_URL = f"{IAM_BASE}/validate-session"
SESSION_TAKEN = "The Lynk & Co session was taken by another device (probably the phone app); claiming it back"

CODE = "eyJraWQiOiJjcGltY29yZV8wOTI1MjAxNSIsInZlciI6IjEuMCJ9.abc-DEF_123"
REDIRECT = f"msauth://prod.lynkco.app.crisp.prod/2jmj7l5rSw0yVb%2FvlWAYkK%2FYBwk%3D?code={CODE}"
# What the README's Firefox tip yields: the whole response-headers block
HEADER_BLOCK = (
    "HTTP/2 302\n"
    f"location: {REDIRECT}\n"
    "cache-control: no-store, must-revalidate, no-cache\n"
    "content-length: 0\n"
    "x-ms-gateway-requestid: 00000000-0000-0000-0000-000000000000\n"
)


@pytest.fixture(autouse=True)
def mock_response_content_length(monkeypatch: pytest.MonkeyPatch) -> None:
    """The mocked response lacks aiohttp's content_length, which the client reads before parsing."""
    monkeypatch.setattr(AiohttpClientMockResponse, "content_length", None, raising=False)


def build_api(hass: HomeAssistant, make_token: Callable, on_token_refresh=None) -> LynkCoAPI:
    """A client on the (mocked) shared session with a decodable access token."""
    return LynkCoAPI(
        async_get_clientsession(hass),
        make_token({"email": EMAIL}),
        "refresh-token",
        "device-id",
        on_token_refresh=on_token_refresh,
    )


def answers(*responses: dict) -> Callable:
    """A side effect answering each call with the next response; the last one repeats."""
    queue = list(responses)

    async def side_effect(method, url, data):
        kwargs = queue.pop(0) if len(queue) > 1 else queue[0]
        return AiohttpClientMockResponse(method, url, **kwargs)

    return side_effect


def methods(aioclient_mock: AiohttpClientMocker) -> list[str]:
    """The HTTP methods of every request made so far, in order."""
    return [call[0].upper() for call in aioclient_mock.mock_calls]


@pytest.mark.parametrize("status", [400, 401])
async def test_refresh_rejected_by_the_token_endpoint_is_an_auth_error(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    make_token: Callable,
    caplog: pytest.LogCaptureFixture,
    status: int,
) -> None:
    """A 4xx other than 429 means the refresh token is dead: the user has to log in again."""
    persisted = Mock()
    api = build_api(hass, make_token, on_token_refresh=persisted)
    token_before = api.access_token
    aioclient_mock.post(
        TOKEN_URL,
        status=status,
        json={
            "error": "invalid_grant",
            "error_description": "AADB2C90080: The provided grant has expired.",
        },
    )

    with caplog.at_level(logging.DEBUG):
        with pytest.raises(LynkCoAuthError) as excinfo:
            await api.refresh_tokens()

    assert "invalid_grant" in str(excinfo.value)
    assert api.access_token == token_before
    persisted.assert_not_called()
    # The B2C error fields are logged for debugging, the tokens never are.
    assert "AADB2C90080" in caplog.text
    assert "refresh-token" not in caplog.text
    assert token_before not in caplog.text


@pytest.mark.parametrize(
    "answer",
    [
        {"status": 503},
        {"status": 429, "json": {"error": "temporarily_unavailable"}},
        {"exc": TimeoutError()},
        {"exc": aiohttp.ClientConnectionError("connection reset")},
    ],
    ids=["503", "429", "timeout", "connection error"],
)
async def test_refresh_failing_temporarily_is_a_transient_error(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, make_token: Callable, answer: dict
) -> None:
    """429, 5xx, a timeout or a connection error: no reason to make the user log in again."""
    persisted = Mock()
    api = build_api(hass, make_token, on_token_refresh=persisted)
    token_before = api.access_token
    aioclient_mock.post(TOKEN_URL, **answer)

    with pytest.raises(LynkCoTransientError):
        await api.refresh_tokens()

    assert api.access_token == token_before
    persisted.assert_not_called()


async def test_401_is_retried_once_with_the_refreshed_token(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, make_token: Callable
) -> None:
    """An expired access token: refresh, retry the same request and return its data."""
    persisted = Mock()
    api = build_api(hass, make_token, on_token_refresh=persisted)
    new_token = make_token({"email": EMAIL, "refreshed": True})
    aioclient_mock.get(VEHICLE_DATA_URL, side_effect=answers({"status": 401}, {"json": VEHICLE_DATA}))
    aioclient_mock.post(TOKEN_URL, json={"access_token": new_token, "refresh_token": "new-refresh-token"})

    assert await api.get_vehicle_data(VIN) == VEHICLE_DATA

    assert api.access_token == new_token
    assert api.refresh_token == "new-refresh-token"
    persisted.assert_called_once_with(new_token, "new-refresh-token")
    assert methods(aioclient_mock) == ["GET", "POST", "GET"]
    retry_headers = aioclient_mock.mock_calls[-1][3]
    assert retry_headers["Authorization"] == f"Bearer {new_token}"


async def test_401_after_a_refresh_is_an_auth_error(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, make_token: Callable
) -> None:
    """The freshly refreshed token is rejected as well: nothing left to try but a new login."""
    api = build_api(hass, make_token)
    aioclient_mock.get(VEHICLE_DATA_URL, status=401)
    aioclient_mock.post(TOKEN_URL, json={"access_token": make_token({"email": EMAIL})})

    with pytest.raises(LynkCoAuthError):
        await api.get_vehicle_data(VIN)

    assert methods(aioclient_mock) == ["GET", "POST", "GET"]


async def test_concurrent_401s_share_one_token_refresh(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, make_token: Callable
) -> None:
    """Two requests rejected at the same time: the second retries with the first one's new token."""
    api = build_api(hass, make_token)
    aioclient_mock.post(
        TOKEN_URL,
        json={"access_token": make_token({"email": EMAIL, "refreshed": True})},
    )
    both_rejected = asyncio.Barrier(2)
    rejected = 0

    async def answer(method, url, data):
        nonlocal rejected
        if rejected < 2:
            rejected += 1
            await both_rejected.wait()  # neither request sees its 401 before both were sent
            return AiohttpClientMockResponse(method, url, status=401)
        return AiohttpClientMockResponse(method, url, json=VEHICLE_DATA)

    aioclient_mock.get(VEHICLE_DATA_URL, side_effect=answer)

    results = await asyncio.gather(api.get_vehicle_data(VIN), api.get_vehicle_data(VIN))

    assert results == [VEHICLE_DATA, VEHICLE_DATA]
    assert methods(aioclient_mock).count("POST") == 1


@pytest.mark.parametrize(
    "pasted",
    [
        REDIRECT,
        f"{REDIRECT}&state=abc",
        f"Location: {REDIRECT}",
        HEADER_BLOCK,
        HEADER_BLOCK.replace("\n", "\r\n"),
        f"code={CODE}",
    ],
    ids=["url", "url with more parameters", "location line", "header block", "crlf header block", "bare code"],
)
def test_extract_code_from_pasted_redirect(pasted: str) -> None:
    """The code comes out of whatever the user pasted, without trailing header lines."""
    assert LynkCoAPI.extract_code_from_url(pasted) == CODE


@pytest.mark.parametrize(
    "pasted",
    ["", "msauth://prod.lynkco.app.crisp.prod/x?error=access_denied", "HTTP/2 302\ncontent-length: 0\n"],
    ids=["empty", "error redirect", "headers without a location"],
)
def test_extract_code_without_a_code(pasted: str) -> None:
    assert LynkCoAPI.extract_code_from_url(pasted) is None


# --- Session re-claim after another device (the phone app) took the session ---


def validate_session_calls(aioclient_mock: AiohttpClientMocker) -> list[dict]:
    """The bodies of every validate-session POST made so far."""
    return [call[2] for call in aioclient_mock.mock_calls if str(call[1]) == VALIDATE_SESSION_URL]


async def test_403_on_a_working_endpoint_claims_the_session_back_and_retries(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    make_token: Callable,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The phone app logged in: one validate-session takes the session back, then the request is retried."""
    api = build_api(hass, make_token)
    aioclient_mock.get(
        VEHICLE_DATA_URL, side_effect=answers({"json": VEHICLE_DATA}, {"status": 403}, {"json": VEHICLE_DATA})
    )
    aioclient_mock.post(VALIDATE_SESSION_URL, json={"valid": True, "cccToken": "ccc-token"})

    assert await api.get_vehicle_data(VIN) == VEHICLE_DATA  # the endpoint works for this account
    assert await api.get_vehicle_data(VIN) == VEHICLE_DATA  # the phone app has logged in since

    assert methods(aioclient_mock) == ["GET", "GET", "POST", "GET"]
    assert validate_session_calls(aioclient_mock) == [{"deviceUuid": "device-id", "isLogin": True}]
    warnings = [record.getMessage() for record in caplog.records if record.levelno == logging.WARNING]
    assert warnings == [SESSION_TAKEN]


async def test_403s_within_the_interval_share_one_session_reclaim(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, make_token: Callable
) -> None:
    """Every endpoint of a poll answers 403 after a takeover: the first re-claims, the others only retry."""
    api = build_api(hass, make_token)
    aioclient_mock.get(
        VEHICLE_DATA_URL, side_effect=answers({"json": VEHICLE_DATA}, {"status": 403}, {"json": VEHICLE_DATA})
    )
    aioclient_mock.get(LOCATION_URL, side_effect=answers({"json": LOCATION}, {"status": 403}, {"json": LOCATION}))
    aioclient_mock.post(VALIDATE_SESSION_URL, json={"valid": True, "cccToken": "ccc-token"})

    assert await api.get_vehicle_data(VIN) == VEHICLE_DATA
    assert await api.get_location(VIN) == LOCATION
    # the phone app logs in
    assert await api.get_vehicle_data(VIN) == VEHICLE_DATA
    assert await api.get_location(VIN) == LOCATION

    assert methods(aioclient_mock) == ["GET", "GET", "GET", "POST", "GET", "GET", "GET"]
    assert len(validate_session_calls(aioclient_mock)) == 1


async def test_concurrent_403s_share_one_session_reclaim(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, make_token: Callable
) -> None:
    """Two requests rejected at the same time: one validate-session, both retries succeed."""
    api = build_api(hass, make_token)
    aioclient_mock.post(VALIDATE_SESSION_URL, json={"valid": True, "cccToken": "ccc-token"})
    both_rejected = asyncio.Barrier(2)
    calls = 0

    async def answer(method, url, data):
        nonlocal calls
        calls += 1
        if calls in (2, 3):
            await both_rejected.wait()  # neither request sees its 403 before both were sent
            return AiohttpClientMockResponse(method, url, status=403)
        return AiohttpClientMockResponse(method, url, json=VEHICLE_DATA)

    aioclient_mock.get(VEHICLE_DATA_URL, side_effect=answer)
    assert await api.get_vehicle_data(VIN) == VEHICLE_DATA  # the endpoint works for this account

    results = await asyncio.gather(api.get_vehicle_data(VIN), api.get_vehicle_data(VIN))

    assert results == [VEHICLE_DATA, VEHICLE_DATA]
    assert len(validate_session_calls(aioclient_mock)) == 1


async def test_403_on_an_endpoint_that_never_worked_is_raised_as_is(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, make_token: Callable
) -> None:
    """An endpoint the account may not use: no re-claim (it would log the phone out), just the error."""
    api = build_api(hass, make_token)
    aioclient_mock.get(VEHICLE_DATA_URL, status=403)
    aioclient_mock.post(VALIDATE_SESSION_URL, json={"valid": True, "cccToken": "ccc-token"})

    with pytest.raises(aiohttp.ClientResponseError) as excinfo:
        await api.get_vehicle_data(VIN)

    assert excinfo.value.status == 403
    assert methods(aioclient_mock) == ["GET"]


async def test_403_persisting_after_the_reclaim_is_raised_and_ends_the_reclaims(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    make_token: Callable,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Still 403 with the session back: the error is raised, and the endpoint only re-claims again once it worked again."""
    # No rate limit, so that the working set alone decides whether a 403 re-claims
    monkeypatch.setattr("custom_components.lynkco.api.SESSION_RECLAIM_INTERVAL", 0)
    api = build_api(hass, make_token)
    aioclient_mock.post(VALIDATE_SESSION_URL, json={"valid": True, "cccToken": "ccc-token"})
    aioclient_mock.get(
        VEHICLE_DATA_URL,
        side_effect=answers(
            {"json": VEHICLE_DATA},  # works for this account
            {"status": 403}, {"status": 403},  # taken, and still forbidden after the re-claim
            {"status": 403},  # later: raised straight away
            {"json": VEHICLE_DATA},  # permitted again
            {"status": 403}, {"json": VEHICLE_DATA},  # taken again: re-claimed again
        ),
    )

    assert await api.get_vehicle_data(VIN) == VEHICLE_DATA
    with pytest.raises(aiohttp.ClientResponseError) as excinfo:
        await api.get_vehicle_data(VIN)
    assert excinfo.value.status == 403
    assert methods(aioclient_mock) == ["GET", "GET", "POST", "GET"]

    with pytest.raises(aiohttp.ClientResponseError):
        await api.get_vehicle_data(VIN)
    assert methods(aioclient_mock)[4:] == ["GET"]  # no re-claim for an endpoint that stayed forbidden

    assert await api.get_vehicle_data(VIN) == VEHICLE_DATA
    assert await api.get_vehicle_data(VIN) == VEHICLE_DATA
    assert methods(aioclient_mock)[5:] == ["GET", "GET", "POST", "GET"]
    assert len(validate_session_calls(aioclient_mock)) == 2


@pytest.mark.parametrize(
    ("answer", "valid"),
    [
        ({"json": {"valid": True, "cccToken": "ccc-token"}}, True),
        ({"json": {"valid": False, "cccToken": None}}, False),
        ({}, True),
        ({"status": 401}, False),
    ],
    ids=["valid", "not valid", "no body", "401"],
)
async def test_validate_session_reads_the_valid_flag(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, make_token: Callable, answer: dict, valid: bool
) -> None:
    """A 200 means a valid session unless its body says otherwise; anything else does not."""
    api = build_api(hass, make_token)
    aioclient_mock.post(VALIDATE_SESSION_URL, **answer)

    assert await api.validate_session() is valid
