"""Lynk & Co integration for Home Assistant."""

import asyncio
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
ATTR_TEMP = "temp"
ATTR_HEATERS = "heaters"
ATTR_PIN = "pin"

VALID_HEATERS = [
    "front_left_seat",
    "front_right_seat",
    "rear_left_seat",
    "rear_right_seat",
    "steering_wheel",
    "defrost",
]

OPTIONAL_HEATERS = {
    "rear_left_seat": "rearLeftSeat",
    "rear_right_seat": "rearRightSeat",
    "steering_wheel": "steeringWheel",
}

SERVICE_FLASH_LIGHTS = "flash_lights"
SERVICE_HONK_HORN = "honk_horn"
SERVICE_OPEN_SUNROOF = "open_sunroof"
SERVICE_CLOSE_SUNROOF = "close_sunroof"
SERVICE_SET_CHARGE_LIMIT = "set_charge_limit"
SERVICE_START_VENTILATE = "start_ventilate"
SERVICE_STOP_VENTILATE = "stop_ventilate"
SERVICE_START_HEATERS = "start_heaters"
SERVICE_STOP_HEATERS = "stop_heaters"
SERVICE_START_CONDITIONING = "start_conditioning"
SERVICE_STOP_CONDITIONING = "stop_conditioning"
SERVICE_REFRESH = "refresh"
SERVICE_LOCK_DOOR = "lock_door"
SERVICE_UNLOCK_DOOR = "unlock_door"
SERVICE_LOCK_GLOVEBOX = "lock_glovebox"
SERVICE_UNLOCK_GLOVEBOX = "unlock_glovebox"

ALL_SERVICES = [
    SERVICE_FLASH_LIGHTS, SERVICE_HONK_HORN,
    SERVICE_OPEN_SUNROOF, SERVICE_CLOSE_SUNROOF,
    SERVICE_SET_CHARGE_LIMIT,
    SERVICE_START_VENTILATE, SERVICE_STOP_VENTILATE,
    SERVICE_START_HEATERS, SERVICE_STOP_HEATERS,
    SERVICE_START_CONDITIONING, SERVICE_STOP_CONDITIONING,
    SERVICE_REFRESH,
    SERVICE_LOCK_DOOR, SERVICE_UNLOCK_DOOR,
    SERVICE_LOCK_GLOVEBOX, SERVICE_UNLOCK_GLOVEBOX,
]

VIN_SCHEMA = vol.Schema({vol.Optional(ATTR_VIN): cv.string})
CHARGE_LIMIT_SCHEMA = vol.Schema({
    vol.Optional(ATTR_VIN): cv.string,
    vol.Required(ATTR_PERCENT): vol.All(vol.Coerce(int), vol.Range(min=50, max=100)),
})
CONDITIONING_SCHEMA = vol.Schema({
    vol.Optional(ATTR_VIN): cv.string,
    vol.Required(ATTR_TEMP): vol.All(vol.Coerce(int), vol.Range(min=16, max=28)),
})
HEATERS_SCHEMA = vol.Schema({
    vol.Optional(ATTR_VIN): cv.string,
    vol.Required(ATTR_HEATERS): vol.All(
        cv.ensure_list, [vol.In(VALID_HEATERS)],
    ),
})

GLOVEBOX_LOCK_SCHEMA = vol.Schema({
    vol.Optional(ATTR_VIN): cv.string,
    vol.Required(ATTR_PIN): vol.All(cv.string, vol.Match(r"^\d{4}$")),
})

ACTION_REFRESH_DELAY = 10  # seconds to wait before refreshing after an action


def _all_vins(hass: HomeAssistant) -> list[str]:
    """Return all known VINs across all config entries."""
    vins = []
    for entry_data in hass.data.get(DOMAIN, {}).values():
        vins.extend(entry_data.get("coordinators", {}).keys())
    return vins


def _resolve_vin(hass: HomeAssistant, call: ServiceCall) -> str:
    """Get VIN from service call, or auto-detect if only one vehicle."""
    vin = call.data.get(ATTR_VIN)
    if vin:
        return vin
    vins = _all_vins(hass)
    if len(vins) == 1:
        return vins[0]
    raise vol.Invalid(
        f"Multiple vehicles configured ({', '.join(vins)}). Please specify 'vin'."
    )


