"""Binary sensor entities for charging and high-voltage battery optimization."""

from typing import Any, List, Tuple

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import ZeekrRuntimeData
from .entity import ZeekrVehicleEntity, boolean_value, value_at


# This table mirrors the two binary sensor fields configured in Node-RED.
BINARY_SENSOR_FIELDS: List[Tuple[BinarySensorEntityDescription, str]] = [
    (
        BinarySensorEntityDescription(
            key="charging",
            name="Charging",
            device_class=BinarySensorDeviceClass.BATTERY_CHARGING,
        ),
        "additionalVehicleStatus.electricVehicleStatus.isCharging",
    ),
    (
        BinarySensorEntityDescription(
            key="hv_battery_optimization",
            name="HV Battery Optimization",
            device_class=BinarySensorDeviceClass.PROBLEM,
        ),
        "additionalVehicleStatus.electricVehicleStatus.hvBatteryOptimizeFlag",
    ),
]


class ZeekrBinarySensor(ZeekrVehicleEntity, BinarySensorEntity):
    """Represent a supported vehicle's boolean status as a binary sensor."""

    entity_description: BinarySensorEntityDescription

    def __init__(
        self,
        coordinator: Any,
        vin: str,
        description: BinarySensorEntityDescription,
        path: str,
    ) -> None:
        """Bind the binary sensor description and provider field to one vehicle."""
        super().__init__(coordinator, vin)
        self.entity_description = description
        self._path = path
        self._attr_unique_id = f"{vin}_{description.key}"

    @property
    def is_on(self) -> bool:
        """Return the parsed provider flag; availability tracks missing values."""
        return boolean_value(value_at(self.vehicle_data, self._path)) is True

    @property
    def available(self) -> bool:
        """Keep a missing or unknown provider flag from appearing as an off state."""
        value = boolean_value(value_at(self.vehicle_data, self._path))
        return super().available and value is not None


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create two binary sensor entities for each supported vehicle."""
    runtime: ZeekrRuntimeData = entry.runtime_data
    async_add_entities(
        ZeekrBinarySensor(runtime.coordinator, vin, description, path)
        for vin in runtime.api.vehicles
        for description, path in BINARY_SENSOR_FIELDS
    )
