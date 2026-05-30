"""Goldfish Grandstream integration for Home Assistant."""
from __future__ import annotations

import logging

import aiohttp

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_create_clientsession

from .api import GrandstreamApiClient, GrandstreamAuthError, GrandstreamConnectionError
from .const import DOMAIN
from .coordinator import GrandstreamCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Goldfish Grandstream from a config entry."""
    host = entry.data[CONF_HOST]
    username = entry.data[CONF_USERNAME]
    password = entry.data[CONF_PASSWORD]

    session = async_create_clientsession(
        hass,
        cookie_jar=aiohttp.CookieJar(unsafe=True),
    )
    client = GrandstreamApiClient(host, username, password, session)

    try:
        await client.authenticate()
    except GrandstreamAuthError:
        _LOGGER.error("Invalid credentials for Grandstream phone at %s", host)
        return False
    except GrandstreamConnectionError:
        _LOGGER.error("Cannot connect to Grandstream phone at %s", host)
        return False

    coordinator = GrandstreamCoordinator(hass, client, host)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry and release the phone session."""
    coordinator: GrandstreamCoordinator = hass.data[DOMAIN].get(entry.entry_id)

    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)
        if coordinator is not None:
            await coordinator._client.logout()

    return unload_ok
