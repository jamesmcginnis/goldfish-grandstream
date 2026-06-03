"""Device triggers for Goldfish Grandstream phones."""
from __future__ import annotations

import voluptuous as vol

from homeassistant.components.device_automation import DEVICE_TRIGGER_BASE_SCHEMA
from homeassistant.components.homeassistant.triggers import state as state_trigger
from homeassistant.const import (
    CONF_DEVICE_ID,
    CONF_DOMAIN,
    CONF_ENTITY_ID,
    CONF_PLATFORM,
    CONF_TYPE,
)
from homeassistant.core import CALLBACK_TYPE, HomeAssistant
from homeassistant.helpers import config_validation as cv, entity_registry as er
from homeassistant.helpers.trigger import TriggerActionType, TriggerInfo
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN

# Trigger type constants
TRIGGER_CALL_STARTED  = "call_started"
TRIGGER_CALL_ENDED    = "call_ended"
TRIGGER_PHONE_RINGING = "phone_ringing"
TRIGGER_CALL_ANSWERED = "call_answered"
TRIGGER_CALL_DIALING  = "call_dialing"
TRIGGER_CALL_ON_HOLD  = "call_on_hold"

TRIGGER_TYPES = {
    TRIGGER_CALL_STARTED,
    TRIGGER_CALL_ENDED,
    TRIGGER_PHONE_RINGING,
    TRIGGER_CALL_ANSWERED,
    TRIGGER_CALL_DIALING,
    TRIGGER_CALL_ON_HOLD,
}

# Maps each trigger type to (from_state, to_state).
# None means "any state".
TRIGGER_STATE_MAP: dict[str, tuple[str | None, str | None]] = {
    TRIGGER_CALL_STARTED:  (None,       "in_call"),
    TRIGGER_CALL_ENDED:    (None,       "idle"),
    TRIGGER_PHONE_RINGING: (None,       "ringing"),
    TRIGGER_CALL_ANSWERED: ("ringing",  "in_call"),
    TRIGGER_CALL_DIALING:  (None,       "dialing"),
    TRIGGER_CALL_ON_HOLD:  (None,       "on_hold"),
}

TRIGGER_SCHEMA = DEVICE_TRIGGER_BASE_SCHEMA.extend(
    {
        vol.Required(CONF_ENTITY_ID): cv.entity_id,
        vol.Required(CONF_TYPE): vol.In(TRIGGER_TYPES),
    }
)


async def async_get_triggers(
    hass: HomeAssistant, device_id: str
) -> list[dict]:
    """Return a list of triggers for a Grandstream phone device."""
    entity_registry = er.async_get(hass)
    triggers = []

    # Find the call_status sensor entity for this device
    for entry in er.async_entries_for_device(entity_registry, device_id):
        if entry.domain == "sensor" and entry.unique_id.endswith("_call_status"):
            for trigger_type in TRIGGER_TYPES:
                triggers.append(
                    {
                        CONF_PLATFORM: "device",
                        CONF_DEVICE_ID: device_id,
                        CONF_DOMAIN: DOMAIN,
                        CONF_ENTITY_ID: entry.entity_id,
                        CONF_TYPE: trigger_type,
                    }
                )

    return triggers


async def async_get_trigger_capabilities(
    hass: HomeAssistant, config: ConfigType
) -> dict:
    """Return extra capabilities (none needed — triggers are self-contained)."""
    return {}


async def async_attach_trigger(
    hass: HomeAssistant,
    config: ConfigType,
    action: TriggerActionType,
    trigger_info: TriggerInfo,
) -> CALLBACK_TYPE:
    """Attach a trigger for the given config."""
    trigger_type = config[CONF_TYPE]
    from_state, to_state = TRIGGER_STATE_MAP[trigger_type]

    state_config = {
        CONF_PLATFORM: "state",
        CONF_ENTITY_ID: config[CONF_ENTITY_ID],
        state_trigger.CONF_TO: to_state,
    }
    if from_state is not None:
        state_config[state_trigger.CONF_FROM] = from_state

    state_config = await state_trigger.async_validate_trigger_config(hass, state_config)
    return await state_trigger.async_attach_trigger(
        hass, state_config, action, trigger_info, platform_type="device"
    )
