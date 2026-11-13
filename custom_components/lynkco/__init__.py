"""Lynk & Co integration for Home Assistant."""

import logging
from collections.abc import Callable
from datetime import timedelta

import aiohttp
import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import LynkCoAPI, LynkCoAuthError, LynkCoTransientError, redact_vin
from .const import (
    CONF_ACCESS_TOKEN,
    CONF_DEVICE_ID,
    CONF_REFRESH_TOKEN,
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    LOCATION_FAQ_URL,
    MODEL_REPORT_URL,
)
from .coordinator import LynkCoCoordinator, dig
from .features import async_get_model_features

_LOGGER = logging.getLogger(__name__)
PLATFORMS = ["sensor", "binary_sensor", "device_tracker", "lock", "switch", "number", "climate", "button"]

# hass.data key of the VIN claims: VIN -> entry_id of the config entry that serves
# the car. Kept outside hass.data[DOMAIN], whose values are the per-entry dicts.
VEHICLE_CLAIMS = "lynkco_vehicle_claims"

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
SERVICE_START_CHARGING = "start_charging"
SERVICE_STOP_CHARGING = "stop_charging"
SERVICE_START_VENTILATE = "start_ventilate"
SERVICE_STOP_VENTILATE = "stop_ventilate"
SERVICE_START_HEATERS = "start_heaters"
SERVICE_STOP_HEATERS = "stop_heaters"
SERVICE_START_CONDITIONING = "start_conditioning"
SERVICE_STOP_CONDITIONING = "stop_conditioning"
SERVICE_REFRESH = "refresh"
SERVICE_REQUEST_LOCATION = "request_location"
SERVICE_LOCK_DOOR = "lock_door"
SERVICE_UNLOCK_DOOR = "unlock_door"
SERVICE_LOCK_GLOVEBOX = "lock_glovebox"
SERVICE_UNLOCK_GLOVEBOX = "unlock_glovebox"

