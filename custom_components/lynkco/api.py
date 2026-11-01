"""API client for Lynk & Co vehicles."""

import asyncio
import hashlib
import json
import logging
import re
import time
import urllib.parse
import uuid

import aiohttp
import pkce

from .const import (
    API_BASE,
    CLIENT_ID,
    COMMAND_BASE,
    IAM_BASE,
    LOGIN_B2C_URL,
    LOVE_BASE,
    REDIRECT_URI,
    SCOPE,
    SIGNATURE_BASE_URLS,
    SIGNATURE_VERSION,
    TENANT,
)

_LOGGER = logging.getLogger(__name__)

# Every request gives up after this long instead of hanging on a stalled connection
REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=30)

# A 403 on an endpoint that worked before means another device took over the
# account's single session; one re-claim covers every 403 in this many seconds
SESSION_RECLAIM_INTERVAL = 60

# The authorization code in a pasted redirect ends at the next query parameter
# or at whitespace, so a whole pasted response-headers block works as well
_CODE_IN_URL = re.compile(r"[?&]code=([^&\s]+)")
_BARE_CODE = re.compile(r"^\s*code=([^&\s]+)")  # just "code=..." pasted

# Lower-cased fragments of JSON keys whose values never reach the debug log.
REDACT_KEY_PARTS = (
    "token",
    "authorization",
    "password",
    "secret",
    "vin",
    "email",
    "address",
    "latitude",
    "longitude",
    "coordinate",
    "customer",
    "snowflake",
    "device",
    "temid",
    "registrationnumber",
    "vehiclename",
)


class LynkCoAuthError(Exception):
    """The session is no longer valid and the refresh token was rejected.

    Raised instead of a plain HTTP error so the integration can ask Home
    Assistant to start the re-authentication flow (Settings > Repairs).
    """


class LynkCoTransientError(Exception):
    """A token refresh failed for a reason that does not call for a new login.

    The token endpoint could not be reached, timed out or answered 429 or 5xx:
    the refresh token may well still be valid, so the caller should try again
    later instead of sending the user through the browser login (which also
    logs their phone out of the official app).
    """


def redact(value: object, key: str = "") -> object:
    """Return a copy of an API payload with sensitive values replaced."""
    if any(part in key.lower() for part in REDACT_KEY_PARTS):
        return "<redacted>"
    if isinstance(value, dict):
        return {name: redact(item, str(name)) for name, item in value.items()}
    if isinstance(value, list):
        return [redact(item, key) for item in value]
    return value


def redact_vin(vin: str) -> str:
    """Return the VIN as log messages may show it: "***" plus its last four characters.

    Enough to tell the cars of a multi-car account apart without identifying
    the vehicle. An empty or shorter value comes back as just "***".
    """
    if not vin or len(vin) < 4:
        return "***"
    return f"***{vin[-4:]}"


def _compute_signature(secret: str, nonce: str, path: str) -> str:
    return hashlib.sha256((secret + nonce + path).encode("utf-8")).hexdigest()


def _extract_path(url: str) -> str:
    for base in SIGNATURE_BASE_URLS:
        if url.startswith(base):
            relative = url[len(base):]
            return "/" + relative.lstrip("/")
    parsed = urllib.parse.urlparse(url)
    return parsed.path


def _decode_jwt_claims(token: str) -> dict:
    import base64
    payload = token.split(".")[1]
    payload += "=" * (4 - len(payload) % 4)
    return json.loads(base64.urlsafe_b64decode(payload))


