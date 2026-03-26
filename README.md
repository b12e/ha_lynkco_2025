# Lynk & Co Home Assistant Integration

Custom [Home Assistant](https://www.home-assistant.io/) integration for 2025 Lynk & Co vehicles (01, 02, 08) via [HACS](https://hacs.xyz/).

Pull Requests are disabled until further notice.

## Supported Models

Tested on the following vehicles:
- 2025 (New) Lynk & Co 01 (PHEV)
- 2025 Lynk & Co 02 (BEV)
- 2025 Lynk & Co 08 (PHEV)

Other models are currently not available on the EU market, although it is likely when they do become available they are on the same platform and will work. The documentation will be updated accordingly as soon as this happens.

> **Note**: Pre-2025 Lynk & Co 01 models use a different platform and are NOT supported. You can try your luck with [this](https://github.com/Donkie/Hass-Lynk-Co) repo.

## Polling

Vehicle data is polled every 15 minutes by default. If you want to poll more frequently, you can do so using Home Assistant automations by calling the update action, although I don't recommend to update more often clock-round.

Data is also refreshed by default 15 seconds after any action is called.

## ⚠️ Limitations

- Lynk&Co only allows 1 device to be logged in to the app at all times. This sadly also means that, when you log in to Home Assistant, your mobile app will automatically be logged out and vice versa. The workaround is to create a Home Assistant dashboard that replaces the Lynk&Co mobile app.

## Features

### Sensors
| Entity | Description | Unit | Model Availability
|---|---|---|---|
| Battery level | State of charge | % | All
| Electric range | Remaining electric range | km | All
| Charging status | Current charging state (charging, fully_charged, etc.) | - | All
| Charging speed | Current charging power | kW | All
| Charging time remaining | Time until fully charged | min | All
| Charge limit | Configured charge limit | % | All
| Battery capacity | Total battery capacity | kWh | All
| Battery energy | Current energy in battery (capacity x SoC) | kWh | All
| Fuel level | Remaining fuel | % | 01 / 08
| Fuel range | Remaining fuel range | km | 01 / 08
| Average fuel consumption | Average fuel consumption | L/100km | 01 / 08
| Fuel type | Fuel type | - | 01 / 08
| Interior temperature | Current cabin temperature | °C | All
| Target temperature | HVAC target temperature | °C | All
| Climate status | HVAC state | - | All
| Central lock | Lock state (locked/unlocked) | - | All
| Address | Last known address | - | All
| Odometer | Total distance driven | km | All 

### Binary Sensors
| Entity | Device class | Model Availability
|---|---|--|
| Front left door | door | All
| Front right door | door | All
| Rear left door | door | All
| Rear right door | door | All
| Front left window | window | All
| Front right window | window | All
| Rear left window | window | All
| Rear right window | window | All
| Sunroof | window | 01 / 08
| Hood | door | All
| Trunk | door | All

### Device Tracker
- GPS location with coordinates

### Lock
- Door lock / unlock

### Actions (Services)

All actions (except `lynkco.refresh`) accept an optional `vin` parameter. When only one vehicle is configured, the VIN is auto-detected and can be omitted.

| Service | Description | Parameters | 01 (facelift) | 02 | 08 |
|---|---|---|---|---|---|
| `lynkco.refresh` | Force-refresh all sensors now | | ✅ | ✅ | ✅ |
| `lynkco.lock_door` | Lock the vehicle's doors | | ✅ | ✅ | ✅ |
| `lynkco.unlock_door` | Unlock the vehicle's doors | | ✅ | ✅ | ✅ |
| `lynkco.flash_lights` | Flash the vehicle's lights | | ✅ | ✅ | |
| `lynkco.honk_horn` | Honk the horn | | t.b.c. | ✅ | |
| `lynkco.open_sunroof` | Open the sunroof | | ✅ | ❌ |
| `lynkco.close_sunroof` | Close the sunroof | | ✅ | ❌ |
| `lynkco.set_charge_limit` | Set charge limit | `percent` (50-100) | t.b.c. | ✅ |
| `lynkco.start_conditioning` | Start air conditioning | `temp` (16-28) | t.b.c. | ✅ |
| `lynkco.stop_conditioning` | Stop air conditioning | | t.b.c. | ✅ |
| `lynkco.start_ventilate` | Start ventilation | | t.b.c. |✅||
| `lynkco.stop_ventilate` | Stop ventilation | | t.b.c. | ✅
| `lynkco.start_heaters` | Start heaters | `heaters` (list) | ✅ | | |
| `lynkco.stop_heaters` | Stop heaters | `heaters` (list) | ✅ | | |

#### Notes:
- ✅ = confirmed working on that model<br />
- Sunroof actions aren't available on the Lynk&Co 02 as it doesn't have a sunroof that can open.<br />
- `temp` is in ºC.
- `heaters` accepts a list of zones (see table below)

**Note:** Seat and steering wheel heaters require the climate system to be active first (use `start_conditioning` before `start_heaters`).

#### Heater zones

| Zone | 01 | 02 | 08 |
|---|---|---|---|
| `front_left_seat` | ✅ | ✅ | ✅ |
| `front_right_seat` | ✅ | ✅ | ✅ |
| `rear_left_seat` | ❌ | ❌ | ✅ (More only) |
| `rear_right_seat` | ❌ | ❌ | ✅ (More only) |
| `steering_wheel` | ✅ (More only) | ✅ (More only) | ✅ (More only) |
| `defrost` | ✅ | ✅ | ✅ |

#### Example: start heaters
```yaml
service: lynkco.start_heaters
data:
  heaters:
    - front_left_seat
    - steering_wheel
```


### Screenshot

![screenshot](screenshot.png)

# Installation

## HACS (recommended)
1. Add this repository as a custom repository in HACS
2. Install "Lynk & Co"
3. Restart Home Assistant
4. Go to Settings → Integrations → Add → Lynk & Co

## Manual
Copy `custom_components/lynkco/` to your Home Assistant `custom_components` directory.

# Setup

The integration uses Azure AD B2C authentication with MFA in the same way the mobile app uses it. Setup requires a one-time browser login:

1. Add the integration in Home Assistant
2. A login URL is generated - open it in your browser
3. Open DevTools (F12) → Network tab
4. Log in with your Lynk & Co email + password + SMS MFA code
5. After MFA, the browser will fail to open `msauth://...`
6. In the network tab of your developer tools, find the last request → copy the `Location` header value (note: Firefox dev tools don't show the entire header. Right click on the request and copy the response headers instead, and then get the `msauth://` header from there)
7. Paste the full `msauth://...` URL back in Home Assistant

This process should be similar to the HACS integration for pre-2025 Lynk&Co cars such as the [Donkie](https://github.com/Donkie/Hass-Lynk-Co) one. 

Tokens are automatically refreshed. You should only need to re-authenticate if the refresh token expires (e.g. if your Home Assistant instance has been offline for an extended period of time, or when you log in on the mobile app).

# Credits

API reverse-engineered from the Lynk & Co Android app v2.55.0.

This HACS plugin is not endorsed by Lynk&Co and I have no affiliation with them whatsoever.
