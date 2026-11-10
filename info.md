# Goldfish Grandstream

If you enjoy Goldfish Grandstream, you can support its development:

[![Buy Me a Coffee](https://img.buymeacoffee.com/button-api/?text=Buy%20Me%20a%20Coffee&emoji=&slug=jamesmcginnis&button_colour=FFDD00&font_colour=000000&font_family=Inter&outline_colour=000000&coffee_colour=ffffff)](https://buymeacoffee.com/jamesmcginnis)

Local network integration for **Grandstream GXP series IP phones** — exposes a real-time call status sensor by polling the phone's built-in HTTP API. No syslog setup, no external dependencies.

## What's included

- **Call Status sensor** — `idle`, `ringing`, `dialing`, `in_call`, `on_hold`, updated every 5 seconds
- **Dynamic icons** — the entity icon changes with call state (outline → ringing → in-talk)
- **UI setup** — configure via Settings → Add Integration, no YAML required
- **Device card** — the phone appears as a device with model, firmware version, and a link to its web interface

## Install via HACS

**Step 1 — Add the repository to HACS:**

[![Open your Home Assistant instance and add this repository to HACS.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=jamesmcginnis&repository=goldfish-grandstream&category=integration)

**Step 2 — After downloading and restarting, add the integration:**

[![Open your Home Assistant instance and start setting up Goldfish Grandstream.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=goldfish_grandstream)

## Compatible hardware

Developed and tested on the **GXP1625** (firmware 1.0.7.81). Other GXP16xx models are likely compatible as they share the same web API.

## Note on single sessions

The GXP phone supports one authenticated session at a time. While this integration is active, it holds that session but releases it cleanly when disabled.

---

For full documentation see the [README](https://github.com/jamesmcginnis/goldfish-grandstream#readme).
