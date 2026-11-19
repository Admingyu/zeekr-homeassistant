"""Stateless action buttons for configured Zeekr vehicles."""

from typing import Any, Awaitable, Callable, List

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import ZeekrApi, ZeekrApiError, ZeekrAuthError
from .coordinator import ZeekrRuntimeData, start_reauth
from .entity import ZeekrVehicleEntity

RemoteAction = Callable[[ZeekrApi, str], Awaitable[None]]


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


class ZeekrRemoteButton(ZeekrVehicleEntity, ButtonEntity):
    """Fire one stateless remote command and refresh status afterwards."""

    def __init__(
        self,
        runtime: ZeekrRuntimeData,
        vin: str,
        name: str,
        unique_key: str,
        action: RemoteAction,
    ) -> None:
        """Bind a named remote command to one vehicle and the account API client."""
        super().__init__(runtime.coordinator, vin)
        self._api = runtime.api
        self._action = action
        self._attr_name = name
        self._attr_unique_id = f"{vin}_{unique_key}"

    async def async_press(self) -> None:
        """Send the command, then poll so dependent entities update sooner."""
        try:
            await self._action(self._api, self.vin)
        except ZeekrAuthError as err:
            start_reauth(self.hass)
            raise HomeAssistantError("Zeekr credentials expired") from err
        except ZeekrApiError as err:
            raise HomeAssistantError("Zeekr remote-control command failed") from err
        try:
            await self.coordinator.async_refresh_vehicle(self.vin)
        except ZeekrApiError:
            # The command already reached the vehicle; a stale poll is not a failure.
            pass


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create the refresh and remote-action buttons for each supported vehicle."""
    runtime: ZeekrRuntimeData = entry.runtime_data
    actions = (
        ("Find Vehicle", "find_vehicle", lambda api, vin: api.async_find_vehicle(vin)),
        ("Lock Doors", "lock_doors", lambda api, vin: api.async_set_doors(vin, True)),
        (
            "Unlock Doors",
            "unlock_doors",
            lambda api, vin: api.async_set_doors(vin, False),
        ),
    )
    entities: List[Any] = [
        ZeekrRefreshButton(runtime.coordinator, vin) for vin in runtime.api.vehicles
    ]
    entities.extend(
        ZeekrRemoteButton(runtime, vin, name, key, action)
        for vin in runtime.api.vehicles
        for name, key, action in actions
    )
    async_add_entities(entities)
