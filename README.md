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

> **Note**: Pre-2025 Lynk & Co 01 models use a different platform and are NOT supported.

## Credits

API reverse-engineered from the Lynk & Co Android app v2.55.0.
