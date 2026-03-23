# Lynk & Co Home Assistant Integration

Custom [Home Assistant](https://www.home-assistant.io/) integration for 2025 Lynk & Co vehicles (01, 02, 08) via [HACS](https://hacs.xyz/).

This HACS plugin was vibe-coded by decompiling the Lynk&Co Android app and letting Claude Code have a run at the code to figure out endpoints and authentication. Claude then wrote the python - although I'm not a stranger to python, it was just easier this way :) 

It works for the European Lynk&Co vehicles on the new platform (facelift 01, 02 and probably the 08). I've tested myself with the 2025 Lynk&Co 01 and have had confirmation it works for the Lynk&Co 02 BEV.

Pull Requests are disabled until further notice.

## Features

### Sensors
| Entity | Description | Unit |
|---|---|---|
| Battery level | State of charge | % |
| Electric range | Remaining electric range | km |
| Charging status | Current charging state (charging, fully_charged, etc.) | - |
| Charging speed | Current charging power | kW |
| Charging time remaining | Time until fully charged | min |
| Charge limit | Configured charge limit | % |
| Battery capacity | Total battery capacity | kWh |
| Battery energy | Current energy in battery (capacity x SoC) | kWh |
| Fuel level | Remaining fuel (PHEV only) | % |
| Fuel range | Remaining fuel range (PHEV only) | km |
| Average fuel consumption | Average fuel consumption (PHEV only) | L/100km |
| Fuel type | Fuel type (PHEV only) | - |
| Interior temperature | Current cabin temperature | °C |
| Target temperature | HVAC target temperature | °C |
| Climate status | HVAC state | - |
| Central lock | Lock state (locked/unlocked) | - |
| Address | Last known address | - |
| Odometer | Total distance driven | km |

### Binary Sensors
| Entity | Device class |
|---|---|
| Front left door | door |
| Front right door | door |
| Rear left door | door |
| Rear right door | door |
| Front left window | window |
| Front right window | window |
| Rear left window | window |
| Rear right window | window |
| Sunroof | window |
| Hood | door |
| Trunk | door |

### Device Tracker
- GPS location with coordinates

### Lock
- Door lock / unlock

### Actions (Services)

All services (except `lynkco.refresh`) accept an optional `vin` parameter. When only one vehicle is configured, the VIN is auto-detected and can be omitted.
| Service | Description | Parameters | 01 (facelift) | 02 | 08 |
|---|---|---|---|---|---|
| `lynkco.refresh` | Force-refresh all sensors now | | ✅ | ✅ | |
| `lynkco.lock_door` | Lock the vehicle's doors | | ✅ | ✅ | |
| `lynkco.unlock_door` | Unlock the vehicle's doors | | ✅ | ✅ | |
| `lynkco.flash_lights` | Flash the vehicle's lights | | ✅ | | |
| `lynkco.honk_horn` | Honk the horn | | t.b.c. | | |
| `lynkco.open_sunroof` | Open the sunroof | | ✅ | | |
| `lynkco.close_sunroof` | Close the sunroof | | ✅ | | |
| `lynkco.set_charge_limit` | Set charge limit | `percent` (50-100) | t.b.c. | | |
| `lynkco.start_conditioning` | Start air conditioning | `temp` (16-28°C) | t.b.c. | | |
| `lynkco.stop_conditioning` | Stop air conditioning | | t.b.c. | | |
| `lynkco.start_ventilate` | Start ventilation | | t.b.c. | | |
| `lynkco.stop_ventilate` | Stop ventilation | | t.b.c. | | |
| `lynkco.start_heaters` | Start seat/steering heaters | | t.b.c. | | |
| `lynkco.stop_heaters` | Stop heaters | | t.b.c. | | |

✅ = confirmed working on that model

### Screenshot

![screenshot](screenshot.png)

## Installation

### HACS (recommended)
1. Add this repository as a custom repository in HACS
2. Install "Lynk & Co"
3. Restart Home Assistant
4. Go to Settings → Integrations → Add → Lynk & Co

### Manual
Copy `custom_components/lynkco/` to your Home Assistant `custom_components` directory.

## Setup

The integration uses Azure AD B2C authentication with MFA. Setup requires a one-time browser login:

1. Add the integration in Home Assistant
2. A login URL is generated - open it in your browser
3. Log in with your Lynk & Co email + password + SMS MFA code
4. After MFA, the browser will fail to open `msauth://...`
5. Open DevTools (F12) → Network tab → find the last request → copy the `Location` header value (note: Firefox dev tools don't show the entire header. Right click on the request and copy the response headers instead, and then get the `msauth://` header from there)
6. Paste the full `msauth://...` URL back in Home Assistant

This process should be similar to the HACS integration for pre-2025 Lynk&Co cars such as the [Donkie](https://github.com/Donkie/Hass-Lynk-Co) one. 

Tokens are automatically refreshed. You should only need to re-authenticate if the refresh token expires.

## Polling

Vehicle data is polled every 15 minutes by default. If you want to poll more frequently, you can do so using Home Assistant automations by calling the update action, although I don't recommend to update more often 24/7. 

Data is also refreshed by default after any other action is called.

## Supported Models

Tested with the 2025 platform used by:
- Lynk & Co 01 (PHEV) - confirmed working
- Lynk & Co 02 (BEV) - confirmed working
- Lynk & Co 08 (PHEV) - not tested

> **Note**: Pre-2025 Lynk & Co 01 models use a different platform and are NOT supported. You can try your luck with [this](https://github.com/Donkie/Hass-Lynk-Co) repo. 

## Credits

API reverse-engineered from the Lynk & Co Android app v2.55.0.

This HACS plugin is not endorsed by Lynk&Co and I have no affiliation with them whatsoever.
