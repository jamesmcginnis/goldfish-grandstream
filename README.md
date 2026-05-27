# Goldfish Grandstream

*** WORK IN PROGRESS ***


[![HACS Custom](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
[![License](https://img.shields.io/github/license/jamesmcginnis/goldfish-grandstream.svg?style=flat-square)](LICENSE)

A Home Assistant custom integration for **Grandstream GXP series IP phones** (developed and tested on the GXP1625).

Exposes a **Call Status sensor** that updates in near real-time by polling the phone's built-in HTTP API — no syslog configuration, no external dependencies.

---

## Install via HACS

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=jamesmcginnis&repository=goldfish-grandstream&category=integration)

1. Click the button above — Home Assistant opens and asks you to confirm adding the repo
2. In HACS find **Goldfish Grandstream** and click **Download**
3. Restart Home Assistant
4. Go to **Settings → Devices & Services → Add Integration** → search **Goldfish Grandstream**

### Manual installation

1. Download `goldfish-grandstream.zip` from the [latest release](https://github.com/jamesmcginnis/goldfish-grandstream/releases/latest)
2. Extract and copy the `custom_components/goldfish_grandstream` folder into `/config/custom_components/`
3. Restart Home Assistant

---

## Sensor

| Entity | States | Icon |
|---|---|---|
| `sensor.grandstream_gxp1625_call_status` | `idle` · `ringing` · `in_call` · `unknown` | Changes with state |

---

## Requirements

- Home Assistant 2023.1 or later
- Your Grandstream phone must be on the **same local network** as Home Assistant
- The phone's **web interface must be enabled** (it is by default)
- You need the phone's **admin credentials** (default username: `admin`)

---

## Setup

1. Go to **Settings → Devices & Services → Add Integration**
2. Search for **Goldfish Grandstream**
3. Enter:
   - **IP Address** — your phone's local IP (e.g. `192.168.0.46`). Tip: set a static IP or DHCP reservation so this never changes.
   - **Username** — `admin` (default)
   - **Password** — your phone's admin password

The integration will appear as a device with a Call Status sensor.

---

## Automations

Example — send a notification when the phone starts ringing:

```yaml
automation:
  - alias: "Notify when phone rings"
    trigger:
      - platform: state
        entity_id: sensor.grandstream_gxp1625_call_status
        to: "ringing"
    action:
      - service: notify.mobile_app
        data:
          message: "Phone is ringing!"
```

---

## Polling interval

The phone is polled every **5 seconds** by default. This matches what the phone's own web UI does and has no noticeable impact on the phone's performance.

---

## Tested on

| Model | Firmware |
|---|---|
| GXP1625 | 1.0.7.81 |

Other GXP16xx models are likely compatible as they share the same web API.

---

## Limitations

- **Caller ID** is not yet exposed — the phone's API does not return caller information in the status endpoint
- **Outgoing vs incoming** call direction is not distinguished (both show as `in_call`)
- The phone's HTTP API is undocumented by Grandstream; this integration was built by analysing packet captures
