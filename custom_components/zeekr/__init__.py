"""Set up the Zeekr integration, services, WebSocket handlers, and entities."""

from pathlib import Path
from typing import Any, Awaitable, Callable, Dict

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, SupportsResponse, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import ZeekrApi, ZeekrApiError, ZeekrAuthError
from .const import (
    DOMAIN,
    PLATFORMS,
    WS_LIST_VEHICLES,
    WS_START_SENTINEL,
)
from .coordinator import (
    VehicleStatusCoordinator,
    ZeekrRuntimeData,
    get_runtime,
    start_reauth,
)


async def async_setup(hass: HomeAssistant, config: Dict[str, Any]) -> bool:
    """Register static frontend assets and authenticated dashboard commands."""
    hass.data.setdefault(DOMAIN, {})
    www_path = Path(__file__).parent / "www"
    await hass.http.async_register_static_paths(
        [
            StaticPathConfig(
                "/api/zeekr/zeekr-sentinel-card.js",
                str(www_path / "zeekr-sentinel-card.js"),
                False,
            ),
            # Vendored so the dashboard never needs to reach a public CDN. The
            # versioned filename makes the one-month cache safe across upgrades.
            StaticPathConfig(
                "/api/zeekr/volcengine-rtc-4.69.2.js",
                str(www_path / "volcengine-rtc-4.69.2.js"),
                True,
            ),
        ]
    )
    websocket_api.async_register_command(hass, websocket_list_vehicles)
    websocket_api.async_register_command(hass, websocket_start_sentinel)
    _async_register_services(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Create the API runtime, perform the first poll, and set up entity platforms."""

    async def persist_tokens(data: Dict[str, Any]) -> None:
        """Save rotated credentials in the existing config entry."""
        hass.config_entries.async_update_entry(entry, data=data)

    api = ZeekrApi(async_get_clientsession(hass), entry.data, persist_tokens)
    coordinator = VehicleStatusCoordinator(hass, api)
    try:
        await coordinator.async_config_entry_first_refresh()
    except ConfigEntryAuthFailed:
        raise
    runtime = ZeekrRuntimeData(api=api, coordinator=coordinator)
    entry.runtime_data = runtime
    hass.data[DOMAIN][entry.entry_id] = runtime
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload platforms and remove the runtime from the integration registry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unloaded


@websocket_api.websocket_command({vol.Required("type"): WS_LIST_VEHICLES})
@callback
def websocket_list_vehicles(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: Dict[str, Any]
) -> None:
    """Return VIN/name pairs so the authenticated Lovelace card can offer a selector."""
    try:
        runtime = get_runtime(hass)
        vehicles = [
            {"vin": vin, "name": f"Zeekr {vin[-6:]}"}
            for vin in runtime.api.vehicles
        ]
        connection.send_result(msg["id"], {"vehicles": vehicles})
    except RuntimeError as err:
        connection.send_error(msg["id"], "not_loaded", str(err))


@websocket_api.websocket_command(
    {
        vol.Required("type"): WS_START_SENTINEL,
        vol.Required("vin"): cv.string,
    }
)
@websocket_api.async_response
async def websocket_start_sentinel(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: Dict[str, Any]
) -> None:
    """Return one short-lived RTC session to the authenticated dashboard client."""
    try:
        runtime = get_runtime(hass)
        vin = msg["vin"]
        if vin not in runtime.api.vehicles:
            raise HomeAssistantError("Vehicle is not part of this Zeekr account")
        session = await runtime.api.async_get_sentinel_session(vin)
        connection.send_result(msg["id"], session)
    except ZeekrAuthError:
        connection.send_error(msg["id"], "auth_failed", "Zeekr credentials expired")
        start_reauth(hass)
    except (ZeekrApiError, RuntimeError, HomeAssistantError) as err:
        connection.send_error(msg["id"], "unknown_error", str(err)[:160])


def _async_register_services(hass: HomeAssistant) -> None:
    """Register response actions for monthly statistics and vehicle messages."""
    month_validator = vol.All(cv.string, vol.Match(r"^\d{4}-(0[1-9]|1[0-2])$"))
    temperature_validator = vol.All(vol.Coerce(float), vol.Range(min=16, max=30))
    ac_duration_validator = vol.All(vol.Coerce(int), vol.Range(min=1, max=30))
    short_duration_validator = vol.All(vol.Coerce(int), vol.Range(min=1, max=15))
    level_validator = vol.All(vol.Coerce(int), vol.Range(min=1, max=3))

    def runtime_for(vin: str) -> ZeekrRuntimeData:
        """Return the active account runtime after checking vehicle membership."""
        runtime = get_runtime(hass)
        if vin not in runtime.api.vehicles:
            raise HomeAssistantError("Vehicle is not part of this Zeekr account")
        return runtime

    async def async_remote_action(
        vin: str, action: Callable[[ZeekrApi], Awaitable[None]]
    ) -> None:
        """Run one remote command, then refresh that vehicle's status best-effort."""
        runtime = runtime_for(vin)
        try:
            await action(runtime.api)
        except ZeekrAuthError as err:
            start_reauth(hass)
            raise HomeAssistantError("Zeekr credentials expired") from err
        except ZeekrApiError as err:
            raise HomeAssistantError("Zeekr remote-control command failed") from err
        try:
            await runtime.coordinator.async_refresh_vehicle(vin)
        except ZeekrApiError:
            # The command already reached the vehicle; a stale poll is not a failure.
            pass

    async def get_monthly_statistics(call: Any) -> Dict[str, Any]:
        """Fetch one month of statistics and return the provider data to the caller."""
        runtime = get_runtime(hass)
        vin = call.data["vin"]
        if vin not in runtime.api.vehicles:
            raise HomeAssistantError("Vehicle is not part of this Zeekr account")
        try:
            data = await runtime.api.async_get_monthly_statistics(
                vin, call.data["year_month"], call.data["account_id"]
            )
        except ZeekrAuthError as err:
            start_reauth(hass)
            raise HomeAssistantError("Zeekr credentials expired") from err
        except ZeekrApiError as err:
            raise HomeAssistantError("Monthly statistics request failed") from err
        return {"data": data}

    async def get_app_messages(call: Any) -> Dict[str, Any]:
        """Fetch app upgrade messages for one supported vehicle."""
        runtime = get_runtime(hass)
        vin = call.data["vin"]
        if vin not in runtime.api.vehicles:
            raise HomeAssistantError("Vehicle is not part of this Zeekr account")
        try:
            data = await runtime.api.async_get_app_messages(vin)
        except ZeekrAuthError as err:
            start_reauth(hass)
            raise HomeAssistantError("Zeekr credentials expired") from err
        except ZeekrApiError as err:
            raise HomeAssistantError("App message request failed") from err
        return {"data": data}

    hass.services.async_register(
        DOMAIN,
        "get_monthly_statistics",
        get_monthly_statistics,
        schema=vol.Schema(
            {
                vol.Required("vin"): cv.string,
                vol.Required("year_month"): month_validator,
                vol.Required("account_id"): cv.string,
            }
        ),
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN,
        "get_app_messages",
        get_app_messages,
        schema=vol.Schema({vol.Required("vin"): cv.string}),
        supports_response=SupportsResponse.ONLY,
    )

    async def find_vehicle(call: Any) -> None:
        """Flash the horn and lights so the vehicle can be located."""
        vin = call.data["vin"]
        await async_remote_action(vin, lambda api: api.async_find_vehicle(vin))

    async def lock_doors(call: Any) -> None:
        """Lock every door on the vehicle."""
        vin = call.data["vin"]
        await async_remote_action(vin, lambda api: api.async_set_doors(vin, True))

    async def unlock_doors(call: Any) -> None:
        """Unlock every door on the vehicle."""
        vin = call.data["vin"]
        await async_remote_action(vin, lambda api: api.async_set_doors(vin, False))

    async def set_climate(call: Any) -> None:
        """Start air conditioning with a target and run time, or stop it."""
        vin = call.data["vin"]
        await async_remote_action(
            vin,
            lambda api: api.async_set_climate(
                vin,
                call.data["enabled"],
                call.data["temperature"],
                call.data["duration"],
            ),
        )

    async def set_seat_heating(call: Any) -> None:
        """Start seat heating with a level and run time, or stop it."""
        vin = call.data["vin"]
        await async_remote_action(
            vin,
            lambda api: api.async_set_seat_heating(
                vin,
                call.data["enabled"],
                call.data["level"],
                call.data["duration"],
            ),
        )

    async def set_steering_wheel_heating(call: Any) -> None:
        """Start steering-wheel heating with a level and run time, or stop it."""
        vin = call.data["vin"]
        await async_remote_action(
            vin,
            lambda api: api.async_set_steering_wheel_heating(
                vin,
                call.data["enabled"],
                call.data["level"],
                call.data["duration"],
            ),
        )

    async def remote_control(call: Any) -> None:
        """Send an app command that this integration does not model yet."""
        vin = call.data["vin"]
        parameters = call.data.get("parameters") or {}
        await async_remote_action(
            vin,
            lambda api: api.async_send_raw_control(
                vin, call.data["service_id"], call.data["command"], parameters
            ),
        )

    vehicle_only = vol.Schema({vol.Required("vin"): cv.string})
    for name, handler in (
        ("find_vehicle", find_vehicle),
        ("lock_doors", lock_doors),
        ("unlock_doors", unlock_doors),
    ):
        hass.services.async_register(DOMAIN, name, handler, schema=vehicle_only)
    hass.services.async_register(
        DOMAIN,
        "set_climate",
        set_climate,
        schema=vol.Schema(
            {
                vol.Required("vin"): cv.string,
                vol.Required("enabled"): cv.boolean,
                vol.Optional("temperature", default=22.0): temperature_validator,
                vol.Optional("duration", default=15): ac_duration_validator,
            }
        ),
    )
    for name, handler in (
        ("set_seat_heating", set_seat_heating),
        ("set_steering_wheel_heating", set_steering_wheel_heating),
    ):
        hass.services.async_register(
            DOMAIN,
            name,
            handler,
            schema=vol.Schema(
                {
                    vol.Required("vin"): cv.string,
                    vol.Required("enabled"): cv.boolean,
                    vol.Optional("level", default=3): level_validator,
                    vol.Optional("duration", default=15): short_duration_validator,
                }
            ),
        )
    hass.services.async_register(
        DOMAIN,
        "remote_control",
        remote_control,
        schema=vol.Schema(
            {
                vol.Required("vin"): cv.string,
                vol.Required("service_id"): cv.string,
                vol.Optional("command", default="start"): cv.string,
                vol.Optional("parameters"): dict,
            }
        ),
    )

