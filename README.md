# Lynk & Co Home Assistant Integration

Custom [Home Assistant](https://www.home-assistant.io/) integration for 2025 Lynk & Co vehicles (01, 02, 08) via [HACS](https://hacs.xyz/).

This HACS plugin was entirely reverse engineered and vibe-coded. It should work for the European Lynk&Co vehicles on the new platform (facelift 01, 02, 08).

It was tested with the 2025 Lynk&Co 01.

## Features

### Sensors
- **Battery**: level (%), range (km), charging status, charging speed (kW), time remaining, charge limit
- **Fuel** (01/08 PHEV only): level (%), range (km), average consumption (L/100km), fuel type
- **Climate**: interior temperature, target temperature, HVAC status
- **Vehicle**: odometer, central lock status, address

### Binary Sensors
- 4 doors (front/rear left/right)
- 4 windows (front/rear left/right)
- Sunroof, hood, trunk

### Device Tracker
- GPS location with coordinates

### Lock
- Door lock / unlock

### Actions (Services)
Actions are available in v0.2.0 and above. As of right now, they are untested. 
| Service | Description | Required parameters | Confirmed working*
|---|---|---|---|
| `lynkco.refresh` | Force-refresh all sensors now | none | ✅ 
| `lynkco.flash_lights` | Flash the vehicle's lights | `vin` | ✅ 
| `lynkco.honk_horn` | Honk the horn | `vin`
| `lynkco.open_sunroof` | Open the sunroof | `vin` | ✅
| `lynkco.close_sunroof` | Close the sunroof | `vin` | ✅
| `lynkco.set_charge_limit` | Set charge limit | `vin`, <br> `percent` (between 50 and 100) |
| `lynkco.start_conditioning` | Start air conditioning | `vin`<br /> `temp` (number between 16 and 28) |
| `lynkco.stop_conditioning` | Stop air conditioning | `vin` |
| `lynkco.start_ventilate` | Start ventilation | `vin` |
| `lynkco.stop_ventilate` | Stop ventilation | `vin` |
| `lynkco.start_heaters` | Start seat/steering heaters | `vin` |
| `lynkco.stop_heaters` | Stop heaters | `vin` |

<sup><sub>\* Confirmed on a Lynk&Co 01, 2025 model</sup></sub>

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
2. A login URL is generated — open it in your browser
3. Log in with your Lynk & Co email + password + SMS MFA code
4. After MFA, the browser will fail to open `msauth://...`
5. Open DevTools (F12) → Network tab → find the last request → copy the `Location` header value (note: Firefox dev tools don't show the entire header. Right click on the request and copy the response headers instead, and then get the `msauth://` header from there)
6. Paste the full `msauth://...` URL back in Home Assistant

This process should be similar to the HACS integration for pre-2025 Lynk&Co cars such as the [Donkie](https://github.com/Donkie/Hass-Lynk-Co) one. 

Tokens are automatically refreshed. You should only need to re-authenticate if the refresh token expires.

## Polling

Vehicle data is polled every 15 minutes by default.

## Supported Models

Tested with the 2025 platform used by:
- Lynk & Co 01 (PHEV) - confirmed working
- Lynk & Co 02 (BEV) - not tested
- Lynk & Co 08 - not tested

> **Note**: Pre-2025 Lynk & Co 01 models use a different platform and are NOT supported. You can try your luck with [this](https://github.com/Donkie/Hass-Lynk-Co) repo. 

## Credits

API reverse-engineered from the Lynk & Co Android app v2.55.0.