def _get_api(hass: HomeAssistant, vin: str) -> LynkCoAPI:
    """Find the API instance that owns a given VIN."""
    for entry_data in hass.data.get(DOMAIN, {}).values():
        if vin in entry_data.get("coordinators", {}):
            return entry_data["api"]
    raise vol.Invalid(f"VIN {vin} not found")


def _get_coordinator(hass: HomeAssistant, vin: str) -> LynkCoCoordinator | None:
    for entry_data in hass.data.get(DOMAIN, {}).values():
        coordinator = entry_data.get("coordinators", {}).get(vin)
        if coordinator:
            return coordinator
    return None


async def _delayed_refresh(hass: HomeAssistant, vin: str) -> None:
    """Schedule a sensor refresh after a short delay to pick up new state."""
    await asyncio.sleep(ACTION_REFRESH_DELAY)
    coordinator = _get_coordinator(hass, vin)
    if coordinator:
        await coordinator.async_request_refresh()


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Lynk & Co from a config entry."""
    session = async_get_clientsession(hass)

    def _persist_tokens(access_token: str, refresh_token: str) -> None:
        hass.config_entries.async_update_entry(
            entry,
            data={**entry.data, CONF_ACCESS_TOKEN: access_token, CONF_REFRESH_TOKEN: refresh_token},
        )

    api = LynkCoAPI(
        session,
        entry.data[CONF_ACCESS_TOKEN],
        entry.data[CONF_REFRESH_TOKEN],
        entry.data[CONF_DEVICE_ID],
        on_token_refresh=_persist_tokens,
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
            vin = _resolve_vin(hass, call)
            await _get_api(hass, vin).flash_lights(vin)
            hass.async_create_task(_delayed_refresh(hass, vin))

        async def handle_honk_horn(call: ServiceCall) -> None:
            vin = _resolve_vin(hass, call)
            await _get_api(hass, vin).honk_horn(vin)
            hass.async_create_task(_delayed_refresh(hass, vin))

        async def handle_open_sunroof(call: ServiceCall) -> None:
            vin = _resolve_vin(hass, call)
            await _get_api(hass, vin).open_sunroof(vin)
            hass.async_create_task(_delayed_refresh(hass, vin))

        async def handle_close_sunroof(call: ServiceCall) -> None:
            vin = _resolve_vin(hass, call)
            await _get_api(hass, vin).close_sunroof(vin)
            hass.async_create_task(_delayed_refresh(hass, vin))

        async def handle_set_charge_limit(call: ServiceCall) -> None:
            vin = _resolve_vin(hass, call)
            await _get_api(hass, vin).set_charge_limit(vin, call.data[ATTR_PERCENT])
            hass.async_create_task(_delayed_refresh(hass, vin))

        async def handle_start_ventilate(call: ServiceCall) -> None:
            vin = _resolve_vin(hass, call)
            await _get_api(hass, vin).start_ventilate(vin)
            hass.async_create_task(_delayed_refresh(hass, vin))

        async def handle_stop_ventilate(call: ServiceCall) -> None:
            vin = _resolve_vin(hass, call)
            await _get_api(hass, vin).stop_ventilate(vin)
            hass.async_create_task(_delayed_refresh(hass, vin))

        def _validate_heaters(hass: HomeAssistant, vin: str, heaters: list[str]) -> list[str]:
            coordinator = _get_coordinator(hass, vin)
            if coordinator and coordinator.data:
                available = (coordinator.data.get("climate", {}).get("heaters") or {})
                for h in heaters:
                    api_key = OPTIONAL_HEATERS.get(h)
                    if api_key and available.get(api_key) is None:
                        raise vol.Invalid(f"Heater zone '{h}' is not available on this vehicle")
            return [h.upper() for h in heaters]

        async def handle_start_heaters(call: ServiceCall) -> None:
            vin = _resolve_vin(hass, call)
            heaters = _validate_heaters(hass, vin, call.data[ATTR_HEATERS])
            await _get_api(hass, vin).start_heaters(vin, heaters)
            hass.async_create_task(_delayed_refresh(hass, vin))

        async def handle_stop_heaters(call: ServiceCall) -> None:
            vin = _resolve_vin(hass, call)
            heaters = _validate_heaters(hass, vin, call.data[ATTR_HEATERS])
            await _get_api(hass, vin).stop_heaters(vin, heaters)
            hass.async_create_task(_delayed_refresh(hass, vin))

        async def handle_start_conditioning(call: ServiceCall) -> None:
            vin = _resolve_vin(hass, call)
            await _get_api(hass, vin).start_conditioning(vin, call.data[ATTR_TEMP])
            hass.async_create_task(_delayed_refresh(hass, vin))

        async def handle_stop_conditioning(call: ServiceCall) -> None:
            vin = _resolve_vin(hass, call)
            await _get_api(hass, vin).stop_conditioning(vin)
            hass.async_create_task(_delayed_refresh(hass, vin))

        async def handle_lock_door(call: ServiceCall) -> None:
            vin = _resolve_vin(hass, call)
            await _get_api(hass, vin).lock_door(vin)
            hass.async_create_task(_delayed_refresh(hass, vin))

        async def handle_unlock_door(call: ServiceCall) -> None:
            vin = _resolve_vin(hass, call)
            await _get_api(hass, vin).unlock_door(vin)
            hass.async_create_task(_delayed_refresh(hass, vin))

        async def handle_lock_glovebox(call: ServiceCall) -> None:
            vin = _resolve_vin(hass, call)
            await _get_api(hass, vin).lock_glovebox(vin, call.data[ATTR_PIN])
            hass.async_create_task(_delayed_refresh(hass, vin))

        async def handle_unlock_glovebox(call: ServiceCall) -> None:
            vin = _resolve_vin(hass, call)
            await _get_api(hass, vin).unlock_glovebox(vin)
            hass.async_create_task(_delayed_refresh(hass, vin))

        async def handle_refresh(call: ServiceCall) -> None:
            vin = _resolve_vin(hass, call)
            coordinator = _get_coordinator(hass, vin)
            if coordinator:
                await coordinator.async_request_refresh()
            else:
                raise vol.Invalid(f"VIN {vin} not found")

        hass.services.async_register(DOMAIN, SERVICE_FLASH_LIGHTS, handle_flash_lights, VIN_SCHEMA)
        hass.services.async_register(DOMAIN, SERVICE_HONK_HORN, handle_honk_horn, VIN_SCHEMA)
        hass.services.async_register(DOMAIN, SERVICE_OPEN_SUNROOF, handle_open_sunroof, VIN_SCHEMA)
        hass.services.async_register(DOMAIN, SERVICE_CLOSE_SUNROOF, handle_close_sunroof, VIN_SCHEMA)
        hass.services.async_register(DOMAIN, SERVICE_SET_CHARGE_LIMIT, handle_set_charge_limit, CHARGE_LIMIT_SCHEMA)
        hass.services.async_register(DOMAIN, SERVICE_START_VENTILATE, handle_start_ventilate, VIN_SCHEMA)
        hass.services.async_register(DOMAIN, SERVICE_STOP_VENTILATE, handle_stop_ventilate, VIN_SCHEMA)
        hass.services.async_register(DOMAIN, SERVICE_START_HEATERS, handle_start_heaters, HEATERS_SCHEMA)
        hass.services.async_register(DOMAIN, SERVICE_STOP_HEATERS, handle_stop_heaters, HEATERS_SCHEMA)
        hass.services.async_register(DOMAIN, SERVICE_START_CONDITIONING, handle_start_conditioning, CONDITIONING_SCHEMA)
        hass.services.async_register(DOMAIN, SERVICE_STOP_CONDITIONING, handle_stop_conditioning, VIN_SCHEMA)
        hass.services.async_register(DOMAIN, SERVICE_LOCK_DOOR, handle_lock_door, VIN_SCHEMA)
        hass.services.async_register(DOMAIN, SERVICE_UNLOCK_DOOR, handle_unlock_door, VIN_SCHEMA)
        hass.services.async_register(DOMAIN, SERVICE_LOCK_GLOVEBOX, handle_lock_glovebox, GLOVEBOX_LOCK_SCHEMA)
        hass.services.async_register(DOMAIN, SERVICE_UNLOCK_GLOVEBOX, handle_unlock_glovebox, VIN_SCHEMA)
        hass.services.async_register(DOMAIN, SERVICE_REFRESH, handle_refresh, VIN_SCHEMA)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
        if not hass.data.get(DOMAIN):
            for service in ALL_SERVICES:
                hass.services.async_remove(DOMAIN, service)
    return unload_ok
