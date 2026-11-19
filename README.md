# Zeekr for Home Assistant

[English](README.md) · [简体中文](README.zh-Hans.md)

[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2024.7%2B-41BDF5?logo=homeassistant&logoColor=white)](#requirements)
[![Integration type](https://img.shields.io/badge/type-custom%20integration-blue)](#installation)
[![IoT class](https://img.shields.io/badge/IoT%20class-cloud%20polling-informational)](#how-it-works)

An unofficial Home Assistant custom integration for **Zeekr (极氪)** vehicles. It signs in with a Zeekr account, discovers the supported vehicles on that account, and exposes battery, range, tyres, location, sentry mode, and remote controls as Home Assistant entities and actions.

The integration was ported from a Node-RED flow and replaces it: the entity mapping is listed below so existing dashboards can be migrated.

> [!WARNING]
> This is not an official integration. It talks to unpublished Zeekr mobile-app endpoints that can change at any time, so it can break without notice. Remote commands operate a real vehicle — only send them when it is safe to do so.

## Contents

- [Features](#features)
- [Requirements](#requirements)
- [Installation](#installation)
- [Configuration](#configuration)
- [Entities](#entities)
- [Actions](#actions)
- [Sentry live video card](#sentry-live-video-card)
- [Troubleshooting](#troubleshooting)
- [How it works](#how-it-works)
- [Limitations and disclaimer](#limitations-and-disclaimer)
- [Migrating from Node-RED](#migrating-from-node-red)
- [Development](#development)
- [License](#license)
- [Acknowledgements](#acknowledgements)

## Features

- **Automatic vehicle discovery** — one Home Assistant device per supported new-model VIN on the account, created at sign-in.
- **Status polling every 60 seconds** — battery, remaining range, temperatures, tyre pressures, odometer, service interval, 12 V battery, power consumption, lock and park-brake state, plus a GPS tracker with battery, speed, and odometer attributes.
- **Refresh on demand** — a per-vehicle Refresh button instead of waiting for the next poll.
- **Remote controls** — horn and lights, lock/unlock, air conditioning with target temperature and run time, driver-seat heating, and steering-wheel heating, plus a raw escape hatch for commands that are not modelled yet.
- **Sentry mode switch** — starts and stops the RSM sentry service and confirms the resulting state from the next status poll.
- **Sentry live video** — a Lovelace card that joins the vehicle's sentry RTC room. The RTC Web SDK is bundled with the integration, so playback needs no public CDN.
- **Statistics and messages** — response actions for monthly journey statistics and in-app vehicle messages.
- **Token handling** — access tokens rotate automatically and are written back to the config entry; when they expire, Home Assistant asks you to reauthenticate with a new SMS code.

## Requirements

Updated upstream
The card contains its own vehicle selector and **开始观看** button; no entity ID is needed. After joining the vehicle room, the card provides front, rear, left, and right camera buttons plus on-demand remote talk. Remote talk requests browser microphone permission when it starts and releases the microphone when it stops or leaves the room. Use Home Assistant through HTTPS or localhost so the browser can grant microphone access. If Home Assistant reports that the custom element does not exist, the resource was not loaded—check its URL and type, reload resources, and reopen the dashboard editor.

The card asks the integration for a short-lived room session, then uses the fixed `@volcengine/rtc@4.69.2` Web SDK to join and render the vehicle's main stream. Camera buttons send the verified `cmd_action_change_source` RTC room message, while remote talk publishes microphone audio only while the talk control is active. It reconnects when the room duration or RTC token expires. The browser loads that pinned SDK from unpkg when playback starts, so the dashboard browser must be able to reach `unpkg.com`. The browser receives only the short-lived RTC session token; Zeekr account tokens and request-signing keys stay in the integration backend.

LAN HTTP addresses (for example, `http://192.168.x.x:8123`) are not secure contexts: Chromium does not expose `navigator.mediaDevices` there, so remote talk cannot start. Serve Home Assistant over HTTPS with a certificate trusted by the browser, then allow microphone access for that HTTPS origin. Merely changing the URL to HTTPS does not configure TLS on the server. The localhost exception applies to the computer running the browser, not to the Home Assistant server's LAN IP.
=======
| Requirement | Detail |
| --- | --- |
| Home Assistant | 2024.7 or newer (uses `StaticPathConfig` for the card and SDK) |
| Account | A Zeekr account registered with a +86 mobile number that works in the Zeekr mobile app |
| Vehicle | A new-model vehicle listed on that account; old-model VINs are excluded |
| Network | Home Assistant must reach `api-gw-toc.zeekrlife.com`, `api.zeekrline.com`, `snc-tsp-api.zeekrlife.com`, and `snc-static.zeekrlife.com` |

Only one Zeekr account can be configured per Home Assistant instance (`single_config_entry`). Shared vehicles are included, and the shared list is re-read on sign-in.

## Installation

### HACS (custom repository)

This integration is not in the default HACS store.

1. Open HACS → **Integrations** → the **⋮** menu → **Custom repositories**.
2. Add `https://github.com/Admingyu/zeekr-homeassistant` with category **Integration**.
3. Install **Zeekr**, then restart Home Assistant.
4. Go to **Settings → Devices & services → Add integration** and pick **Zeekr**.

### Manual

Copy `custom_components/zeekr` into your Home Assistant configuration directory so that it becomes `custom_components/zeekr`, restart Home Assistant, then add **Zeekr** from **Settings → Devices & services → Add integration**.

## Configuration

Setup is a single sign-in flow:

1. Enter the mobile number used by the Zeekr app. The integration sends an SMS code.
2. Enter the code. The integration signs in, loads the vehicle list, and creates one device named `Zeekr <last six VIN characters>` per supported vehicle.

Home Assistant generates the entity ID prefix from that device name; the stable part of each entity is its unique ID suffix listed below. The first status update runs during setup.

Session tokens are stored in the config entry. The app's fixed signing values stay in the integration code. When Home Assistant reports that the integration needs reauthentication, run the SMS flow again — that also re-reads the vehicle list, so reauthenticate after the account's shared-vehicle list changes.


## Entities

All entities are grouped under one device per VIN.

| Entity | Platform | Unique ID suffix | Node-RED name |
| --- | --- | --- | --- |
| Battery | sensor | `battery` | Battery |
| Distance to Empty | sensor | `distance_to_empty` | DistanceToEmpty |
| Interior Temperature | sensor | `interior_temperature` | InteriorTemp |
| Engine Status | sensor | `engine_status` | Engine |
| Tire Pressure Front Left | sensor | `tire_pressure_front_left` | TyreStatusDriver |
| Tire Pressure Front Right | sensor | `tire_pressure_front_right` | TyreStatusPassenger |
| Tire Pressure Rear Left | sensor | `tire_pressure_rear_left` | TyreStatusDriverRear |
| Tire Pressure Rear Right | sensor | `tire_pressure_rear_right` | TyreStatusPassengerRear |
| Distance to Service | sensor | `distance_to_service` | ServiceLD |
| Odometer | sensor | `odometer` | TravalTotal |
| Main Battery Voltage | sensor | `main_battery_voltage` | mainBattVoltage |
| Average Power Consumption | sensor | `average_power_consumption` | averPowerConsumption |
| Central Locking Status | sensor | `central_locking_status` | CentralLockingStatus |
| Electric Park Brake Status | sensor | `electric_park_brake_status` | electricParkBrakeStatus |
| Charging | binary_sensor | `charging` | ChargingState |
| HV Battery Optimization | binary_sensor | `hv_battery_optimization` | hvBatteryOptimizeFlag |
| Location | device_tracker | `location` | Location |
| Refresh | button | `refresh` | Refresh |
| Find Vehicle | button | `find_vehicle` | — |
| Lock Doors | button | `lock_doors` | — |
| Unlock Doors | button | `unlock_doors` | — |
| Sentry Mode | switch | `sentry_mode` | SentryModeSwitch |

Old-model status entities are not included. The legacy account endpoint is still used during setup to identify old-model VINs and exclude them from the supported list.

An entity that is missing from a particular model's response is reported as unavailable instead of showing a stale or invented value. Refresh, remote commands, and sentry changes poll only the affected vehicle.

## Actions

### Vehicle status

| Action | Fields | Returns |
| --- | --- | --- |
| `zeekr.get_monthly_statistics` | `vin`, `year_month` (`YYYY-MM`), `account_id` | The provider's monthly journey statistics |
| `zeekr.get_app_messages` | `vin` | The provider's in-app upgrade message list |

Both return a service response, so call them from a response-capable action UI or an automation/script with `response_variable`:

```yaml
action: zeekr.get_monthly_statistics
data:
  vin: YOUR_VIN
  year_month: "2025-10"
  account_id: YOUR_ACCOUNT_ID
response_variable: statistics
```

`account_id` is the Zeekr account identifier stored as `user_id` in the integration's config entry.

### Remote control

Every remote command posts to the same app endpoint (`/ms-remote-control/v1.0/remoteControl/control`) with a different body. Commands without parameters are also available as the buttons listed above:

| Action | Fields | Effect |
| --- | --- | --- |
| `zeekr.find_vehicle` | `vin` | Flash the horn and lights |
| `zeekr.lock_doors` | `vin` | Lock all doors |
| `zeekr.unlock_doors` | `vin` | Unlock all doors |
| `zeekr.set_climate` | `vin`, `enabled`, `temperature` (16–30 °C, default 22), `duration` (1–30 min, default 15) | Start air conditioning, or stop it |
| `zeekr.set_seat_heating` | `vin`, `enabled`, `level` (1–3, default 3), `duration` (1–15 min, default 15) | Driver-seat heating |
| `zeekr.set_steering_wheel_heating` | same as seat heating | Steering-wheel heating |
| `zeekr.remote_control` | `vin`, `service_id`, `command` (default `start`), `parameters` | Any other app command |

Start air conditioning at 22 °C for 15 minutes:

```yaml
action: zeekr.set_climate
data:
  vin: YOUR_VIN
  enabled: true
  temperature: 22
  duration: 15
```

Stop it:

```yaml
action: zeekr.set_climate
data:
  vin: YOUR_VIN
  enabled: false
```

Switch on steering-wheel heating at level 3 for 15 minutes:

```yaml
action: zeekr.set_steering_wheel_heating
data:
  vin: YOUR_VIN
  enabled: true
  level: 3
  duration: 15
```

Send a service ID that is not modelled yet:

```yaml
action: zeekr.remote_control
data:
  vin: YOUR_VIN
  service_id: ZAF
  command: start
  parameters:
    AC: "true"
    AC.temp: "22.0"
    AC.duration: "15"
```

These commands report no confirmable state: the status endpoint does not expose a settled climate, heating, or door state. They are therefore stateless buttons and actions rather than switch or climate entities, and the integration polls the vehicle once after each command so dependent entities refresh sooner. Only sentry mode reads back a state, because `basicVehicleStatus.usageMode` reports it.

Request bodies match the app exactly, including its inconsistent value types — the air-conditioning and seat flags are the strings `"true"`/`"false"`, the steering-wheel flag is a JSON boolean, and the horn/light and steering-wheel commands use an empty `command` while the others send `start`. The bodies live in `custom_components/zeekr/remote_control.py` as pure builders, and `tests/test_remote_control.py` pins them.

Only the driver seat (`SH.11`) is modelled; other seat positions would use their own app keys through `zeekr.remote_control`.

## Sentry live video card

Installing the integration serves the card file, but Home Assistant does not add it to a dashboard automatically. Register the JavaScript resource first:

1. Open **Settings → Dashboards**, open the top-right **⋮** menu, and choose **Resources**.
2. Select **Add resource** and enter:

   | URL | Type |
   | --- | --- |
   | `/api/zeekr/zeekr-sentinel-card.js` | JavaScript module |

3. Save, then use **⋮ → Reload resources** (or refresh the browser page).
4. Open the dashboard, choose **Edit dashboard → Add card**, and search for **Zeekr 哨兵视频**.
5. If it is not listed, choose **Manual** and paste:

```yaml
type: custom:zeekr-sentinel-card
```

The card contains its own vehicle selector and **开始观看** button; no entity ID is needed. If Home Assistant reports that the custom element does not exist, the resource was not loaded — check its URL and type, reload resources, and reopen the dashboard editor.

The card asks the integration for a short-lived room session, then uses the pinned `@volcengine/rtc@4.69.2` Web SDK to join and render the vehicle's main stream. It reconnects when the room duration or RTC token expires. The SDK is bundled with the integration and served from `/api/zeekr/volcengine-rtc-4.69.2.js`, so playback works without access to any public CDN; the bundled copy ships its BSD-3-Clause license at `custom_components/zeekr/www/volcengine-rtc-LICENSE`. If that file cannot load, the card falls back to the same pinned version on `unpkg.com`.

The browser receives only the short-lived RTC session token. Zeekr account tokens and request-signing keys stay in the integration backend.

## Troubleshooting

**The integration rejects the mobile number or no code arrives.** Only +86 accounts are supported. Confirm the number works in the Zeekr app, then retry — the provider rate-limits repeated code requests.

**Sign-in succeeds but no vehicles appear.** The account has no new-model VINs. Old-model vehicles are deliberately excluded, and the provider rejects the setup with `No supported new-model vehicles were found` in the log.

**Home Assistant asks to reauthenticate the integration.** The stored session expired and could not be refreshed. Run the SMS flow again; this also re-reads the shared-vehicle list.

**Some entities stay unavailable.** That model's status response does not contain the field. Availability tracks the response rather than caching an old value.

**The sentry switch flips back after a click.** The vehicle answered `000000` but did not report the requested usage mode in the follow-up poll. Retry once the car has network coverage.

**The card reports that the custom element does not exist.** Its JavaScript resource is not loaded — see [Sentry live video card](#sentry-live-video-card).

**Playback fails while the card status shows an RTC error.** The card cannot reach the Zeekr RTC service or the engine cannot join the room. Check that the sentry service is active for that vehicle in the Zeekr app.

## How it works

```
config_flow.py ── SMS sign-in ──┐
                                ├─ api.py ── three signed HTTP clients
signing.py ─────────────────────┘   (gateway, legacy account, current vehicle API)
                                        │
                                coordinator.py ── 60 s poll of every VIN
                                        │
        sensor · binary_sensor · device_tracker · button · switch
```

- **Three auth layers.** SMS login returns a JWT. The gateway issues an auth code for that JWT, which the legacy account API exchanges for a session (providing `user_id` and the old-model VIN list); the same JWT also signs in to the current vehicle API. Each layer has its own signing scheme in `signing.py`: SHA-1 over sorted values for the gateway, HMAC-SHA1 with an MD5 body hash for the legacy API, and HMAC-SHA256 over sorted headers, query, and body for the current API — with the VIN encrypted into the `X-VIN` header.
- **One coordinator per account.** A single `DataUpdateCoordinator` polls every supported VIN on the 60-second interval and shares the result with all platforms; single-vehicle actions refresh only that VIN.
- **No polling feedback loop.** Entities read the coordinator's data only; nothing writes state locally, so an entity never claims a value the vehicle did not report.

## Limitations and disclaimer

- Unofficial and unaffiliated with Zeekr. All API endpoints and signing values are unpublished and may change without notice.
- The account, vehicle, and RTC calls depend on Zeekr cloud services. Outages, model-specific response differences, and regional restrictions are outside this integration's control.
- Remote commands act on a real vehicle. Verify the VIN before automating lock, unlock, climate, or heating commands, and never run them unattended in a location where an unexpected action is dangerous.
- No confirmable state exists for climate, heating, or doors, so automations cannot wait for those commands to be confirmed.
- The project is verified against one account and vehicle. SMS login, current response fields, remote commands, and dashboard playback all require live credentials to test.

## Migrating from Node-RED

The [Entities](#entities) table maps every Node-RED entity name to the new platform and unique ID suffix. Existing entity IDs and automations are not rewritten automatically — after the integration creates the devices, update your automations to the new entity IDs.

The Node-RED `Unlock` button only triggered a refresh; this integration implements real lock and unlock commands.

## Development

The tests use the standard library's `unittest` and import the integration modules directly, so they need no Home Assistant installation:

```bash
python -m unittest discover -s tests -v
```

| Path | Purpose |
| --- | --- |
| `custom_components/zeekr/api.py` | HTTP clients, token rotation, vehicle and sentry calls |
| `custom_components/zeekr/signing.py` | The three request-signing schemes |
| `custom_components/zeekr/remote_control.py` | Remote-command request bodies |
| `custom_components/zeekr/coordinator.py` | Account runtime and the shared status poll |
| `custom_components/zeekr/www/` | Lovelace card and the bundled RTC SDK |
| `tests/` | Signing and request-body golden tests |

When adding a remote command, put the body builder in `remote_control.py`, add a golden test for it, then expose it through `api.py` and, if it needs parameters, an action.

## License

No license file is included in this repository yet, which means all rights are reserved by default. Open an issue if you need a license for redistribution or derivative work.

The bundled RTC SDK (`custom_components/zeekr/www/volcengine-rtc-4.69.2.js`) is © The VolcEngineRTC project authors and licensed under BSD-3-Clause; its license text is included next to the file.

## Acknowledgements

- The original behaviour and entity set come from the author's Node-RED flow, which this integration replaces.
- Vehicle live video uses the [Volcengine RTC](https://www.volcengine.com/product/rtc) Web SDK.
