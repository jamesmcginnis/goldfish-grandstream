"""Sensor platform for Goldfish Grandstream."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import GrandstreamCoordinator

_LOGGER = logging.getLogger(__name__)

CALL_STATUS_DESCRIPTION = SensorEntityDescription(
    key="call_status",
    name="Call Status",
    icon="mdi:phone",
)

# Icons that change based on state
STATE_ICONS = {
    "idle": "mdi:phone-outline",
    "ringing": "mdi:phone-ring",
    "in_call": "mdi:phone-in-talk",
    "unknown": "mdi:phone-off",
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Grandstream sensors from a config entry."""
    coordinator: GrandstreamCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([GrandstreamCallStatusSensor(coordinator, entry)])


class GrandstreamCallStatusSensor(
    CoordinatorEntity[GrandstreamCoordinator], SensorEntity
):
    """Sensor reporting the current call status of the Grandstream phone."""

    entity_description = CALL_STATUS_DESCRIPTION
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: GrandstreamCoordinator,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator)
        host = entry.data[CONF_HOST]
        self._attr_unique_id = f"{host}_call_status"

    @property
    def native_value(self) -> str:
        """Return the current call status."""
        if self.coordinator.data is None:
            return "unknown"
        return self.coordinator.data.get("call_status", "unknown")

    @property
    def icon(self) -> str:
        """Return an icon that reflects the current call state."""
        return STATE_ICONS.get(self.native_value, "mdi:phone-off")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes for debugging."""
        if not self.coordinator.data:
            return {}
        return {
            "raw_status": self.coordinator.data.get("raw_status"),
            "host": self.coordinator.host,
        }

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info to group this entity under a device in HA."""
        device_info = self.coordinator.device_info_cache
        return DeviceInfo(
            identifiers={(DOMAIN, self.coordinator.host)},
            name=f"Grandstream {device_info.get('model', 'GXP')} ({self.coordinator.host})",
            manufacturer=device_info.get("vendor", "Grandstream"),
            model=device_info.get("model", "GXP"),
            sw_version=device_info.get("firmware"),
            configuration_url=f"http://{self.coordinator.host}",
        )
