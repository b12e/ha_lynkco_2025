"""Diagnostics support for Lynk & Co.

Settings > Devices & services > Lynk & Co > device > Download diagnostics gives
a redacted JSON of every API payload the integration holds for that car. It is
what owners of a model without its own feature file (or of a pre-2025 01)
attach to a model report so unconfirmed features can be verified from real data.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntry

from .const import DOMAIN
from .coordinator import LynkCoCoordinator

# Exact JSON keys whose values are replaced (async_redact_data matches keys, not fragments)
TO_REDACT = {
    "vin",
    "access_token",
    "refresh_token",
    "device_id",
    "temId",
    "registrationNumber",
    "vehicleName",
    "carName",
    "latitude",
    "longitude",
    "coordinates",
    "longAddress",
    "shortAddress",
}


def _vehicle_diagnostics(coordinator: LynkCoCoordinator) -> dict[str, Any]:
    return async_redact_data(
        {
            "model_code": coordinator.model,
            "guide_type": coordinator.guide_type,
            "model_name": coordinator.model_name,
            "propulsion": coordinator.propulsion,
            "features": coordinator.features.as_dict(),
            "endpoint_errors": dict(coordinator.endpoint_errors),
            "data": coordinator.data,
        },
        TO_REDACT,
    )


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for every vehicle on the account."""
    data = hass.data[DOMAIN][entry.entry_id]
    return {
        "options": dict(entry.options),
        "vehicles": [_vehicle_diagnostics(c) for c in data["coordinators"].values()],
    }


async def async_get_device_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry, device: DeviceEntry
) -> dict[str, Any]:
    """Return diagnostics for one vehicle (device)."""
    data = hass.data[DOMAIN][entry.entry_id]
    vins = {identifier for domain, identifier in device.identifiers if domain == DOMAIN}
    for vin, coordinator in data["coordinators"].items():
        if vin in vins:
            return _vehicle_diagnostics(coordinator)
    return {"error": "vehicle not found for this device"}
