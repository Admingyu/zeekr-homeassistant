"""Shared vehicle identity and response-field helpers for entity platforms."""

from typing import Any, Dict, Optional, Tuple

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import VehicleStatusCoordinator


def value_at(data: Dict[str, Any], path: str) -> Any:
    """Read a dotted response path and return None when a field is absent."""
    value: Any = data
    for part in path.split("."):
        if not isinstance(value, dict):
            return None
        value = value.get(part)
    return value


class ZeekrVehicleEntity(CoordinatorEntity[VehicleStatusCoordinator]):
    """Base entity that binds one coordinator-backed entity to one vehicle VIN."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: VehicleStatusCoordinator, vin: str) -> None:
        """Initialize the stable VIN identity used by all entity platforms."""
        super().__init__(coordinator)
        self.vin = vin
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, vin)},
            manufacturer="Zeekr",
            model="Vehicle",
            name=f"Zeekr {vin[-6:]}",
        )

    @property
    def vehicle_data(self) -> Dict[str, Any]:
        """Return the latest status object for this entity's vehicle."""
        return self.coordinator.data.get(self.vin, {})

    @property
    def available(self) -> bool:
        """Mark this vehicle's entities unavailable if its latest poll failed."""
        return super().available and bool(self.vehicle_data)


def numeric_value(value: Any) -> Optional[float]:
    """Convert provider numeric fields while rejecting invalid or missing values."""
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return int(number) if number.is_integer() else number


def boolean_value(value: Any) -> Optional[bool]:
    """Convert known boolean encodings and leave unrecognized API values unknown."""
    if value is True or value == 1 or value == "1" or value == "true":
        return True
    if value is False or value == 0 or value == "0" or value == "false":
        return False
    return None