class LynkCoAPI:
    """Handles communication with the Lynk & Co API."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        access_token: str,
        refresh_token: str,
        device_id: str,
        on_token_refresh: callable | None = None,
    ) -> None:
        self._session = session
        self._access_token = access_token
        self._refresh_token = refresh_token
        self._device_id = device_id
        self._on_token_refresh = on_token_refresh
        self._refresh_lock = asyncio.Lock()  # one token refresh or session re-claim at a time
        # Paths that answered 2xx before: a 403 on one of them means the session
        # went to another device, see _request. The time of the last re-claim
        # keeps the other 403s of the same poll from repeating it.
        self._working_paths: set[str] = set()
        self._last_reclaim: float | None = None
        self._claims: dict = {}
        self._update_claims()

    def _update_claims(self) -> None:
        try:
            self._claims = _decode_jwt_claims(self._access_token)
        except Exception:
            _LOGGER.exception("Failed to decode JWT claims")
            self._claims = {}

    @property
    def customer_number(self) -> str:
        return self._claims.get("customerNumber", "")

    @property
    def snowflake_id(self) -> str:
        return self._claims.get("snowflakeId", "")

    @property
    def user_email(self) -> str:
        return self._claims.get("email", "")

    @property
    def access_token(self) -> str:
        return self._access_token

    @property
    def refresh_token(self) -> str:
        return self._refresh_token

    @property
    def device_id(self) -> str:
        return self._device_id

    def _build_headers(self, url: str) -> dict:
        nonce = str(uuid.uuid4())
        path = _extract_path(url)
        sig = _compute_signature(self.snowflake_id, nonce, path)

        return {
            "Authorization": f"Bearer {self._access_token}",
            "X-Auth-Token": self._access_token,
            "X-DeviceId": self._device_id,
            "X-CustomerNumber": self.customer_number,
            "X-CustomerId": self.snowflake_id,
            "User-Agent": "Android",
            "api-version": "1",
            "X-NONCE": nonce,
            "X-SIGNATURE-VERSION": SIGNATURE_VERSION,
            "X-SIGNATURE": sig,
            "X-App-Name": "Lynk&Co",
            "X-App-Version": "2.67.0",
            "X-App-Build-Number": "8455",
            "X-Device-OS-Version": "14",
            "X-Device-Model": "Pixel 8",
            "X-Device-Language": "en",
            "Content-Type": "application/json",
        }

    async def _request(self, method: str, url: str, **kwargs) -> dict:
        token = self._access_token
        path = _extract_path(url)
        headers = self._build_headers(url)
        async with self._session.request(
            method, url, headers=headers, timeout=REQUEST_TIMEOUT, **kwargs
        ) as resp:
            # A 403 on an endpoint that worked before means the session went to
            # another device; on any other endpoint it is raised as is, since a
            # re-claim would log that device out at every poll
            taken = resp.status == 403 and path in self._working_paths
            if resp.status != 401 and not taken:
                return await self._read_json(url, resp)

        if taken:
            await self._reclaim_session()
        else:
            _LOGGER.debug("Got 401, attempting token refresh")
            async with self._refresh_lock:
                # Another task may have refreshed the token while this request was
                # in flight or while waiting for the lock: then a retry is enough.
                if self._access_token == token:
                    await self._refresh_tokens_locked()
        headers = self._build_headers(url)
        async with self._session.request(
            method, url, headers=headers, timeout=REQUEST_TIMEOUT, **kwargs
        ) as retry:
            if retry.status == 401 and not taken:
                raise LynkCoAuthError("Still unauthorized after refreshing the token")
            if retry.status == 403 and taken:
                # Still forbidden with the session back: this endpoint is simply
                # not permitted for the account, so stop re-claiming for it. A new
                # login would not help either; the coordinator isolates the endpoint.
                self._working_paths.discard(path)
            return await self._read_json(url, retry)

    async def _read_json(self, url: str, resp: aiohttp.ClientResponse) -> dict:
        """Return the JSON body of a successful response ({} for an empty one)."""
        resp.raise_for_status()
        self._working_paths.add(_extract_path(url))  # a later 403 here is a takeover, see _request
        if resp.content_length == 0:
            return {}
        data = await resp.json()
        self._log_response(url, data)
        return data if data is not None else {}

    @staticmethod
    def _log_response(url: str, data: object) -> None:
        if _LOGGER.isEnabledFor(logging.DEBUG):
            _LOGGER.debug("API response %s: %s", _extract_path(url), redact(data))

    async def refresh_tokens(self) -> bool:
        """Trade the refresh token for a new token pair; True once they are in place.

        A refresh that fails raises instead: LynkCoAuthError when the token
        endpoint rejects the refresh token for good (a 4xx other than 429;
        Azure B2C answers 400 invalid_grant for an expired or revoked one), so
        the user has to log in again, or LynkCoTransientError when the endpoint
        could not be reached, timed out or answered 429 or 5xx, which is no
        reason for a new login.
        """
        async with self._refresh_lock:
            return await self._refresh_tokens_locked()

    async def _refresh_tokens_locked(self) -> bool:
        """refresh_tokens for a caller that already holds the refresh lock."""
        url = f"{LOGIN_B2C_URL}oauth2/v2.0/token"
        try:
            async with self._session.post(
                url,
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                data={
                    "client_id": CLIENT_ID,
                    "grant_type": "refresh_token",
                    "refresh_token": self._refresh_token,
                    "scope": SCOPE,
                    "redirect_uri": REDIRECT_URI,
                },
                timeout=REQUEST_TIMEOUT,
            ) as resp:
                if resp.status != 200:
                    error = await self._log_token_error(resp)
                    if 400 <= resp.status < 500 and resp.status != 429:
                        detail = f"{resp.status} {error}".strip()
                        raise LynkCoAuthError(f"The refresh token was rejected ({detail})")
                    raise LynkCoTransientError(f"Token refresh failed temporarily ({resp.status})")
                data = await resp.json()
        except (aiohttp.ClientError, TimeoutError) as err:
            raise LynkCoTransientError(
                f"Token endpoint not reachable: {str(err) or type(err).__name__}"
            ) from err
        self._access_token = data["access_token"]
        self._refresh_token = data.get("refresh_token", self._refresh_token)
        self._update_claims()
        _LOGGER.debug("Tokens refreshed successfully")
        if self._on_token_refresh:
            self._on_token_refresh(self._access_token, self._refresh_token)
        return True

    @staticmethod
    async def _log_token_error(resp: aiohttp.ClientResponse) -> str:
        """Log the B2C error fields of a failed token answer at debug level; returns the error code.

        Only "error" and "error_description" are read from the body, never a token.
        """
        try:
            body = await resp.json(content_type=None)
        except (aiohttp.ClientError, ValueError):
            body = None
        if not isinstance(body, dict):
            _LOGGER.debug("Token endpoint answered %d without a JSON body", resp.status)
            return ""
        error = str(body.get("error") or "")
        _LOGGER.debug(
            "Token endpoint answered %d: %s (%s)",
            resp.status, error or "no error code", body.get("error_description") or "",
        )
        return error

    async def _reclaim_session(self) -> None:
        """Claim the account's single device session back from the device that took it.

        Lynk & Co keeps one device session per account: when the phone app logs
        in, it takes the session and every endpoint answers 403 for this client
        until validate-session (which the setup also calls before the first
        poll) claims it back, logging the phone out again. Refreshing the tokens
        does not help, they are still valid. One re-claim per
        SESSION_RECLAIM_INTERVAL serves every 403 of a poll: the other requests
        only retry, and concurrent 403s wait for the lock instead of each
        calling validate-session.
        """
        async with self._refresh_lock:
            if (
                self._last_reclaim is not None
                and time.monotonic() - self._last_reclaim < SESSION_RECLAIM_INTERVAL
            ):
                return
            _LOGGER.warning(
                "The Lynk & Co session was taken by another device (probably the phone app); "
                "claiming it back"
            )
            await self.validate_session()
            self._last_reclaim = time.monotonic()

    async def validate_session(self) -> bool:
        """Claim the account's device session for this client; True when the session is valid.

        The official app makes this call at every start. A 200 whose body (the
        app's ValidateSessionResponse: "valid" and "cccToken") says the session
        is not valid counts as False; a 200 without a readable body counts as
        valid. Network errors propagate.
        """
        url = f"{IAM_BASE}/validate-session"
        headers = self._build_headers(url)
        async with self._session.post(
            url,
            headers=headers,
            json={"deviceUuid": self._device_id, "isLogin": True},
            timeout=REQUEST_TIMEOUT,
        ) as resp:
            if resp.status != 200:
                return False
            try:
                body = await resp.json(content_type=None)
            except (aiohttp.ClientError, ValueError):
                body = None
            if isinstance(body, dict) and body.get("valid") is False:
                _LOGGER.debug("validate-session answered 200 but reports the session as not valid")
                return False
            return True

    async def get_vehicles(self) -> list[dict]:
        url = f"{LOVE_BASE}/list/vehicles"
        data = await self._request("GET", url)
        return data.get("listOfVehicles", [])

    async def get_vehicle_data(self, vin: str) -> dict:
        return await self._request("GET", f"{LOVE_BASE}/vehicle/{vin}/vehicle_data")

    async def get_location(self, vin: str) -> dict:
        return await self._request("GET", f"{LOVE_BASE}/vehicle/{vin}/location_state")

    async def get_charge_state(self, vin: str) -> dict:
        return await self._request("GET", f"{LOVE_BASE}/vehicle/{vin}/charge_state")

    async def get_climate_state(self, vin: str) -> dict:
        return await self._request("GET", f"{LOVE_BASE}/vehicle/{vin}/climate_state")

    async def get_doors_windows(self, vin: str) -> dict:
        return await self._request(
            "GET", f"{LOVE_BASE}/vehicle/{vin}/doors_windows_state"
        )

    async def get_vehicle_metadata(self, vin: str) -> dict:
        return await self._request("GET", f"{LOVE_BASE}/vehicle/{vin}/vehicle_metadata")

    async def get_fuel_state(self, vin: str) -> dict:
        return await self._request("GET", f"{LOVE_BASE}/vehicle/{vin}/fuel_state")

    async def get_vehicle_guide(self, vin: str) -> str | None:
        """Return the car guide type, the most precise identity the API offers.

        Pre-2025 01s report their model year (CX11_2021_PHEV, CX11_2022,
        CX11_2023); newer cars report their equipment level (CX11_MORE,
        E335_CORE, DX11_MORE, ...).
        """
        data = await self._request("GET", f"{LOVE_BASE}/vehicle/{vin}/vehicle_guide")
        guide_type = data.get("type")
        return str(guide_type) if guide_type else None

    async def lock_door(self, vin: str) -> dict:
        return await self._request(
            "POST", f"{COMMAND_BASE}/vehicle/{vin}/command/door_lock"
        )

    async def unlock_door(self, vin: str) -> dict:
        return await self._request(
            "POST", f"{COMMAND_BASE}/vehicle/{vin}/command/door_unlock"
        )

    async def request_location(self, vin: str) -> dict:
        """Ask the vehicle to report its current position.

        Declared but never called by the official app (v2.63.0); verified working
        against the live API. The car answers COMMAND_RECEIVED immediately and
        pushes a fresh position a few seconds later.
        """
        return await self._request(
            "POST", f"{COMMAND_BASE}/vehicle/{vin}/command/request_location"
        )

    async def flash_lights(self, vin: str) -> dict:
        return await self._request(
            "POST", f"{COMMAND_BASE}/vehicle/{vin}/command/flash_lights"
        )

    async def honk_horn(self, vin: str) -> dict:
        return await self._request(
            "POST", f"{COMMAND_BASE}/vehicle/{vin}/command/honk_horn"
        )

    async def open_sunroof(self, vin: str) -> dict:
        return await self._request(
            "POST", f"{COMMAND_BASE}/vehicle/{vin}/command/sun_roof_open"
        )

    async def close_sunroof(self, vin: str) -> dict:
        return await self._request(
            "POST", f"{COMMAND_BASE}/vehicle/{vin}/command/sun_roof_close"
        )

    async def set_charge_limit(self, vin: str, percent: int) -> dict:
        url = f"{COMMAND_BASE}/vehicle/{vin}/command/set_charge_limit"
        return await self._request("POST", url, params={"percent": percent})

    async def start_charging(self, vin: str) -> dict:
        return await self._request(
            "POST", f"{COMMAND_BASE}/vehicle/{vin}/command/charge_start"
        )

    async def stop_charging(self, vin: str) -> dict:
        return await self._request(
            "POST", f"{COMMAND_BASE}/vehicle/{vin}/command/charge_stop"
        )

    async def start_conditioning(self, vin: str, temp: int, level: int | None = None) -> dict:
        params = {"temp": temp}
        if level is not None:
            params["level"] = level
        return await self._request(
            "POST", f"{COMMAND_BASE}/vehicle/{vin}/command/auto_conditioning_start",
            params=params,
        )

    async def stop_conditioning(self, vin: str) -> dict:
        return await self._request(
            "POST", f"{COMMAND_BASE}/vehicle/{vin}/command/auto_conditioning_stop"
        )

    async def start_ventilate(self, vin: str) -> dict:
        return await self._request(
            "POST", f"{COMMAND_BASE}/vehicle/{vin}/command/ventilate_start"
        )

    async def stop_ventilate(self, vin: str) -> dict:
        return await self._request(
            "POST", f"{COMMAND_BASE}/vehicle/{vin}/command/ventilate_stop"
        )

    async def start_heaters(self, vin: str, heaters: list[str]) -> dict:
        return await self._request(
            "POST", f"{COMMAND_BASE}/vehicle/{vin}/command/start_heaters",
            json=heaters,
        )

    async def stop_heaters(self, vin: str, heaters: list[str]) -> dict:
        return await self._request(
            "POST", f"{COMMAND_BASE}/vehicle/{vin}/command/stop_heaters",
            json=heaters,
        )

    async def lock_glovebox(self, vin: str, password: str) -> dict:
        return await self._request(
            "POST", f"{COMMAND_BASE}/vehicle/{vin}/command/glovebox_set_password",
            json={"password": password},
        )

    async def unlock_glovebox(self, vin: str) -> dict:
        return await self._request(
            "POST", f"{COMMAND_BASE}/vehicle/{vin}/command/glovebox_unlock"
        )

    # --- Static helpers for the config flow auth ---

    @staticmethod
    def generate_auth_url() -> tuple[str, str, str]:
        """Generate B2C authorize URL. Returns (url, code_verifier, code_challenge)."""
        code_verifier, code_challenge = pkce.generate_pkce_pair()
        scope_encoded = urllib.parse.quote(SCOPE, safe="")
        redirect_encoded = urllib.parse.quote(REDIRECT_URI, safe="")
        url = (
            f"{LOGIN_B2C_URL}oauth2/v2.0/authorize"
            f"?response_type=code"
            f"&client_id={CLIENT_ID}"
            f"&scope={scope_encoded}"
            f"&code_challenge={code_challenge}"
            f"&code_challenge_method=S256"
            f"&redirect_uri={redirect_encoded}"
        )
        return url, code_verifier, code_challenge

    @staticmethod
    def extract_code_from_url(url: str) -> str | None:
        """Extract the authorization code from the pasted msauth:// redirect.

        Accepts the bare URL, a "Location: msauth://..." header line and a whole
        pasted response-headers block (the README's Firefox tip): the code ends
        at the next query parameter or at whitespace, so the header lines after
        it are left out. A pasted "code=..." on its own works too.
        """
        match = _CODE_IN_URL.search(url) or _BARE_CODE.match(url)
        if match is None:
            return None
        return urllib.parse.unquote(match.group(1))

    @staticmethod
    async def exchange_code(
        session: aiohttp.ClientSession, code: str, code_verifier: str
    ) -> dict | None:
        """Exchange authorization code for tokens."""
        url = f"{LOGIN_B2C_URL}oauth2/v2.0/token"
        async with session.post(
            url,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={
                "client_info": "1",
                "scope": SCOPE,
                "code": code,
                "grant_type": "authorization_code",
                "code_verifier": code_verifier,
                "redirect_uri": REDIRECT_URI,
                "client_id": CLIENT_ID,
            },
            timeout=REQUEST_TIMEOUT,
        ) as resp:
            if resp.status != 200:
                _LOGGER.error("Token exchange failed: %d", resp.status)
                return None
            return await resp.json()
