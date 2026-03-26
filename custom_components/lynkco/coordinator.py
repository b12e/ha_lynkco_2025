"""Data coordinator for Lynk & Co integration."""

import logging
from datetime import timedelta

from homeassistant.util import dt as dt_util

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import LynkCoAPI
from .const import DEFAULT_SCAN_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)


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
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{vin}",
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
        )
        self.api = api
        self.vin = vin
        self.model = model
        self.propulsion: str | None = None  # Set after first fetch (e.g. "PHEV", "BEV")
        self.entry = entry

    async def _async_update_data(self) -> dict:
        try:
            vehicle_data = await self.api.get_vehicle_data(self.vin)
            location = await self.api.get_location(self.vin)
            charge = await self.api.get_charge_state(self.vin)
            climate = await self.api.get_climate_state(self.vin)
            doors = await self.api.get_doors_windows(self.vin)
            fuel = await self.api.get_fuel_state(self.vin) if self.propulsion != "BEV" else {}
            metadata = await self.api.get_vehicle_metadata(self.vin)
        except Exception as err:
            # Try refreshing tokens once
            if await self.api.refresh_tokens():
                try:
                    vehicle_data = await self.api.get_vehicle_data(self.vin)
                    location = await self.api.get_location(self.vin)
                    charge = await self.api.get_charge_state(self.vin)
                    climate = await self.api.get_climate_state(self.vin)
                    doors = await self.api.get_doors_windows(self.vin)
                    fuel = await self.api.get_fuel_state(self.vin) if self.propulsion != "BEV" else {}
                    metadata = await self.api.get_vehicle_metadata(self.vin)
                except Exception as retry_err:
                    raise UpdateFailed(f"API error after refresh: {retry_err}") from retry_err
            else:
                raise UpdateFailed(f"API error: {err}") from err

        # Store propulsion type for entity filtering
        propulsion = metadata.get("vehicle", {}).get("propulsionType")
        if propulsion:
            self.propulsion = propulsion

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
