"""Lynk & Co integration for Home Assistant."""

import logging

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import LynkCoAPI
from .const import CONF_ACCESS_TOKEN, CONF_DEVICE_ID, CONF_REFRESH_TOKEN, DOMAIN
from .coordinator import LynkCoCoordinator

_LOGGER = logging.getLogger(__name__)
PLATFORMS = ["sensor", "binary_sensor", "device_tracker", "lock"]

ATTR_VIN = "vin"
ATTR_PERCENT = "percent"

SERVICE_FLASH_LIGHTS = "flash_lights"
SERVICE_HONK_HORN = "honk_horn"
SERVICE_OPEN_SUNROOF = "open_sunroof"
SERVICE_CLOSE_SUNROOF = "close_sunroof"
SERVICE_SET_CHARGE_LIMIT = "set_charge_limit"
SERVICE_START_VENTILATE = "start_ventilate"
SERVICE_STOP_VENTILATE = "stop_ventilate"
SERVICE_START_HEATERS = "start_heaters"
SERVICE_STOP_HEATERS = "stop_heaters"

VIN_SCHEMA = vol.Schema({vol.Required(ATTR_VIN): cv.string})
CHARGE_LIMIT_SCHEMA = vol.Schema({
    vol.Required(ATTR_VIN): cv.string,
    vol.Required(ATTR_PERCENT): vol.All(vol.Coerce(int), vol.Range(min=50, max=100)),
})


def _get_api(hass: HomeAssistant, vin: str) -> LynkCoAPI:
    """Find the API instance that owns a given VIN."""
    for entry_data in hass.data.get(DOMAIN, {}).values():
        if vin in entry_data.get("coordinators", {}):
            return entry_data["api"]
    raise vol.Invalid(f"VIN {vin} not found")


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

    # Register services (only once)
    if not hass.services.has_service(DOMAIN, SERVICE_FLASH_LIGHTS):
        async def handle_flash_lights(call: ServiceCall) -> None:
            api = _get_api(hass, call.data[ATTR_VIN])
            await api.flash_lights(call.data[ATTR_VIN])

        async def handle_honk_horn(call: ServiceCall) -> None:
            api = _get_api(hass, call.data[ATTR_VIN])
            await api.honk_horn(call.data[ATTR_VIN])

        async def handle_open_sunroof(call: ServiceCall) -> None:
            api = _get_api(hass, call.data[ATTR_VIN])
            await api.open_sunroof(call.data[ATTR_VIN])

        async def handle_close_sunroof(call: ServiceCall) -> None:
            api = _get_api(hass, call.data[ATTR_VIN])
            await api.close_sunroof(call.data[ATTR_VIN])

        async def handle_set_charge_limit(call: ServiceCall) -> None:
            api = _get_api(hass, call.data[ATTR_VIN])
            await api.set_charge_limit(call.data[ATTR_VIN], call.data[ATTR_PERCENT])

        async def handle_start_ventilate(call: ServiceCall) -> None:
            api = _get_api(hass, call.data[ATTR_VIN])
            await api.start_ventilate(call.data[ATTR_VIN])

        async def handle_stop_ventilate(call: ServiceCall) -> None:
            api = _get_api(hass, call.data[ATTR_VIN])
            await api.stop_ventilate(call.data[ATTR_VIN])

        async def handle_start_heaters(call: ServiceCall) -> None:
            api = _get_api(hass, call.data[ATTR_VIN])
            await api.start_heaters(call.data[ATTR_VIN])

        async def handle_stop_heaters(call: ServiceCall) -> None:
            api = _get_api(hass, call.data[ATTR_VIN])
            await api.stop_heaters(call.data[ATTR_VIN])

        hass.services.async_register(DOMAIN, SERVICE_FLASH_LIGHTS, handle_flash_lights, VIN_SCHEMA)
        hass.services.async_register(DOMAIN, SERVICE_HONK_HORN, handle_honk_horn, VIN_SCHEMA)
        hass.services.async_register(DOMAIN, SERVICE_OPEN_SUNROOF, handle_open_sunroof, VIN_SCHEMA)
        hass.services.async_register(DOMAIN, SERVICE_CLOSE_SUNROOF, handle_close_sunroof, VIN_SCHEMA)
        hass.services.async_register(DOMAIN, SERVICE_SET_CHARGE_LIMIT, handle_set_charge_limit, CHARGE_LIMIT_SCHEMA)
        hass.services.async_register(DOMAIN, SERVICE_START_VENTILATE, handle_start_ventilate, VIN_SCHEMA)
        hass.services.async_register(DOMAIN, SERVICE_STOP_VENTILATE, handle_stop_ventilate, VIN_SCHEMA)
        hass.services.async_register(DOMAIN, SERVICE_START_HEATERS, handle_start_heaters, VIN_SCHEMA)
        hass.services.async_register(DOMAIN, SERVICE_STOP_HEATERS, handle_stop_heaters, VIN_SCHEMA)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
        # Remove services if no entries left
        if not hass.data.get(DOMAIN):
            for service in [
                SERVICE_FLASH_LIGHTS, SERVICE_HONK_HORN,
                SERVICE_OPEN_SUNROOF, SERVICE_CLOSE_SUNROOF,
                SERVICE_SET_CHARGE_LIMIT,
                SERVICE_START_VENTILATE, SERVICE_STOP_VENTILATE,
                SERVICE_START_HEATERS, SERVICE_STOP_HEATERS,
            ]:
                hass.services.async_remove(DOMAIN, service)
    return unload_ok
