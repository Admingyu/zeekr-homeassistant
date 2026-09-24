"""Vehicle sensor entities from the current Zeekr status endpoint."""

from typing import Any, List, Tuple

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfLength,
    UnitOfPressure,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entity import ZeekrVehicleEntity, numeric_value, value_at
from .coordinator import ZeekrRuntimeData


# This table mirrors the 14 sensor names, state paths, and metadata in Node-RED.
SENSOR_FIELDS: List[Tuple[SensorEntityDescription, str, bool]] = [
    (
        SensorEntityDescription(
            key="distance_to_empty",
            name="Distance to Empty",
            native_unit_of_measurement=UnitOfLength.KILOMETERS,
            device_class=SensorDeviceClass.DISTANCE,
            state_class=SensorStateClass.MEASUREMENT,
        ),
        "additionalVehicleStatus.electricVehicleStatus.distanceToEmptyOnBatteryOnly",
        True,
    ),
    (
        SensorEntityDescription(
            key="battery",
            name="Battery",
            native_unit_of_measurement=PERCENTAGE,
            device_class=SensorDeviceClass.BATTERY,
            state_class=SensorStateClass.MEASUREMENT,
        ),
        "additionalVehicleStatus.electricVehicleStatus.chargeLevel",
        True,
    ),
    (
        SensorEntityDescription(
            key="interior_temperature",
            name="Interior Temperature",
            native_unit_of_measurement=UnitOfTemperature.CELSIUS,
            device_class=SensorDeviceClass.TEMPERATURE,
            state_class=SensorStateClass.MEASUREMENT,
        ),
        "additionalVehicleStatus.climateStatus.interiorTemp",
        True,
    ),
    (
        SensorEntityDescription(key="engine_status", name="Engine Status"),
        "basicVehicleStatus.engineStatus",
        False,
    ),
    (
        SensorEntityDescription(
            key="tire_pressure_front_left",
            name="Tire Pressure Front Left",
            device_class=SensorDeviceClass.PRESSURE,
            native_unit_of_measurement=UnitOfPressure.CBAR,
        ),
        "additionalVehicleStatus.maintenanceStatus.tyreStatusDriver",
        True,
    ),
    (
        SensorEntityDescription(
            key="tire_pressure_front_right",
            name="Tire Pressure Front Right",
            device_class=SensorDeviceClass.PRESSURE,
            native_unit_of_measurement=UnitOfPressure.CBAR,
        ),
        "additionalVehicleStatus.maintenanceStatus.tyreStatusPassenger",
        True,
    ),
    (
        SensorEntityDescription(
            key="tire_pressure_rear_left",
            name="Tire Pressure Rear Left",
            device_class=SensorDeviceClass.PRESSURE,
            native_unit_of_measurement=UnitOfPressure.CBAR,
        ),
        "additionalVehicleStatus.maintenanceStatus.tyreStatusDriverRear",
        True,
    ),
    (
        SensorEntityDescription(
            key="tire_pressure_rear_right",
            name="Tire Pressure Rear Right",
            device_class=SensorDeviceClass.PRESSURE,
            native_unit_of_measurement=UnitOfPressure.CBAR,
        ),
        "additionalVehicleStatus.maintenanceStatus.tyreStatusPassengerRear",
        True,
    ),
    (
        SensorEntityDescription(
            key="distance_to_service",
            name="Distance to Service",
            native_unit_of_measurement=UnitOfLength.KILOMETERS,
            device_class=SensorDeviceClass.DISTANCE,
            state_class=SensorStateClass.MEASUREMENT,
        ),
        "additionalVehicleStatus.maintenanceStatus.distanceToService",
        True,
    ),
    (
        SensorEntityDescription(
            key="odometer",
            name="Odometer",
            native_unit_of_measurement=UnitOfLength.KILOMETERS,
        ),
        "additionalVehicleStatus.maintenanceStatus.odometer",
        True,
    ),
    (
        SensorEntityDescription(
            key="main_battery_voltage",
            name="Main Battery Voltage",
            native_unit_of_measurement=UnitOfElectricPotential.VOLT,
            device_class=SensorDeviceClass.VOLTAGE,
        ),
        "additionalVehicleStatus.maintenanceStatus.mainBatteryStatus.voltage",
        True,
    ),
    (
        SensorEntityDescription(
            key="average_power_consumption",
            name="Average Power Consumption",
            device_class=SensorDeviceClass.ENERGY,
            native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
            state_class=SensorStateClass.MEASUREMENT,
        ),
        "additionalVehicleStatus.electricVehicleStatus.averPowerConsumption",
        True,
    ),
    (
        SensorEntityDescription(
            key="central_locking_status", name="Central Locking Status"
        ),
        "additionalVehicleStatus.drivingSafetyStatus.centralLockingStatus",
        False,
    ),
    (
        SensorEntityDescription(
            key="electric_park_brake_status", name="Electric Park Brake Status"
        ),
        "additionalVehicleStatus.drivingSafetyStatus.electricParkBrakeStatus",
        False,
    ),
]


class ZeekrSensor(ZeekrVehicleEntity, SensorEntity):
    """Expose one typed value from a vehicle status response as a sensor."""

    entity_description: SensorEntityDescription

    def __init__(
        self,
        coordinator: Any,
        vin: str,
        description: SensorEntityDescription,
        path: str,
        numeric: bool,
    ) -> None:
        """Bind the sensor description and provider field path to one vehicle."""
        super().__init__(coordinator, vin)
        self.entity_description = description
        self._path = path
        self._numeric = numeric
        self._attr_unique_id = f"{vin}_{description.key}"

    @property
    def native_value(self) -> Any:
        """Return the current provider field in a Home Assistant-compatible type."""
        value = value_at(self.vehicle_data, self._path)
        if self._numeric:
            return numeric_value(value)
        if isinstance(value, bool):
            return "On" if value else "Off"
        return None if value is None else str(value)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create the configured 14 sensor entities for every supported vehicle."""
    runtime: ZeekrRuntimeData = entry.runtime_data
    async_add_entities(
        ZeekrSensor(runtime.coordinator, vin, description, path, numeric)
        for vin in runtime.api.vehicles
        for description, path, numeric in SENSOR_FIELDS
    )
