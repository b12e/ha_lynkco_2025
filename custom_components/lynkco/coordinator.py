"""Data coordinator for Lynk & Co integration."""

import asyncio
import logging
from collections.abc import Callable, Coroutine
from datetime import datetime, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import LynkCoAPI
from .const import (
    CLIMATE_SCAN_INTERVAL,
    CONF_DRIVING_INTERVAL,
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    DRIVING_SCAN_INTERVAL,
    GUIDE_TYPE_NAMES,
    LIVE_PERMISSION_FLAGS,
    MANUFACTURER,
    MODEL_NAMES,
    MODEL_REPORT_URL,
)
from .features import ModelFeatures

_LOGGER = logging.getLogger(__name__)

REFRESH_RETRY_DELAYS = [3, 5, 10]
FAST_POLL_BASE_INTERVAL = timedelta(seconds=CLIMATE_SCAN_INTERVAL)  # finest fast-poll cadence

# Every data key a full snapshot carries (fuel is skipped on BEVs)
DATA_KEYS = ("vehicle_data", "location", "charge", "climate", "doors", "fuel", "metadata")


def dig(data, *keys):
    """Safely traverse nested dicts, tolerating None or missing keys at any level."""
    for key in keys:
        if not isinstance(data, dict):
            return None
        data = data.get(key)
    return data


