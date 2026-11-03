<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="custom_components/lynkco/brand/dark_logo.png">
    <img src="custom_components/lynkco/brand/logo.png" alt="Lynk & Co" width="320">
  </picture>
</p>

<h1 align="center">Lynk &amp; Co for Home Assistant</h1>

<p align="center">
  Your Lynk &amp; Co 01, 02 or 08 in Home Assistant: battery and charging, climate, doors and locks, location,<br>
  and every remote action the official app has.
</p>

<p align="center">
  <a href="https://github.com/b12e/ha_lynkco_2025/releases"><img alt="Release" src="https://img.shields.io/github/v/release/b12e/ha_lynkco_2025?display_name=tag&label=release&color=41BDF5"></a>
  <a href="https://my.home-assistant.io/redirect/hacs_repository/?owner=b12e&repository=ha_lynkco_2025&category=integration"><img alt="HACS" src="https://img.shields.io/badge/HACS-Default-41BDF5?logo=homeassistantcommunitystore&logoColor=white"></a>
  <img alt="Home Assistant 2025.1 and newer" src="https://img.shields.io/badge/Home%20Assistant-2025.1%2B-18BCF2?logo=homeassistant&logoColor=white">
  <a href="https://github.com/b12e/ha_lynkco_2025/actions/workflows/validate.yml"><img alt="Validate" src="https://img.shields.io/github/actions/workflow/status/b12e/ha_lynkco_2025/validate.yml?branch=main&label=validate"></a>
  <img alt="Installs" src="https://img.shields.io/badge/dynamic/json?color=41BDF5&logo=home-assistant&label=installs&cacheSeconds=15600&url=https://raw.githubusercontent.com/b12e/hacs-b12e-usage-stats/refs/heads/main/usage.json&query=$.integrations.lynkco.total_usage">
  <a href="LICENSE"><img alt="License" src="https://img.shields.io/github/license/b12e/ha_lynkco_2025?color=blue"></a>
</p>

<p align="center">
  <a href="#installation">Installation</a> ·
  <a href="#setup">Setup</a> ·
  <a href="#what-you-get">What you get</a> ·
  <a href="#polling">Polling</a> ·
  <a href="https://github.com/b12e/ha_lynkco_2025/wiki">Wiki</a> ·
  <a href="https://github.com/b12e/ha_lynkco_2025/issues/new/choose">Report an issue</a>
</p>

<p align="center">
  <img src="https://github.com/user-attachments/assets/184aa864-c625-482a-b342-fee780f978b9" alt="Mock-up of a dashboard card built from the integration's entities" width="880">
</p>

<table align="center">
  <tr>
    <td align="center" width="33%">
      <img src="https://github.com/user-attachments/assets/4caf8fca-4369-4756-9b16-2a9ae19e880b" width="32" height="32" alt=""><br>
      <b>Battery and charging</b><br>
      <sub>Level, range, charging speed and time left, charge limit, start and stop charging</sub>
    </td>
    <td align="center" width="33%">
      <img src="https://github.com/user-attachments/assets/a0adf448-ba88-4539-8bab-940441c05695" width="32" height="32" alt=""><br>
      <b>Climate</b><br>
      <sub>Pre-conditioning with a target temperature, seat, steering wheel and windshield heaters, ventilation</sub>
    </td>
    <td align="center" width="33%">
      <img src="https://github.com/user-attachments/assets/77cde8b0-184c-4618-afbb-0cc23498c438" width="32" height="32" alt=""><br>
      <b>Doors and locks</b><br>
      <sub>Central lock, glovebox lock with a PIN, door, window, hood, trunk and sunroof sensors</sub>
    </td>
  </tr>
  <tr>
    <td align="center">
      <img src="https://github.com/user-attachments/assets/127a12da-d96d-4add-95b1-a97229163dfc" width="32" height="32" alt=""><br>
      <b>Location</b><br>
      <sub>A GPS device tracker and the address, refreshed while driving and on demand</sub>
    </td>
    <td align="center">
      <img src="https://github.com/user-attachments/assets/88936426-14e1-4be6-a8db-60c9b728c718" width="32" height="32" alt=""><br>
      <b>Fuel and trip data</b><br>
      <sub>Fuel level, range and consumption on hybrids, odometer, electric consumption</sub>
    </td>
    <td align="center">
      <img src="https://github.com/user-attachments/assets/75342005-89ee-4881-8ae6-8aabb8230e58" width="32" height="32" alt=""><br>
      <b>Remote actions</b><br>
      <sub>Lock, lights, horn, sunroof, charging, climate, heaters, ventilation, glovebox, location request</sub>
    </td>
  </tr>
</table>

## Supported models

