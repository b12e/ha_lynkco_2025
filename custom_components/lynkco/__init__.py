"""Lynk & Co integration for Home Assistant."""

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import LynkCoAPI
from .const import CONF_ACCESS_TOKEN, CONF_DEVICE_ID, CONF_REFRESH_TOKEN, DOMAIN
from .coordinator import LynkCoCoordinator

_LOGGER = logging.getLogger(__name__)
PLATFORMS = ["sensor", "binary_sensor", "device_tracker", "lock"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Lynk & Co from a config entry."""
    session = async_get_clientsession(hass)
    api = LynkCoAPI(
        session,
        entry.data[CONF_ACCESS_TOKEN],
        entry.data[CONF_REFRESH_TOKEN],
        entry.data[CONF_DEVICE_ID],
    )

    await api.validate_session()
    vehicles = await api.get_vehicles()

    if not vehicles:
        _LOGGER.error("No vehicles found")
        return False

    coordinators: dict[str, LynkCoCoordinator] = {}
    for vehicle_entry in vehicles:
        vehicle = vehicle_entry.get("vehicle", {})
        vin = vehicle.get("vin")
        model = vehicle.get("model", "Unknown")
        if not vin:
            continue

        coordinator = LynkCoCoordinator(hass, entry, api, vin, model)
        await coordinator.async_config_entry_first_refresh()
        coordinators[vin] = coordinator

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "api": api,
        "coordinators": coordinators,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok
