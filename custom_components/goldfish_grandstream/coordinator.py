"""DataUpdateCoordinator for Goldfish Grandstream."""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import GrandstreamApiClient, GrandstreamConnectionError

_LOGGER = logging.getLogger(__name__)

POLL_INTERVAL = timedelta(seconds=5)


class GrandstreamCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Polls the Grandstream phone API and distributes data to entities."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: GrandstreamApiClient,
        host: str,
    ) -> None:
        self._client = client
        self.host = host
        self.device_info_cache: dict[str, Any] = {}

        super().__init__(
            hass,
            _LOGGER,
            name=f"Grandstream {host}",
            update_interval=POLL_INTERVAL,
        )

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch latest data from the phone."""
        try:
            status = await self._client.get_phone_status()
        except GrandstreamConnectionError as err:
            raise UpdateFailed(f"Error communicating with {self.host}: {err}") from err

        # Fetch device info once and cache it
        if not self.device_info_cache:
            try:
                self.device_info_cache = await self._client.get_device_info()
            except GrandstreamConnectionError:
                _LOGGER.warning("Could not fetch device info from %s", self.host)

        return status
