"""UI login and reauthentication flow for a Zeekr account."""

import uuid
from typing import Any, Dict, Optional

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import SOURCE_REAUTH
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import ZeekrApi, ZeekrApiError, ZeekrConnectionError
from .const import CONF_DEVICE_ID, CONF_MOBILE, DOMAIN


class ZeekrConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Manage SMS login, account uniqueness, and credential recovery."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize transient login state that is never written to disk."""
        self._mobile: Optional[str] = None
        self._device_id: Optional[str] = None

    async def async_step_user(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Ask for a mobile number, send its code, and advance to verification."""
        errors: Dict[str, str] = {}
        if user_input is not None:
            self._mobile = user_input[CONF_MOBILE].strip()
            self._device_id = str(uuid.uuid4())
            api = ZeekrApi(
                async_get_clientsession(self.hass),
                {CONF_DEVICE_ID: self._device_id, CONF_MOBILE: self._mobile},
            )
            try:
                await api.async_send_sms(self._mobile)
            except ZeekrApiError:
                errors["base"] = "cannot_connect"
            else:
                return await self.async_step_verify()
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required(CONF_MOBILE): str}),
            errors=errors,
        )

    async def async_step_verify(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Verify the SMS code and create or update the account config entry."""
        errors: Dict[str, str] = {}
        if user_input is not None and self._mobile and self._device_id:
            api = ZeekrApi(
                async_get_clientsession(self.hass),
                {CONF_DEVICE_ID: self._device_id, CONF_MOBILE: self._mobile},
            )
            try:
                data = await api.async_authenticate(
                    self._mobile, user_input["sms_code"].strip()
                )
            except ZeekrConnectionError:
                errors["base"] = "cannot_connect"
            except ZeekrApiError:
                errors["base"] = "invalid_auth"
            else:
                await self.async_set_unique_id(data["user_id"])
                if self.source == SOURCE_REAUTH:
                    self._abort_if_unique_id_mismatch()
                    return self.async_update_reload_and_abort(
                        self._get_reauth_entry(), data_updates=data
                    )
                self._abort_if_unique_id_configured()
                suffix = data["user_id"][-6:]
                return self.async_create_entry(title=f"Zeekr {suffix}", data=data)
        return self.async_show_form(
            step_id="verify",
            data_schema=vol.Schema({vol.Required("sms_code"): str}),
            errors=errors,
        )

    async def async_step_reauth(self, entry_data: Dict[str, Any]) -> Dict[str, Any]:
        """Start a user-confirmed SMS reauthentication flow for an existing account."""
        self._mobile = entry_data[CONF_MOBILE]
        self._device_id = entry_data[CONF_DEVICE_ID]
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Send a new code after the user opens the reauthentication prompt."""
        errors: Dict[str, str] = {}
        if user_input is not None and self._mobile and self._device_id:
            api = ZeekrApi(
                async_get_clientsession(self.hass),
                {CONF_DEVICE_ID: self._device_id, CONF_MOBILE: self._mobile},
            )
            try:
                await api.async_send_sms(self._mobile)
            except ZeekrApiError:
                errors["base"] = "cannot_connect"
            else:
                return await self.async_step_verify()
        return self.async_show_form(step_id="reauth_confirm", errors=errors)