class LynkCoCoordinator(DataUpdateCoordinator):
    """Fetch data from Lynk & Co API."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        api: LynkCoAPI,
        vin: str,
        model: str,
        guide_type: str | None,
        features: ModelFeatures,
    ) -> None:
        scan_minutes = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL // 60)
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{vin}",
            update_interval=timedelta(minutes=scan_minutes),
        )
        self.api = api
        self.vin = vin
        self.model = model
        self.guide_type = guide_type
        self.features = features
        self.propulsion: str | None = None  # Set after first fetch (e.g. "PHEV", "BEV")
        self.entry = entry
        self._last_fast_poll: dict[str, datetime] = {}
        # data key -> last error message, for endpoints that failed on the latest poll
        self.endpoint_errors: dict[str, str] = {}

    # --- identity ---------------------------------------------------------

    @property
    def model_name(self) -> str:
        """Human readable name: guide type (year / trim) first, model code second."""
        if self.guide_type and self.guide_type in GUIDE_TYPE_NAMES:
            return GUIDE_TYPE_NAMES[self.guide_type]
        return MODEL_NAMES.get(self.model, f"Lynk & Co {self.model}")

    @property
    def device_info(self) -> DeviceInfo:
        vehicle = dig(self.data, "metadata", "vehicle") or {}
        hw_parts = [str(v) for v in (vehicle.get("propulsionType"), vehicle.get("year")) if v]
        return DeviceInfo(
            identifiers={(DOMAIN, self.vin)},
            name=self.model_name,
            manufacturer=MANUFACTURER,
            model=self.model_name,
            model_id=self.model,
            hw_version=" ".join(hw_parts) or None,
            serial_number=self.vin,
        )

    # --- feature gating ---------------------------------------------------

    def action_enabled(self, action: str) -> bool:
        return self.features.action_enabled(action)

    def require_action(self, action: str) -> None:
        """Raise a translated error when an action is off for this model or blocked right now."""
        placeholders = {
            "action": action.replace("_", " "),
            "model": self.model_name,
            "model_code": self.model,
            "guide_type": self.guide_type or "unknown",
            "support_url": self.features.source or MODEL_REPORT_URL,
        }
        if not self.features.action_enabled(action):
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="action_not_supported",
                translation_placeholders=placeholders,
            )
        blocked = False
        flag = LIVE_PERMISSION_FLAGS.get(action)
        if flag and dig(self.data, "vehicle_data", flag) is False:
            blocked = True
        if action in ("start_ventilate", "stop_ventilate") and (
            dig(self.data, "doors", "windowVentilateState", "enabled") is False
        ):
            blocked = True
        if blocked:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="action_not_permitted",
                translation_placeholders=placeholders,
            )

    # --- polling ----------------------------------------------------------

    def _endpoints(self) -> dict[str, Callable[[], Coroutine[Any, Any, dict]]]:
        endpoints: dict[str, Callable[[], Coroutine[Any, Any, dict]]] = {
            "vehicle_data": lambda: self.api.get_vehicle_data(self.vin),
            "location": lambda: self.api.get_location(self.vin),
            "charge": lambda: self.api.get_charge_state(self.vin),
            "climate": lambda: self.api.get_climate_state(self.vin),
            "doors": lambda: self.api.get_doors_windows(self.vin),
            "metadata": lambda: self.api.get_vehicle_metadata(self.vin),
        }
        if self.propulsion != "BEV":
            endpoints["fuel"] = lambda: self.api.get_fuel_state(self.vin)
        return endpoints

    async def _fetch_endpoint(
        self, key: str, fetch_fn: Callable[[], Coroutine[Any, Any, dict]]
    ) -> dict | None:
        """Fetch one endpoint; a failure is recorded instead of failing the whole poll."""
        try:
            value = await fetch_fn()
        except Exception as err:  # noqa: BLE001 - any API error isolates this endpoint only
            if key not in self.endpoint_errors:
                _LOGGER.warning("Lynk & Co endpoint %s failed for %s: %s", key, self.vin, err)
            else:
                _LOGGER.debug("Lynk & Co endpoint %s still failing for %s: %s", key, self.vin, err)
            self.endpoint_errors[key] = str(err)
            return None
        if key in self.endpoint_errors:
            _LOGGER.info("Lynk & Co endpoint %s recovered for %s", key, self.vin)
            self.endpoint_errors.pop(key, None)
        return value

    async def _async_fetch_all(self) -> dict | None:
        """Fetch every endpoint; returns None only when all of them failed.

        Requests stay sequential: the API client may refresh the shared token
        after a 401, and concurrent refreshes could overwrite each other.
        """
        old_data = self.data or {}
        results: dict[str, dict] = {}
        for key, fetch_fn in self._endpoints().items():
            value = await self._fetch_endpoint(key, fetch_fn)
            if value is not None:
                results[key] = value
        if not results:
            return None
        # Keep the last known value for an endpoint that failed; the entities
        # tied to it report unavailable through endpoint_errors.
        data = {key: results.get(key, old_data.get(key, {})) for key in DATA_KEYS}
        data["last_updated"] = dt_util.now()
        return data

    async def _async_update_data(self) -> dict:
        data = await self._async_fetch_all()
        if data is None:
            # Everything failed at once: most likely an expired session, so try
            # one token refresh before giving up on this cycle.
            if await self.api.refresh_tokens():
                data = await self._async_fetch_all()
            if data is None:
                raise UpdateFailed(f"All Lynk & Co API endpoints failed: {self.endpoint_errors}")

        # Store propulsion type for entity filtering
        propulsion = (data["metadata"].get("vehicle") or {}).get("propulsionType")
        if propulsion:
            self.propulsion = propulsion

        return data

    def start_fast_poll(self) -> Callable[[], None]:
        """Start the endpoint-specific fast-poll timer; returns an unsub callable.

        The full snapshot keeps polling on ``update_interval`` as a backstop; this
        timer additionally refreshes only the endpoints relevant to whatever is
        currently active (driving / climate), each at its own cadence.
        """
        return async_track_time_interval(self.hass, self._async_fast_poll, FAST_POLL_BASE_INTERVAL)

    def _fast_poll_targets(self) -> list[tuple[str, str, timedelta]]:
        """(data_key, api_method, period) for each endpoint to fast-poll right now."""
        data = self.data or {}
        targets: list[tuple[str, str, timedelta]] = []
        if (data.get("vehicle_data") or {}).get("driveModeEnabled", False):
            drive = timedelta(
                minutes=self.entry.options.get(CONF_DRIVING_INTERVAL, DRIVING_SCAN_INTERVAL // 60)
            )
            # vehicle_data polls at the base cadence so drive-end is detected promptly
            targets.append(("vehicle_data", "get_vehicle_data", FAST_POLL_BASE_INTERVAL))
            targets.append(("location", "get_location", drive))
            targets.append(("charge", "get_charge_state", drive))
        status = (data.get("climate") or {}).get("status")
        if str(status or "").upper().startswith("ACTIVE"):
            targets.append(("climate", "get_climate_state", FAST_POLL_BASE_INTERVAL))
        return targets

    async def _async_fast_poll(self, now: datetime) -> None:
        """Refresh only the endpoints relevant to the active trigger(s)."""
        if self.data is None:
            return

        slack = timedelta(seconds=1)  # tolerate timer jitter so a 60s target fires each 60s tick
        due: dict[str, str] = {}
        for key, fn_name, period in self._fast_poll_targets():
            last = self._last_fast_poll.get(key)
            if last is None or (now - last) >= (period - slack):
                due[key] = fn_name
        if not due:
            return

        was_driving = (self.data.get("vehicle_data") or {}).get("driveModeEnabled", False)
        errors_before = dict(self.endpoint_errors)
        updates: dict[str, Any] = {}
        for key, fn_name in due.items():
            value = await self._fetch_endpoint(key, getattr(self.api, fn_name))
            if value is not None:
                updates[key] = value
                self._last_fast_poll[key] = now
        if not updates:
            if self.endpoint_errors != errors_before:
                self.async_update_listeners()  # availability changed
            return

        changed = any(updates[k] != self.data.get(k) for k in updates)
        self.data = {**self.data, **updates, "last_updated": dt_util.now()}
        if changed or self.endpoint_errors != errors_before:
            self.async_update_listeners()
        _LOGGER.debug("Fast-polled %s for %s (changed=%s)", list(updates), self.vin, changed)

        # LynkOS 1.4.0+ only refreshes location when the car stops, so when
        # driving has just ended, chase the final (destination) location.
        now_driving = (updates.get("vehicle_data") or {}).get("driveModeEnabled", False)
        if was_driving and "vehicle_data" in updates and not now_driving:
            self.hass.async_create_task(
                self.async_targeted_refresh("location", lambda: self.api.get_location(self.vin))
            )

    async def async_targeted_refresh(
        self,
        data_key: str,
        fetch_fn: Callable[[], Coroutine[Any, Any, dict]],
    ) -> None:
        """Refresh a single data key with retry logic."""
        if self.data is None:
            return

        old_value = self.data.get(data_key)

        for delay in REFRESH_RETRY_DELAYS:
            await asyncio.sleep(delay)
            had_error = data_key in self.endpoint_errors
            new_value = await self._fetch_endpoint(data_key, fetch_fn)
            if new_value is None:
                _LOGGER.debug("Targeted refresh of %s failed, will retry", data_key)
                continue

            if new_value != old_value:
                self.data = {**self.data, data_key: new_value, "last_updated": dt_util.now()}
                self.async_update_listeners()
                _LOGGER.debug("Targeted refresh of %s detected change", data_key)
                return
            if had_error:
                self.async_update_listeners()  # endpoint recovered, entities back
                return

        _LOGGER.debug("Targeted refresh of %s: no change after %d retries", data_key, len(REFRESH_RETRY_DELAYS))
        if data_key in self.endpoint_errors:
            self.async_update_listeners()  # make the failure visible as unavailable
