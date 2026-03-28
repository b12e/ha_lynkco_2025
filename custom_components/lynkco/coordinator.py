"""Data coordinator for Lynk & Co integration."""

import asyncio
import logging
from collections.abc import Callable, Coroutine
from datetime import timedelta
from typing import Any

from homeassistant.util import dt as dt_util

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import LynkCoAPI
from .const import CONF_DRIVING_INTERVAL, CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL, DRIVING_SCAN_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)

REFRESH_RETRY_DELAYS = [3, 5, 10]


class LynkCoCoordinator(DataUpdateCoordinator):
    """Fetch data from Lynk & Co API."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        api: LynkCoAPI,
        vin: str,
        model: str,
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
        self.propulsion: str | None = None  # Set after first fetch (e.g. "PHEV", "BEV")
        self.entry = entry
        self._driving = False

    async def _async_fetch_all(self) -> dict:
        vehicle_data = await self.api.get_vehicle_data(self.vin)
        location = await self.api.get_location(self.vin)
        charge = await self.api.get_charge_state(self.vin)
        climate = await self.api.get_climate_state(self.vin)
        doors = await self.api.get_doors_windows(self.vin)
        fuel = await self.api.get_fuel_state(self.vin) if self.propulsion != "BEV" else {}
        metadata = await self.api.get_vehicle_metadata(self.vin)
        return {
            "vehicle_data": vehicle_data,
            "location": location,
            "charge": charge,
            "climate": climate,
            "doors": doors,
            "fuel": fuel,
            "metadata": metadata,
            "last_updated": dt_util.now(),
        }

    async def _async_update_data(self) -> dict:
        try:
            data = await self._async_fetch_all()
        except Exception as err:
            if await self.api.refresh_tokens():
                try:
                    data = await self._async_fetch_all()
                except Exception as retry_err:
                    raise UpdateFailed(f"API error after refresh: {retry_err}") from retry_err
            else:
                raise UpdateFailed(f"API error: {err}") from err

        # Store propulsion type for entity filtering
        propulsion = data["metadata"].get("vehicle", {}).get("propulsionType")
        if propulsion:
            self.propulsion = propulsion

        # Adjust polling interval based on driving state
        scan_minutes = self.entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL // 60)
        drive_minutes = self.entry.options.get(CONF_DRIVING_INTERVAL, DRIVING_SCAN_INTERVAL // 60)
        driving = data["vehicle_data"].get("driveModeEnabled", False)
        if driving and not self._driving:
            _LOGGER.debug("Car is running, increasing poll frequency to %dm", drive_minutes)
            self.update_interval = timedelta(minutes=drive_minutes)
        elif not driving and self._driving:
            _LOGGER.debug("Car stopped, reverting poll frequency to %dm", scan_minutes)
            self.update_interval = timedelta(minutes=scan_minutes)
        self._driving = driving

        return data

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
            try:
                new_value = await fetch_fn()
            except Exception:
                _LOGGER.debug("Targeted refresh of %s failed, will retry", data_key)
                continue

            if new_value != old_value:
                self.data = {**self.data, data_key: new_value, "last_updated": dt_util.now()}
                self.async_update_listeners()
                _LOGGER.debug("Targeted refresh of %s detected change", data_key)
                return

        _LOGGER.debug("Targeted refresh of %s: no change after %d retries", data_key, len(REFRESH_RETRY_DELAYS))