ALL_SERVICES = [
    SERVICE_FLASH_LIGHTS, SERVICE_HONK_HORN,
    SERVICE_OPEN_SUNROOF, SERVICE_CLOSE_SUNROOF,
    SERVICE_SET_CHARGE_LIMIT,
    SERVICE_START_CHARGING, SERVICE_STOP_CHARGING,
    SERVICE_START_VENTILATE, SERVICE_STOP_VENTILATE,
    SERVICE_START_HEATERS, SERVICE_STOP_HEATERS,
    SERVICE_START_CONDITIONING, SERVICE_STOP_CONDITIONING,
    SERVICE_REFRESH, SERVICE_REQUEST_LOCATION,
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


def _require_action(hass: HomeAssistant, vin: str, action: str) -> LynkCoCoordinator:
    """Resolve the coordinator for a VIN and check the action is allowed on that car."""
    coordinator = _get_coordinator(hass, vin)
    if coordinator is None:
        raise vol.Invalid(f"VIN {vin} not found")
    coordinator.require_action(action)
    return coordinator


def _targeted_refresh(hass: HomeAssistant, vin: str, data_key: str, fetch_fn_name: str) -> None:
    """Schedule a targeted refresh of a single data key after an action."""
    coordinator = _get_coordinator(hass, vin)
    if coordinator:
        api = _get_api(hass, vin)
        fetch_fn = getattr(api, fetch_fn_name)
        hass.async_create_task(
            coordinator.async_targeted_refresh(data_key, lambda: fetch_fn(vin))
        )


def _model_report_url(model: str, guide_type: str | None) -> str:
    """Issue form link with the identity fields prefilled."""
    return f"{MODEL_REPORT_URL}&model_code={model}&guide_type={guide_type or ''}"


def _update_unknown_model_issue(hass: HomeAssistant, coordinator: LynkCoCoordinator) -> None:
    """Raise (or clear) the Repairs notice for a car without a model feature file."""
    issue_id = f"unknown_model_{coordinator.vin}"
    if not coordinator.features.is_default:
        ir.async_delete_issue(hass, DOMAIN, issue_id)
        return
    report_url = _model_report_url(coordinator.model, coordinator.guide_type)
    ir.async_create_issue(
        hass,
        DOMAIN,
        issue_id,
        is_fixable=False,
        is_persistent=False,
        severity=ir.IssueSeverity.WARNING,
        learn_more_url=report_url,
        translation_key="unknown_model",
        translation_placeholders={
            "model_code": coordinator.model,
            "guide_type": coordinator.guide_type or "unknown",
            "report_url": report_url,
        },
    )


def _update_location_sharing_issue(
    hass: HomeAssistant, coordinator: LynkCoCoordinator, enabled: bool | None
) -> None:
    """Raise (or clear) the Repairs notice for a car that does not share its location by itself.

    Since LynkOS 1.4 the car only reports where it is parked when location
    sharing is allowed in its privacy settings. The notice is cleared when the
    car reports the setting as on and deliberately not on unload: deleting it
    would also forget that the user chose to ignore it. A missing value (the
    endpoint failed) leaves the notice as it is.
    """
    issue_id = f"location_sharing_off_{coordinator.vin}"
    if enabled is True:
        ir.async_delete_issue(hass, DOMAIN, issue_id)
    elif enabled is False:
        # Asking for a position on demand only helps where that action is confirmed
        can_request = coordinator.action_enabled("request_location")
        ir.async_create_issue(
            hass,
            DOMAIN,
            issue_id,
            is_fixable=False,
            is_persistent=False,
            severity=ir.IssueSeverity.WARNING,
            learn_more_url=LOCATION_FAQ_URL,
            translation_key="location_sharing_off" if can_request else "location_sharing_off_no_request",
            translation_placeholders={
                "model": coordinator.model_name,
                "vin": coordinator.log_vin,
                "faq_url": LOCATION_FAQ_URL,
            },
        )


def _watch_location_sharing(hass: HomeAssistant, coordinator: LynkCoCoordinator) -> Callable[[], None]:
    """Keep the location sharing notice in step with the car; returns an unsub callable."""
    seen: list[bool | None] = []  # the last reported value, empty before the first check

    @callback
    def _check() -> None:
        enabled = dig(coordinator.data, "vehicle_data", "vehicleAutoShareLocationDataEnabled")
        if seen and seen[0] is enabled:
            return  # polls rarely change it; only touch the registry when it does
        seen[:] = [enabled]
        _update_location_sharing_issue(hass, coordinator, enabled)

    _check()
    return coordinator.async_add_listener(_check)


def _create_duplicate_vehicle_issue(
    hass: HomeAssistant, entry: ConfigEntry, vin: str, owner_id: str
) -> str:
    """Raise the Repairs notice for a car that another entry already serves; returns its id."""
    owner = hass.config_entries.async_get_entry(owner_id)
    owner_title = owner.title if owner else owner_id
    log_vin = redact_vin(vin)
    _LOGGER.warning(
        "Vehicle %s is already set up through the entry %s, skipping it for %s",
        log_vin, owner_title, entry.title,
    )
    issue_id = f"duplicate_vehicle_{entry.entry_id}_{vin}"
    ir.async_create_issue(
        hass,
        DOMAIN,
        issue_id,
        is_fixable=False,
        is_persistent=False,
        severity=ir.IssueSeverity.WARNING,
        translation_key="duplicate_vehicle",
        translation_placeholders={"vin": log_vin, "entry": entry.title, "other_entry": owner_title},
    )
    return issue_id


def _release_vehicles(hass: HomeAssistant, entry: ConfigEntry, duplicate_issues: list[str]) -> None:
    """Give the entry's cars back and drop its duplicate-car notices.

    Runs on unload and when the setup fails after claiming, so a retried
    setup (or the entry the car is shared with) can claim the cars again.
    """
    claims: dict[str, str] = hass.data.get(VEHICLE_CLAIMS, {})
    for vin in [vin for vin, owner in claims.items() if owner == entry.entry_id]:
        del claims[vin]
    for issue_id in duplicate_issues:
        ir.async_delete_issue(hass, DOMAIN, issue_id)


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

    # An expired session that cannot be refreshed raises ConfigEntryAuthFailed:
    # Home Assistant then shows a Repairs entry that opens the login flow again.
    # An API that cannot be reached (Home Assistant often boots before the
    # network is up) raises ConfigEntryNotReady instead: the setup is retried.
    try:
        if not await api.validate_session():
            await api.refresh_tokens()
        vehicles = await api.get_vehicles()
    except LynkCoAuthError as err:
        raise ConfigEntryAuthFailed(str(err)) from err
    except (aiohttp.ClientError, TimeoutError, LynkCoTransientError) as err:
        raise ConfigEntryNotReady(
            f"Lynk & Co API not available: {str(err) or type(err).__name__}"
        ) from err

    if not vehicles:
        _LOGGER.error("No vehicles found")
        return False

    # One car is one device. A car shared with a second Lynk & Co account is
    # listed by both entries, and both would create the same entities (the
    # unique ids are "<vin>_<key>"): the first entry to claim a VIN serves the
    # car, a later one skips it and raises a Repairs notice instead. Entries of
    # a domain are set up concurrently at startup, so the claims are made in
    # one step on the event loop, without an await between check and claim.
    claims: dict[str, str] = hass.data.setdefault(VEHICLE_CLAIMS, {})
    skipped: dict[str, str] = {}  # VIN -> entry_id of the entry that serves the car
    for vehicle_entry in vehicles:
        vin = (vehicle_entry.get("vehicle") or {}).get("vin")
        if vin and claims.setdefault(vin, entry.entry_id) != entry.entry_id:
            skipped[vin] = claims[vin]

    coordinators: dict[str, LynkCoCoordinator] = {}
    duplicate_issues: list[str] = []
    try:
        for vehicle_entry in vehicles:
            vehicle = vehicle_entry.get("vehicle") or {}
            vin = vehicle.get("vin")
            model = vehicle.get("model", "Unknown")
            if not vin:
                continue
            if vin in skipped:
                issue_id = _create_duplicate_vehicle_issue(hass, entry, vin, skipped[vin])
                duplicate_issues.append(issue_id)
                continue
            log_vin = redact_vin(vin)

            # The guide type (model year for pre-2025 01s, Core/More for newer cars)
            # is the most precise identity the API offers; it is fetched once.
            try:
                guide_type = await api.get_vehicle_guide(vin)
            except LynkCoAuthError as err:
                raise ConfigEntryAuthFailed(str(err)) from err
            except (aiohttp.ClientConnectionError, TimeoutError, LynkCoTransientError) as err:
                # No answer at all (unlike an answer without a guide): retry the setup
                raise ConfigEntryNotReady(
                    "Lynk & Co API not available: "
                    f"{str(err).replace(vin, log_vin) or type(err).__name__}"
                ) from err
            except Exception as err:  # noqa: BLE001 - identity is best effort
                # aiohttp puts the request URL, and with it the VIN, in the error text
                _LOGGER.warning(
                    "Could not read the vehicle guide type for %s: %s",
                    log_vin, str(err).replace(vin, log_vin),
                )
                guide_type = None
            features = await async_get_model_features(hass, guide_type, model)
            _LOGGER.info(
                "Vehicle %s: model %s, guide type %s, features from %s",
                log_vin, model, guide_type, features.file,
            )

            coordinator = LynkCoCoordinator(hass, entry, api, vin, model, guide_type, features)
            await coordinator.async_config_entry_first_refresh()
            coordinators[vin] = coordinator
            _update_unknown_model_issue(hass, coordinator)
            entry.async_on_unload(_watch_location_sharing(hass, coordinator))
            # Endpoint-specific fast polling (driving / climate active); stopped on unload
            entry.async_on_unload(coordinator.start_fast_poll())

        hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
            "api": api,
            "coordinators": coordinators,
            "duplicate_issues": duplicate_issues,
        }

        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    except Exception:
        # Not ready, a dead session or a platform error: the next attempt (or
        # the entry the car is shared with) has to be able to claim the cars
        _release_vehicles(hass, entry, duplicate_issues)
        raise

    # Apply the (full-snapshot) scan interval when options change
    async def _options_updated(_hass, _entry):
        scan_minutes = _entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL // 60)
        for coordinator in coordinators.values():
            coordinator.update_interval = timedelta(minutes=scan_minutes)

    entry.async_on_unload(entry.add_update_listener(_options_updated))

    # Register services (only once)
    if not hass.services.has_service(DOMAIN, SERVICE_FLASH_LIGHTS):
        async def handle_flash_lights(call: ServiceCall) -> None:
            vin = _resolve_vin(hass, call)
            _require_action(hass, vin, SERVICE_FLASH_LIGHTS)
            await _get_api(hass, vin).flash_lights(vin)

        async def handle_honk_horn(call: ServiceCall) -> None:
            vin = _resolve_vin(hass, call)
            _require_action(hass, vin, SERVICE_HONK_HORN)
            await _get_api(hass, vin).honk_horn(vin)

        async def handle_open_sunroof(call: ServiceCall) -> None:
            vin = _resolve_vin(hass, call)
            _require_action(hass, vin, SERVICE_OPEN_SUNROOF)
            await _get_api(hass, vin).open_sunroof(vin)
            _targeted_refresh(hass, vin, "doors", "get_doors_windows")

        async def handle_close_sunroof(call: ServiceCall) -> None:
            vin = _resolve_vin(hass, call)
            _require_action(hass, vin, SERVICE_CLOSE_SUNROOF)
            await _get_api(hass, vin).close_sunroof(vin)
            _targeted_refresh(hass, vin, "doors", "get_doors_windows")

        async def handle_set_charge_limit(call: ServiceCall) -> None:
            vin = _resolve_vin(hass, call)
            _require_action(hass, vin, SERVICE_SET_CHARGE_LIMIT)
            await _get_api(hass, vin).set_charge_limit(vin, call.data[ATTR_PERCENT])
            _targeted_refresh(hass, vin, "charge", "get_charge_state")

        async def handle_start_charging(call: ServiceCall) -> None:
            vin = _resolve_vin(hass, call)
            _require_action(hass, vin, SERVICE_START_CHARGING)
            await _get_api(hass, vin).start_charging(vin)
            _targeted_refresh(hass, vin, "charge", "get_charge_state")

        async def handle_stop_charging(call: ServiceCall) -> None:
            vin = _resolve_vin(hass, call)
            _require_action(hass, vin, SERVICE_STOP_CHARGING)
            await _get_api(hass, vin).stop_charging(vin)
            _targeted_refresh(hass, vin, "charge", "get_charge_state")

        async def handle_start_ventilate(call: ServiceCall) -> None:
            vin = _resolve_vin(hass, call)
            _require_action(hass, vin, SERVICE_START_VENTILATE)
            await _get_api(hass, vin).start_ventilate(vin)
            _targeted_refresh(hass, vin, "doors", "get_doors_windows")

        async def handle_stop_ventilate(call: ServiceCall) -> None:
            vin = _resolve_vin(hass, call)
            _require_action(hass, vin, SERVICE_STOP_VENTILATE)
            await _get_api(hass, vin).stop_ventilate(vin)
            _targeted_refresh(hass, vin, "doors", "get_doors_windows")

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
            _require_action(hass, vin, SERVICE_START_HEATERS)
            heaters = _validate_heaters(hass, vin, call.data[ATTR_HEATERS])
            await _get_api(hass, vin).start_heaters(vin, heaters)
            _targeted_refresh(hass, vin, "climate", "get_climate_state")

        async def handle_stop_heaters(call: ServiceCall) -> None:
            vin = _resolve_vin(hass, call)
            _require_action(hass, vin, SERVICE_STOP_HEATERS)
            heaters = _validate_heaters(hass, vin, call.data[ATTR_HEATERS])
            await _get_api(hass, vin).stop_heaters(vin, heaters)
            _targeted_refresh(hass, vin, "climate", "get_climate_state")

        async def handle_start_conditioning(call: ServiceCall) -> None:
            vin = _resolve_vin(hass, call)
            _require_action(hass, vin, SERVICE_START_CONDITIONING)
            await _get_api(hass, vin).start_conditioning(vin, call.data[ATTR_TEMP])
            _targeted_refresh(hass, vin, "climate", "get_climate_state")

        async def handle_stop_conditioning(call: ServiceCall) -> None:
            vin = _resolve_vin(hass, call)
            _require_action(hass, vin, SERVICE_STOP_CONDITIONING)
            await _get_api(hass, vin).stop_conditioning(vin)
            _targeted_refresh(hass, vin, "climate", "get_climate_state")

        async def handle_lock_door(call: ServiceCall) -> None:
            vin = _resolve_vin(hass, call)
            _require_action(hass, vin, SERVICE_LOCK_DOOR)
            await _get_api(hass, vin).lock_door(vin)
            _targeted_refresh(hass, vin, "vehicle_data", "get_vehicle_data")

        async def handle_unlock_door(call: ServiceCall) -> None:
            vin = _resolve_vin(hass, call)
            _require_action(hass, vin, SERVICE_UNLOCK_DOOR)
            await _get_api(hass, vin).unlock_door(vin)
            _targeted_refresh(hass, vin, "vehicle_data", "get_vehicle_data")

        async def handle_lock_glovebox(call: ServiceCall) -> None:
            vin = _resolve_vin(hass, call)
            _require_action(hass, vin, SERVICE_LOCK_GLOVEBOX)
            await _get_api(hass, vin).lock_glovebox(vin, call.data[ATTR_PIN])
            _targeted_refresh(hass, vin, "vehicle_data", "get_vehicle_data")

        async def handle_unlock_glovebox(call: ServiceCall) -> None:
            vin = _resolve_vin(hass, call)
            _require_action(hass, vin, SERVICE_UNLOCK_GLOVEBOX)
            await _get_api(hass, vin).unlock_glovebox(vin)
            _targeted_refresh(hass, vin, "vehicle_data", "get_vehicle_data")

        async def handle_request_location(call: ServiceCall) -> None:
            vin = _resolve_vin(hass, call)
            _require_action(hass, vin, SERVICE_REQUEST_LOCATION)
            await _get_api(hass, vin).request_location(vin)
            _targeted_refresh(hass, vin, "location", "get_location")

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
        hass.services.async_register(DOMAIN, SERVICE_START_CHARGING, handle_start_charging, VIN_SCHEMA)
        hass.services.async_register(DOMAIN, SERVICE_STOP_CHARGING, handle_stop_charging, VIN_SCHEMA)
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
        hass.services.async_register(DOMAIN, SERVICE_REQUEST_LOCATION, handle_request_location, VIN_SCHEMA)
        hass.services.async_register(DOMAIN, SERVICE_REFRESH, handle_refresh, VIN_SCHEMA)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        entry_data = hass.data[DOMAIN].pop(entry.entry_id)
        _release_vehicles(hass, entry, entry_data["duplicate_issues"])
        if not hass.data.get(DOMAIN):
            for service in ALL_SERVICES:
                hass.services.async_remove(DOMAIN, service)
    return unload_ok


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Drop the location sharing notices of a removed entry.

    They are kept on unload so an ignored one stays ignored; once the entry
    is gone for good nothing would ever clear them.
    """
    registry = dr.async_get(hass)
    for device in dr.async_entries_for_config_entry(registry, entry.entry_id):
        for domain, vin in device.identifiers:
            if domain == DOMAIN:
                ir.async_delete_issue(hass, DOMAIN, f"location_sharing_off_{vin}")
