"""DataUpdateCoordinator for Goldfish Grandstream."""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import GrandstreamApiClient, GrandstreamAuthError, GrandstreamConnectionError

_LOGGER = logging.getLogger(__name__)

POLL_INTERVAL = timedelta(seconds=5)
MAX_FAILURES = 3


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
        self._consecutive_failures = 0

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

        except (GrandstreamAuthError, GrandstreamConnectionError) as err:
            self._consecutive_failures += 1
            if self._consecutive_failures >= MAX_FAILURES:
                raise UpdateFailed(
                    f"Error communicating with {self.host} "
                    f"({self._consecutive_failures} consecutive failures): {err}"
                ) from err
            _LOGGER.debug(
                "Transient error from %s (failure %d/%d), keeping last state: %s",
                self.host, self._consecutive_failures, MAX_FAILURES, err,
            )
            if self.data is not None:
                return self.data
            raise UpdateFailed(str(err)) from err

        self._consecutive_failures = 0

        if not self.device_info_cache:
            try:
                self.device_info_cache = await self._client.get_device_info()
            except (GrandstreamAuthError, GrandstreamConnectionError):
                _LOGGER.warning("Could not fetch device info from %s", self.host)

        return status
