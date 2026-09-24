"""Remote sentry-mode switches for configured Zeekr vehicles."""

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import ZeekrApiError, ZeekrAuthError
from .coordinator import ZeekrRuntimeData, start_reauth
from .entity import ZeekrVehicleEntity


class ZeekrSentrySwitch(ZeekrVehicleEntity, SwitchEntity):
    """Control the RSM sentry service and reflect the last reported usage mode."""

    _attr_name = "Sentry Mode"

    def __init__(self, runtime: ZeekrRuntimeData, vin: str) -> None:
        """Bind the RSM control to one vehicle and the shared account API client."""
        super().__init__(runtime.coordinator, vin)
        self._api = runtime.api
        self._attr_unique_id = f"{vin}_sentry_mode"

    @property
    def is_on(self) -> bool:
        """Read sentry state from the latest vehicle usage mode field."""
        value = self.vehicle_data.get("basicVehicleStatus", {}).get("usageMode")
        return str(value) == "1"

    @property
    def available(self) -> bool:
        """Require a reported usage mode before presenting the switch as available."""
        return (
            super().available
            and self.vehicle_data.get("basicVehicleStatus", {}).get("usageMode")
            is not None
        )

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Send the RSM start command and poll again to confirm the resulting state."""
        await self._set_sentry(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Send the RSM stop command and poll again to confirm the resulting state."""
        await self._set_sentry(False)

    async def _set_sentry(self, enabled: bool) -> None:
        """Execute a sentry command and surface provider failures to Home Assistant."""
        try:
            await self._api.async_set_sentry(self.vin, enabled)
            await self.coordinator.async_refresh_vehicle(self.vin)
            if self.is_on != enabled:
                raise HomeAssistantError(
                    "Vehicle status did not confirm the requested sentry mode"
                )
        except ZeekrAuthError as err:
            start_reauth(self.hass)
            raise HomeAssistantError("Zeekr credentials expired") from err
        except ZeekrApiError as err:
            raise HomeAssistantError("Unable to change Zeekr sentry mode") from err


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create one sentry-mode switch for each supported vehicle."""
    runtime: ZeekrRuntimeData = entry.runtime_data
    async_add_entities(
        ZeekrSentrySwitch(runtime, vin) for vin in runtime.api.vehicles
    )
