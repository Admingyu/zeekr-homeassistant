"""Set up the Zeekr integration, services, WebSocket handlers, and entities."""

from pathlib import Path
from typing import Any, Dict

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
    card_path = Path(__file__).parent / "www" / "zeekr-sentinel-card.js"
    await hass.http.async_register_static_paths(
        [StaticPathConfig("/api/zeekr/zeekr-sentinel-card.js", str(card_path), False)]
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
