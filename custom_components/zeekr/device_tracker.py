"""GPS device tracker entities for supported Zeekr vehicles."""

from typing import Any, Dict, Optional

from homeassistant.components.device_tracker import SourceType, TrackerEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import ZeekrRuntimeData
from .entity import ZeekrVehicleEntity, numeric_value


class ZeekrTracker(ZeekrVehicleEntity, TrackerEntity):
    """Expose a vehicle's latest GPS point with selected status as attributes."""

    _attr_source_type = SourceType.GPS
    _attr_name = "Location"
    _attr_location_accuracy = 10

    def __init__(self, coordinator: Any, vin: str) -> None:
        """Bind the device tracker to one VIN and its coordinator data."""
        super().__init__(coordinator, vin)
        self._attr_unique_id = f"{vin}_location"

    @property
    def latitude(self) -> Optional[float]:
        """Return the latest vehicle latitude when the response contains one."""
        position = self.vehicle_data.get("basicVehicleStatus", {}).get("position", {})
        return numeric_value(position.get("latitude"))

    @property
    def longitude(self) -> Optional[float]:
        """Return the latest vehicle longitude when the response contains one."""
        position = self.vehicle_data.get("basicVehicleStatus", {}).get("position", {})
        return numeric_value(position.get("longitude"))

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Expose battery, speed, and odometer values on the location entity."""
        basic = self.vehicle_data.get("basicVehicleStatus", {})
        electric = (
            self.vehicle_data.get("additionalVehicleStatus", {})
            .get("electricVehicleStatus", {})
        )
        maintenance = self.vehicle_data.get("maintenanceStatus", {})
        return {
            "battery": electric.get("chargeLevel"),
            "speed": basic.get("speed"),
            "odometer": maintenance.get("odometer"),
        }


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create one GPS tracker for each configured supported vehicle."""
    runtime: ZeekrRuntimeData = entry.runtime_data
    async_add_entities(
        ZeekrTracker(runtime.coordinator, vin) for vin in runtime.api.vehicles
    )
