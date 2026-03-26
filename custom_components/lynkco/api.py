"""API client for Lynk & Co vehicles."""

import hashlib
import json
import logging
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
    ) -> None:
        self._session = session
        self._access_token = access_token
        self._refresh_token = refresh_token
        self._device_id = device_id
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
    def user_full_name(self) -> str:
        given = self._claims.get("given_name", "")
        family = self._claims.get("family_name", "")
        return f"{given} {family}".strip()

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
            "X-App-Version": "2.55.0",
            "X-App-Build-Number": "8284",
            "X-Device-OS-Version": "14",
            "X-Device-Model": "Pixel 8",
            "X-Device-Language": "en",
            "Content-Type": "application/json",
        }

    async def _request(self, method: str, url: str, **kwargs) -> dict:
        headers = self._build_headers(url)
        async with self._session.request(method, url, headers=headers, **kwargs) as resp:
            if resp.status == 401:
                _LOGGER.debug("Got 401, attempting token refresh")
                if await self.refresh_tokens():
                    headers = self._build_headers(url)
                    async with self._session.request(
                        method, url, headers=headers, **kwargs
                    ) as retry:
                        retry.raise_for_status()
                        return await retry.json()
            resp.raise_for_status()
            if resp.content_length == 0:
                return {}
            return await resp.json()

    async def refresh_tokens(self) -> bool:
        url = f"{LOGIN_B2C_URL}oauth2/v2.0/token"
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
        ) as resp:
            if resp.status != 200:
                _LOGGER.error("Token refresh failed: %d", resp.status)
                return False
            data = await resp.json()
            self._access_token = data["access_token"]
            self._refresh_token = data.get("refresh_token", self._refresh_token)
            self._update_claims()
            _LOGGER.debug("Tokens refreshed successfully")
            return True

    async def validate_session(self) -> bool:
        url = f"{IAM_BASE}/validate-session"
        headers = self._build_headers(url)
        async with self._session.post(
            url,
            headers=headers,
            json={"deviceUuid": self._device_id, "isLogin": True},
        ) as resp:
            return resp.status == 200

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

    async def lock_door(self, vin: str) -> dict:
        return await self._request(
            "POST", f"{COMMAND_BASE}/vehicle/{vin}/command/door_lock"
        )

    async def unlock_door(self, vin: str) -> dict:
        return await self._request(
            "POST", f"{COMMAND_BASE}/vehicle/{vin}/command/door_unlock"
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

    async def start_heaters(self, vin: str) -> dict:
        return await self._request(
            "POST", f"{COMMAND_BASE}/vehicle/{vin}/command/start_heaters",
            json=[],
        )

    async def stop_heaters(self, vin: str) -> dict:
        return await self._request(
            "POST", f"{COMMAND_BASE}/vehicle/{vin}/command/stop_heaters",
            json=[],
        )

    async def send_to_car(self, vin: str, title: str, lat: float, lon: float) -> dict:
        import time
        now_ms = int(time.time() * 1000)
        expire_ms = now_ms + 24 * 60 * 60 * 1000  # 24 hours
        url = f"{COMMAND_BASE}/vehicle/{vin}/command/set_navigation"
        return await self._request(
            "POST", url, json={
                "title": title,
                "latitude": lat,
                "longitude": lon,
                "initiatedAt": now_ms,
                "expiresAt": expire_ms,
                "senderName": self.user_full_name or self.user_email or "Home Assistant",
            }
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
        """Extract authorization code from msauth:// redirect URL."""
        if "code=" in url:
            if "?" in url:
                query = url.split("?", 1)[1]
            else:
                query = url
            return urllib.parse.parse_qs(query).get("code", [None])[0]
        return None

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
        ) as resp:
            if resp.status != 200:
                _LOGGER.error("Token exchange failed: %d", resp.status)
                return None
            return await resp.json()
