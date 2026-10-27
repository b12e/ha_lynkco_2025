# Lynk & Co Home Assistant Integration
![Usage counter](https://img.shields.io/badge/dynamic/json?color=41BDF5&logo=home-assistant&label=integration%20usage&suffix=%20installs&cacheSeconds=15600&url=https://raw.githubusercontent.com/b12e/hacs-b12e-usage-stats/refs/heads/main/usage.json&query=$.integrations.lynkco.total_usage) 

Custom [Home Assistant](https://www.home-assistant.io/) integration for Lynk & Co vehicles (>MY25 01, 02 and 08), installable from the Home Assistant [Marketplace](https://www.home-assistant.io/integrations/marketplace/) (Home Assistant 2026.11 and newer) or [HACS](https://hacs.xyz/) (2026.10 and older).

If you like the integration, make sure to show your love by giving it a ⭐. 

Pull requests are currently turned off (to prevent AI slop). If you have any feature requests or issues, please [create an issue](https://github.com/b12e/ha_lynkco_2025/issues/new/choose) using the template provided. 

## Supported Models

Tested on the following vehicles:
- 2025 (New/Facelift) Lynk & Co 01 (PHEV) and newer
- Lynk & Co 02 (BEV)
- Lynk & Co 08 (PHEV)
- Pre-2025 Lynk & Co 01: sensors plus the actions owners have confirmed, see below

Other models are currently not available on the EU market, although it is likely when they do become available they are on the same platform and will work. The documentation will be updated accordingly as soon as this happens.

The integration identifies your car by its model code (`CX11_A3`, `E335`, `DX11`, `CX11_A1`) and by the car guide type the API reports (model year for pre-2025 01s, Core/More for newer cars). Both are shown on the device page and in the diagnostics download. Remote actions are only enabled for models where they are confirmed to work; everything the API itself tells us (BEV vs PHEV, which heater zones exist, whether the glovebox can be locked) is detected automatically.

> [!NOTE]
> Pre-2025 01s run on a different vehicle platform, but [owners report](https://github.com/b12e/ha_lynkco_2025/issues/33) that the same API serves them. On these cars the integration exposes all sensors the API returns data for, plus the actions owners have confirmed; everything else stays disabled until confirmed. See the [pre-2025 01 wiki page](https://github.com/b12e/ha_lynkco_2025/wiki/Lynk-%26-Co-01-(pre-2025)) for the full list and how to confirm a feature. [Hass-Lynk-Co](https://github.com/Donkie/Hass-Lynk-Co) remains an alternative for these cars.

A car with a model code the integration has never seen gets the same treatment, plus a notice under Settings → Repairs that links straight to the model report form.

# Installation

[![Open your Home Assistant instance and open this repository in the Marketplace or HACS.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=b12e&repository=ha_lynkco_2025&category=integration)

## Marketplace (Home Assistant 2026.11 and newer)
Starting with Home Assistant 2026.11, HACS ships as part of Home Assistant itself under the name [Marketplace](https://www.home-assistant.io/integrations/marketplace/). It uses the same catalog, so this integration is available there without adding a custom repository.
1. Go to Settings → Marketplace
2. Search for "Lynk & Co" and click Install
3. Restart Home Assistant
4. Go to Settings → Devices & services → + Add Integration → Lynk & Co

> [!NOTE]
> If you installed the integration through HACS before upgrading to 2026.11, nothing changes: it stays installed and keeps receiving updates through the Marketplace.

## HACS (Home Assistant 2026.10 and older)
1. Make sure [HACS](https://hacs.xyz) is installed in your Home Assistant installation
2. Search for "Lynk & Co" and click Download. Follow the on-screen instructions.
3. Restart Home Assistant
4. Go to Settings → Devices & services → + Add Integration → Lynk & Co

## Manual
Copy `custom_components/lynkco/` to your Home Assistant `custom_components` directory.

# Setup

The integration uses Azure AD B2C authentication with MFA in the same way the mobile app uses it. Setup requires a one-time browser login:

1. Add the integration in Home Assistant
2. A login URL is generated - open it in your browser
3. Open DevTools (F12) → Network tab
4. Log in with your Lynk & Co email + password + SMS MFA code
5. After MFA, the browser will fail to open `msauth://...`
6. In the network tab of your developer tools, find the last request → copy the `Location` header value
7. Paste the full `msauth://...` URL back in Home Assistant

> [!TIP]
> Firefox dev tools don't show the entire header. Right click on the request and copy the response headers instead, and then get the `msauth://` header from there.

This process should be similar to the HACS integration for pre-2025 Lynk&Co cars such as the [Donkie](https://github.com/Donkie/Hass-Lynk-Co) one. 

Tokens are automatically refreshed. You should only need to re-authenticate if the refresh token expires (e.g. if your Home Assistant instance has been offline for an extended period of time, or when you log in on the mobile app).

## Limitations

> [!WARNING]
> Lynk&Co only allows 1 device to be logged in to the app at all times. This sadly also means that, when you log in to Home Assistant, your mobile app will automatically be logged out and vice versa. The workaround is to create a Home Assistant dashboard that replaces the Lynk&Co mobile app.

> [!TIP]
> Since late September, Lynk&Co allows to share your car with up to 3 additional Lynk&Co accounts. You could potentially create a new account, share the car with this account, and then use that account with HA or on your mobile phone. I've so far not tested this functionality. If there are issues, please open an issue.

# Features

Every sensor, entity and action is documented per car model in the wiki, with its status on that model:

- [Lynk & Co 01 (>MY2025)](https://github.com/b12e/ha_lynkco_2025/wiki/Lynk-&-Co-01-(2025-Facelift))
- [Lynk & Co 02](https://github.com/b12e/ha_lynkco_2025/wiki/Lynk-%26-Co-02)
- [Lynk & Co 08](https://github.com/b12e/ha_lynkco_2025/wiki/Lynk-%26-Co-08)
- [Lynk & Co 01 (pre-2025)](https://github.com/b12e/ha_lynkco_2025/wiki/Lynk-&-Co-01-(2021%E2%80%902024))

In short: battery, fuel (PHEV), climate and heater sensors, odometer and address, grouped door and window sensors, a GPS device tracker, door and glovebox locks, a charging switch, a climate entity, refresh and update-location buttons, and `lynkco.*` actions for everything the official app can do remotely (lock, lights, horn, sunroof, charging, charge limit, climate, ventilation, heaters, glovebox, location request). The [wiki home page](https://github.com/b12e/ha_lynkco_2025/wiki) explains how a feature gets its status on a model and how to confirm one.

A redacted diagnostics download (device page → ⋮ → Download diagnostics) shows model code, guide type, enabled features, failing endpoints and all raw payloads; attach it to issues.

# Polling

The full vehicle data is polled every 15 minutes by default. On top of that, only endpoints relevant to what's happening are fast-polled (about every 60 seconds), instead of refetching everything:
- **While driving:** location, drive state and battery. The final location is fetched once when you reach your destination (on LynkOS 1.4.0+ the car only reports location when it stops if you've granted permission to do so in Settings -> System -> Privacy on your infotainment screen).
- **While the climate/conditioning system is active:** the climate state.

When you perform an action (e.g. lock the doors or start the heaters), only the relevant data is refreshed - not everything. The integration checks for a state change after 3 seconds, and if the car hasn't processed the command yet, retries after 5 and then 10 seconds before giving up. Fire-and-forget actions like flashing the lights or honking the horn don't trigger a refresh at all.

Custom polling intervals can be configured using the gear icon after setting up the integration, however as to protect Lynk&Co's infrastructure, the default intervals are also the minimum intervals. Only longer intervals can be configured.

# Screenshot

<img width="1260" height="871" alt="image" src="https://github.com/user-attachments/assets/bc763f0a-7b3a-44d6-917f-8ea24ba05ce2" />

# Credits

API reverse-engineered from the Lynk & Co Android app v2.55.0 and v2.63.0, and verified against v2.67.0.

This integration is not endorsed by Lynk&Co and I have no affiliation with them whatsoever.