| Model | Powertrain | Model code | Support | Details |
| --- | --- | --- | --- | --- |
| Lynk &amp; Co 01, 2025 facelift and newer | PHEV | `CX11_A3` | Everything | [wiki](https://github.com/b12e/ha_lynkco_2025/wiki/Lynk-&-Co-01-(2025-Facelift)) |
| Lynk &amp; Co 02 | BEV | `E335` | Everything (no sunroof) | [wiki](https://github.com/b12e/ha_lynkco_2025/wiki/Lynk-%26-Co-02) |
| Lynk &amp; Co 08 | PHEV | `DX11` | Everything | [wiki](https://github.com/b12e/ha_lynkco_2025/wiki/Lynk-%26-Co-08) |
| Lynk &amp; Co 01, 2021 to 2024 | PHEV, HEV | `CX11_A1` | Sensors, plus the actions owners confirmed | [wiki](https://github.com/b12e/ha_lynkco_2025/wiki/Lynk-&-Co-01-(2021%E2%80%902024)) |

> [!NOTE]
> Pre-2025 01s run on a different vehicle platform, but [owners report](https://github.com/b12e/ha_lynkco_2025/issues/33) that the same API serves them. On these cars the integration exposes every sensor the API returns data for, plus the actions owners have confirmed; everything else stays disabled until confirmed. [Hass-Lynk-Co](https://github.com/Donkie/Hass-Lynk-Co) remains an alternative for these cars.

Remote actions are only enabled on models where they are confirmed to work. A car with a model code the integration has never seen gets the same careful treatment, plus a notice under Settings → Repairs that links straight to the [model report form](https://github.com/b12e/ha_lynkco_2025/issues/new?template=model_report.yml). Other models are not on the EU market yet; they most likely share the platform and will be added as soon as an owner reports one.

## Installation

<a href="https://my.home-assistant.io/redirect/hacs_repository/?owner=b12e&repository=ha_lynkco_2025&category=integration"><img src="https://my.home-assistant.io/badges/hacs_repository.svg" alt="Open your Home Assistant instance and open this repository in the Marketplace or HACS."></a>

<details open>
<summary><b>Marketplace</b> (Home Assistant 2026.11 and newer)</summary>

Starting with Home Assistant 2026.11, HACS ships as part of Home Assistant itself under the name [Marketplace](https://www.home-assistant.io/integrations/marketplace/). It uses the same catalog, so this integration is available there without adding a custom repository.

1. Go to Settings → Marketplace
2. Search for "Lynk & Co" and click Install. The setup wizard opens by itself; if not, go to Settings → Devices & services → Add integration → Lynk & Co

</details>

<details>
<summary><b>HACS</b> (Home Assistant 2026.10 and older)</summary>

1. Make sure [HACS](https://hacs.xyz) is installed
2. Search for "Lynk & Co" and click Download, then follow the on-screen instructions
3. Restart Home Assistant
4. Go to Settings → Devices & services → Add integration → Lynk & Co

</details>

<details>
<summary><b>Manual</b></summary>

Copy `custom_components/lynkco/` into the `custom_components` directory of your Home Assistant configuration and restart.

</details>

## Setup

The integration logs in the same way the mobile app does: Azure AD B2C with SMS verification. It takes a one-time browser login:

1. Add the integration in Home Assistant
2. A login URL is generated - open it in your browser
3. Open the browser's DevTools (F12) → Network tab
4. Log in with your Lynk & Co email, password and SMS code
5. After the SMS step the browser fails to open `msauth://...`, which is expected
6. In the Network tab, find the last request and copy the `Location` header value
7. Paste that `msauth://...` URL back into Home Assistant

> [!TIP]
> - Firefox does not show the whole header in the panel. Right-click the request and copy the response headers; the full `msauth://` value is in there.
> - Chrome and Firefox are the easiest browsers for this. Safari makes it harder.
> - Pasting the whole copied header block works too; the integration picks the code out of it.

Tokens refresh themselves. A new login is only needed when the refresh token expires, for example after a long offline period, or when Lynk & Co invalidates it; Home Assistant then shows a Repairs entry that opens the login again.

### Limitations

> [!WARNING]
> Lynk & Co allows one device per account to be logged in. When Home Assistant logs in, the mobile app is logged out, and when the app logs in, Home Assistant takes the session back at its next request. Either build a dashboard that replaces the app, or share the car with a second account, as below.

> [!TIP]
> Since late September, Lynk & Co lets you share your car with up to 2 additional accounts. To use the app and Home Assistant side by side:
> 1. In your primary account, in the mobile app, go to Car Settings → Additional drivers and copy the invite link. Keep it somewhere safe, such as the notes app on your phone.
> 2. Log out of your primary account.
> 3. Create a new Lynk & Co account with another email address and phone number (for the SMS code) and go through the app onboarding until you are logged in with the secondary account.
> 4. Open the invite link from step 1. The app opens with a prompt to accept the invitation.
>
> Use either account in Home Assistant and the other one in the app. One car should be set up through one account only; a second entry for the same car is skipped with a Repairs notice.

## What you get

Every sensor, entity and action is documented per model in the wiki, with its status on that model: [01 (2025 facelift)](https://github.com/b12e/ha_lynkco_2025/wiki/Lynk-&-Co-01-(2025-Facelift)), [02](https://github.com/b12e/ha_lynkco_2025/wiki/Lynk-%26-Co-02), [08](https://github.com/b12e/ha_lynkco_2025/wiki/Lynk-%26-Co-08), [01 (2021 to 2024)](https://github.com/b12e/ha_lynkco_2025/wiki/Lynk-&-Co-01-(2021%E2%80%902024)).

| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;  | Entities | Actions |
| --- | --- | --- |
| <img src="https://github.com/user-attachments/assets/4caf8fca-4369-4756-9b16-2a9ae19e880b" width="20" height="20" alt=""> | Battery level, electric range, charging status, speed and time remaining, charge limit, battery capacity and energy, electric consumption, charging switch | `start_charging`, `stop_charging`, `set_charge_limit` |
| <img src="https://github.com/user-attachments/assets/88936426-14e1-4be6-a8db-60c9b728c718" width="20" height="20" alt=""> | Fuel level and percentage, fuel range, fuel consumption, fuel type, tank capacity, odometer | |
| <img src="https://github.com/user-attachments/assets/a0adf448-ba88-4539-8bab-940441c05695" width="20" height="20" alt=""> | Climate entity, climate status, interior and target temperature, a sensor per heater zone | `start_conditioning`, `stop_conditioning`, `start_heaters`, `stop_heaters`, `start_ventilate`, `stop_ventilate` |
| <img src="https://github.com/user-attachments/assets/77cde8b0-184c-4618-afbb-0cc23498c438" width="20" height="20" alt=""> | Door lock, glovebox lock, central lock status, doors, windows, hood, trunk, sunroof, car running | `lock_door`, `unlock_door`, `lock_glovebox`, `unlock_glovebox`, `open_sunroof`, `close_sunroof` |
| <img src="https://github.com/user-attachments/assets/127a12da-d96d-4add-95b1-a97229163dfc" width="20" height="20" alt=""> | GPS device tracker, address, last-updated timestamps, refresh and update-location buttons | `request_location`, `refresh`, `flash_lights`, `honk_horn` |

All actions live under `lynkco.*` and take an optional `vin` for accounts with more than one car.

A redacted diagnostics download (device page → ⋮ → Download diagnostics) shows the model code, guide type, enabled features, failing endpoints and all raw payloads. Attach it to issues; it is what turns a model report into enabled features.

<p align="center">
  <img width="700" alt="The device page of a Lynk &amp; Co 01 in Home Assistant" src="https://github.com/user-attachments/assets/bc763f0a-7b3a-44d6-917f-8ea24ba05ce2">
</p>

## Polling

<p align="center">
  <img src="https://github.com/user-attachments/assets/c34e64d2-e575-430a-b604-e3b2714f5ac6" alt="Timeline of the full poll every 15 minutes, the fast poll while driving or while climate is active, and the targeted refresh after an action" width="880">
</p>

The full vehicle data is polled every 15 minutes. On top of that, only the endpoints relevant to what is happening are fast-polled, about every 60 seconds, instead of refetching everything:

- **While driving:** location, drive state and battery. The final location is fetched once when you reach your destination. On LynkOS 1.4.0 and newer the car only reports its location when it stops, and only if you allowed that under Settings → System → Privacy on the infotainment screen.
- **While the climate is active:** the climate state.

After an action such as locking the doors or starting the heaters, only the data that action affects is refreshed: after 3 seconds, and if the car has not processed the command yet, again after 5 and 10 seconds. Fire-and-forget actions such as flashing the lights or honking the horn trigger no refresh at all.

The intervals can be made longer with the gear icon on the integration, never shorter: the defaults are the minimum, to keep this integration as quiet as the official app on Lynk & Co's backend.

## Contributing

Feature requests and bug reports are welcome as issues, using the templates; pull requests are welcome too. [CONTRIBUTING.md](CONTRIBUTING.md) has the details, and [AGENTS.md](AGENTS.md) is for anyone pointing an AI coding agent at this repository.

## Credits

API reverse-engineered from the Lynk & Co Android app v2.55.0 and v2.63.0, and verified against v2.67.0.

Icons are [Material Design Icons](https://pictogrammers.com/library/mdi/) by Pictogrammers, Apache 2.0.

This integration is not endorsed by Lynk & Co and I have no affiliation with them whatsoever. Lynk & Co and the Lynk & Co logo are trademarks of their owner.
