# Goldfish Grandstream

Local network integration for **Grandstream GXP series IP phones** — exposes a real-time call status sensor by polling the phone's built-in HTTP API. No syslog setup, no external dependencies.

## What's included

- **Call Status sensor** — `idle`, `ringing`, `dialing`, `in_call`, `on_hold`, updated every 5 seconds
- **Dynamic icons** — the entity icon changes with call state (outline → ringing → in-talk)
- **UI setup** — configure via Settings → Add Integration, no YAML required
- **Device card** — the phone appears as a device with model, firmware version, and a link to its web interface

## Install via HACS

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=jamesmcginnis&repository=goldfish-grandstream&category=integration)

## Compatible hardware

Developed and tested on the **GXP1625** (firmware 1.0.7.81). Other GXP16xx models are likely compatible as they share the same web API.

## Note on single sessions

The GXP phone supports one authenticated session at a time. While this integration is active, it holds that session but releases it cleanly when disabled.

---

For full documentation see the [README](https://github.com/jamesmcginnis/goldfish-grandstream#readme).
