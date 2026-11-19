"""Request bodies for the vehicle remote-control endpoint.

Every builder reproduces a body observed from the Zeekr app, including its
inconsistent value types (some flags are the string "true", the steering-wheel
flag is a JSON boolean). Keep the shapes verbatim so unknown-model behaviour
does not change.
"""

from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

# Seat key used by the app's driver-seat heating command.
SEAT_HEATING_KEY = "SH.11"

# Sentry service parameter observed in the app's RSM command.
SENTRY_LEVEL = "6"

FIND_VEHICLE_SERVICE = "RHL"
CLIMATE_SERVICE = "ZAF"
SEAT_HEATING_SERVICE = "ZAF"
STEERING_WHEEL_SERVICE = "ZAF"
LOCK_SERVICE = "RDL"
UNLOCK_SERVICE = "RDU"
SENTRY_SERVICE = "RSM"


def _body(
    command: str, service_id: str, parameters: Iterable[Tuple[str, Any]]
) -> Dict[str, Any]:
    """Wrap ordered key/value pairs in the endpoint's request envelope."""
    return {
        "command": command,
        "serviceId": service_id,
        "setting": {
            "serviceParameters": [
                {"key": key, "value": value} for key, value in parameters
            ]
        },
    }


def _temperature_text(temperature: float) -> str:
    """Format a target temperature the way the app sends it ("22.0")."""
    return f"{float(temperature):.1f}"


def _duration_text(duration: int) -> str:
    """Format a duration in whole minutes as the app sends it ("15")."""
    return str(int(duration))


def find_vehicle_payload() -> Dict[str, Any]:
    """Flash the horn and lights so the car can be located."""
    return _body("", FIND_VEHICLE_SERVICE, [("rhl", "horn-light-flash")])


def climate_payload(
    enabled: bool, temperature: Optional[float] = None, duration: Optional[int] = None
) -> Dict[str, Any]:
    """Start or stop air conditioning, optionally with target and run time."""
    parameters: List[Tuple[str, Any]] = [("AC", "true" if enabled else "false")]
    if enabled and temperature is not None:
        parameters.append(("AC.temp", _temperature_text(temperature)))
    if enabled and duration is not None:
        parameters.append(("AC.duration", _duration_text(duration)))
    return _body("start", CLIMATE_SERVICE, parameters)


def seat_heating_payload(
    enabled: bool,
    level: Optional[int] = None,
    duration: Optional[int] = None,
    key: str = SEAT_HEATING_KEY,
) -> Dict[str, Any]:
    """Start or stop one seat's heating with an optional level and run time."""
    parameters: List[Tuple[str, Any]] = [
        (key, "true" if enabled else "false"),
    ]
    if enabled and level is not None:
        parameters.append((f"{key}.level", str(int(level))))
    if enabled and duration is not None:
        parameters.append((f"{key}.duration", _duration_text(duration)))
    return _body("start", SEAT_HEATING_SERVICE, parameters)


def steering_wheel_heating_payload(
    enabled: bool, level: Optional[int] = None, duration: Optional[int] = None
) -> Dict[str, Any]:
    """Start or stop steering-wheel heating, using booleans as the app does."""
    parameters: List[Tuple[str, Any]] = [("SW", bool(enabled))]
    if enabled and level is not None:
        parameters.append(("SW.level", str(int(level))))
    if enabled and duration is not None:
        # The app sends this one as a JSON number, unlike the AC duration.
        parameters.append(("SW.duration", int(duration)))
    return _body("", STEERING_WHEEL_SERVICE, parameters)


def door_payload(locked: bool) -> Dict[str, Any]:
    """Lock every door, or unlock every door."""
    return _body(
        "start",
        LOCK_SERVICE if locked else UNLOCK_SERVICE,
        [("door", "all")],
    )


def sentry_payload(enabled: bool) -> Dict[str, Any]:
    """Start or stop the RSM sentry service."""
    return _body(
        "start" if enabled else "stop",
        SENTRY_SERVICE,
        [("rsm", SENTRY_LEVEL)],
    )


def custom_payload(
    command: str, service_id: str, parameters: Optional[Mapping[str, Any]] = None
) -> Dict[str, Any]:
    """Build an unmodelled command so new app actions need no code change."""
    return _body(command, service_id, (parameters or {}).items())
