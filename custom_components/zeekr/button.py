"""Manual refresh buttons for configured Zeekr vehicles."""

from typing import Any

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import ZeekrApiError, ZeekrAuthError
from .coordinator import ZeekrRuntimeData, start_reauth
from .entity import ZeekrVehicleEntity


class ZeekrRefreshButton(ZeekrVehicleEntity, ButtonEntity):
    """Request an immediate status refresh for the parent vehicle."""

    _attr_name = "Refresh"

    def __init__(self, coordinator: Any, vin: str) -> None:
        """Bind a stateless refresh button to one vehicle's status coordinator."""
        super().__init__(coordinator, vin)
        self._attr_unique_id = f"{vin}_refresh"

    async def async_press(self) -> None:
        """Refresh this vehicle immediately and surface API failures to Home Assistant."""
        try:
            await self.coordinator.async_refresh_vehicle(self.vin)
        except ZeekrAuthError as err:
            start_reauth(self.hass)
            raise HomeAssistantError("Zeekr credentials expired") from err
        except ZeekrApiError as err:
            raise HomeAssistantError("Unable to refresh Zeekr vehicle status") from err


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create one refresh button for each supported vehicle."""
    runtime: ZeekrRuntimeData = entry.runtime_data
    async_add_entities(
        ZeekrRefreshButton(runtime.coordinator, vin) for vin in runtime.api.vehicles
    )
