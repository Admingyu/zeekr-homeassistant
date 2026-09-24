"""Asynchronous API client for the Zeekr endpoints used by this integration."""

import asyncio
import time
import uuid
from typing import Any, Awaitable, Callable, Dict, List, Mapping, Optional

import aiohttp

from .const import (
    APP_ID,
    APP_SIGNING_ID,
    BASE_GATEWAY,
    BASE_LEGACY,
    BASE_NEW,
    BASE_STATIC,
    CONF_ACCESS_TOKEN,
    CONF_CLIENT_ID,
    CONF_DEVICE_ID,
    CONF_JWT_TOKEN,
    CONF_MOBILE,
    CONF_REFRESH_TOKEN,
    CONF_USER_ID,
    CONF_VEHICLES,
)
from .signing import (
    gateway_signature,
    legacy_signature,
    new_signature_headers,
    request_url,
)

class ZeekrApiError(Exception):
    """Base error for failed requests or business responses from Zeekr."""


class ZeekrAuthError(ZeekrApiError):
    """Raised when the API rejects an authenticated request."""


class ZeekrConnectionError(ZeekrApiError):
    """Raised when the Zeekr endpoint cannot return a valid response."""


class ZeekrApi:
    """Own request signing, account tokens, vehicle calls, and token rotation."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        data: Mapping[str, Any],
        token_updated: Optional[Callable[[Dict[str, Any]], Awaitable[None]]] = None,
    ) -> None:
        """Initialize the API client from a config entry or an in-progress login."""
        self._session = session
        self.device_id = str(data[CONF_DEVICE_ID])
        self.mobile = str(data.get(CONF_MOBILE, ""))
        self.jwt_token = str(data.get(CONF_JWT_TOKEN, ""))
        self.user_id = str(data.get(CONF_USER_ID, ""))
        self.client_id = str(data.get(CONF_CLIENT_ID, ""))
        self.access_token = str(data.get(CONF_ACCESS_TOKEN, ""))
        self.refresh_token = str(data.get(CONF_REFRESH_TOKEN, ""))
        self.legacy_access_token = str(data.get("legacy_access_token", ""))
        self.legacy_refresh_token = str(data.get("legacy_refresh_token", ""))
        self.vehicles = list(data.get(CONF_VEHICLES, []))
        self._token_updated = token_updated

    def export_data(self) -> Dict[str, Any]:
        """Return the current account state for secure config-entry persistence."""
        return {
            CONF_MOBILE: self.mobile,
            CONF_DEVICE_ID: self.device_id,
            CONF_JWT_TOKEN: self.jwt_token,
            CONF_USER_ID: self.user_id,
            CONF_CLIENT_ID: self.client_id,
            CONF_ACCESS_TOKEN: self.access_token,
            CONF_REFRESH_TOKEN: self.refresh_token,
            "legacy_access_token": self.legacy_access_token,
            "legacy_refresh_token": self.legacy_refresh_token,
            CONF_VEHICLES: list(self.vehicles),
        }

    async def async_send_sms(self, mobile: str) -> None:
        """Send a login code to the configured mobile number."""
        now_ms = str(int(time.time() * 1000))
        response = await self._gateway_request(
            "GET",
            "/zeekrlife-app-user/v1/user/pub/sms/authCode",
            params={
                "mobile": mobile,
                "x_ca_time": now_ms,
                "regionCode": "+86",
            },
        )
        self._expect_code(response, "000000")

    async def async_authenticate(self, mobile: str, sms_code: str) -> Dict[str, Any]:
        """Complete SMS login, both account sessions, and supported-car discovery."""
        self.mobile = mobile
        response = await self._gateway_request(
            "POST",
            "/zeekrlife-app-user/v1/user/pub/login/mobile",
            payload={
                "mobile": mobile,
                "deviceId": self.device_id,
                "smsCode": sms_code,
                "channel": 2,
                "x_ca_time": str(int(time.time() * 1000)),
                "deviceName": "iPhone13",
                "skipSmsCode": "0",
                "regionCode": "+86",
                "ip": "192.168.1.1",
            },
        )
        self._expect_code(response, "000000")
        self.jwt_token = self._data(response).get("jwtToken", "")
        if not self.jwt_token:
            raise ZeekrApiError("SMS login response did not contain jwtToken")

        code_response = await self._gateway_request(
            "GET", "/zeekrlife-mp-auth2/v1/auth/accessCodeList", params={"envType": 3}
        )
        self._expect_code(code_response, "000000")
        auth_code = self._data(code_response).get("YIKAT_NEW")
        if not auth_code:
            raise ZeekrApiError("Account response did not contain YIKAT_NEW")

        legacy_response = await self._legacy_request(
            "POST",
            "/auth/account/session/secure",
            params={"identity_type": "zeekr"},
            payload={"authCode": auth_code},
            expected_code="1000",
        )
        self._save_legacy_session(self._data(legacy_response))
        if not self.user_id:
            raise ZeekrApiError("Legacy account response did not contain userId")

        old_vins = await self._async_get_legacy_vehicle_vins()
        new_response = await self._new_request(
            "POST",
            "/ms-user-auth/v1.0/auth/login",
            payload={
                "loginDeviceType": 1,
                "identityType": 5,
                "loginSystem": "ios",
                "loginDeviceId": self.device_id,
                "token": self.jwt_token,
                "loginPhoneBrand": "Apple",
            },
            headers={"Authorization": self.jwt_token},
        )
        self._expect_code(new_response, "000000")
        self._save_new_session(self._data(new_response))

        vehicle_response = await self._new_request(
            "GET",
            "/ms-app-bff/api/v3.0/veh/vehicle-list",
            params={"needSharedCar": "true"},
            headers={"Authorization": self.jwt_token},
        )
        self._expect_code(vehicle_response, "000000")
        vehicle_rows = self._data_value(vehicle_response)
        if not isinstance(vehicle_rows, list):
            raise ZeekrApiError("Vehicle-list response data was not a list")
        if any(not isinstance(row, dict) for row in vehicle_rows):
            raise ZeekrApiError("Vehicle-list response contained an invalid vehicle")
        all_vins = [str(row["vin"]) for row in vehicle_rows if row.get("vin")]
        self.vehicles = [vin for vin in all_vins if vin not in set(old_vins)]
        if not self.vehicles:
            raise ZeekrApiError("No supported new-model vehicles were found")
        return self.export_data()

    async def async_get_vehicle_status(self, vin: str) -> Dict[str, Any]:
        """Fetch latest status, refreshing the account token once if rejected."""
        response = await self._new_call(
            "GET",
            "/ms-vehicle-status/api/v1.0/vehicle/status/latest",
            params={"latest": "false", "target": "new"},
            headers={"X-VIN": vin, "X-APP-ID": APP_ID},
        )
        self._expect_code(response, "000000")
        data = self._data(response)
        if not isinstance(data, dict):
            raise ZeekrApiError("Vehicle status response data was not an object")
        return data

    async def async_set_sentry(self, vin: str, enabled: bool) -> None:
        """Start or stop the RSM sentry service for one vehicle."""
        response = await self._new_call(
            "POST",
            "/ms-remote-control/v1.0/remoteControl/control",
            payload={
                "command": "start" if enabled else "stop",
                "serviceId": "RSM",
                "setting": {"serviceParameters": [{"key": "rsm", "value": "6"}]},
            },
            headers={"X-VIN": vin, "X-APP-ID": APP_ID},
        )
        self._expect_code(response, "000000")

    async def async_get_monthly_statistics(
        self, vin: str, year_month: str, account_id: str
    ) -> Any:
        """Return one vehicle's monthly statistics for the supplied account month."""
        response = await self._new_call(
            "POST",
            "/journey-statistics-service/api/v1/h5/getMonthlyStatisticsInfo",
            base=BASE_STATIC,
            payload={"vin": vin, "accountId": account_id, "yearMonth": year_month},
            headers={"X-VIN": vin, "X-APP-ID": APP_ID},
        )
        self._expect_code(response, "000000")
        return self._data_value(response)

    async def async_get_app_messages(self, vin: str) -> Any:
        """Return the upgrade-message list for one vehicle."""
        response = await self._new_call(
            "POST",
            "/zeekrlife-mp-mps/v4/user/msg/upgrade/boxList",
            payload={},
            headers={"X-VIN": vin, "X-APP-ID": APP_ID},
        )
        self._expect_code(response, "000000")
        return self._data_value(response)

    async def async_get_sentinel_session(self, vin: str) -> Dict[str, Any]:
        """Open a sentinel room and return its short-lived ByteRTC join parameters."""
        launch = await self._new_call(
            "GET",
            "/sentinel-monitoring-service/api/v1/alarm/live/app/launchLive",
            params={"alarmVin": vin},
            headers={"X-VIN": vin, "X-APP-ID": APP_ID},
        )
        self._expect_code(launch, "000000")
        room = self._data(launch)
        room_id = room.get("roomId")
        app_id = room.get("appId")
        if not room_id or not app_id:
            raise ZeekrApiError("launchLive response did not contain appId and roomId")

        token_response = await self._new_call(
            "POST",
            "/sentinel-monitoring-service/api/v1/alarm/live/app/getToken",
            payload={"roomId": room_id, "userId": self.user_id},
            headers={"X-VIN": vin, "X-APP-ID": APP_ID},
        )
        self._expect_code(token_response, "000000")
        token_data = self._data(token_response)
        access_token = token_data.get("accessToken")
        join_user_id = token_data.get("joinUserId")
        if not access_token or not join_user_id:
            raise ZeekrApiError(
                "getToken response did not contain accessToken and joinUserId"
            )

        return {
            "appId": app_id,
            "roomId": room_id,
            "userId": join_user_id,
            "accessToken": access_token,
            "liveDuration": room.get("liveDuration"),
            "expireAt": token_data.get("expireAt"),
        }

    async def _async_get_legacy_vehicle_vins(self) -> List[str]:
        """Load legacy vehicle VINs so the integration excludes unsupported models."""
        try:
            response = await self._legacy_request(
                "GET",
                "/device-platform/user/vehicle/secure",
                params={"id": self.user_id, "needSharedCar": 1},
                expected_code="1000",
            )
        except ZeekrAuthError:
            await self._async_refresh_legacy_token()
            response = await self._legacy_request(
                "GET",
                "/device-platform/user/vehicle/secure",
                params={"id": self.user_id, "needSharedCar": 1},
                expected_code="1000",
            )
        rows = self._data(response).get("list", [])
        if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
            raise ZeekrApiError(
                "Legacy vehicle response contained an invalid vehicle list"
            )
        return [str(row["vin"]) for row in rows if row.get("vin")]

    async def _async_refresh_legacy_token(self) -> None:
        """Rotate the old session tokens once after the legacy API rejects them."""
        if not self.legacy_refresh_token:
            raise ZeekrAuthError("Legacy session expired and has no refresh token")
        response = await self._legacy_request(
            "PUT",
            "/auth/account/session/secure",
            payload={"refreshToken": self.legacy_refresh_token},
            expected_code="1000",
        )
        self._save_legacy_session(self._data(response))
        await self._async_persist_tokens()

    async def _new_call(self, *args: Any, **kwargs: Any) -> Dict[str, Any]:
        """Retry one new-API operation after a single access-token refresh."""
        try:
            return await self._new_request(*args, **kwargs)
        except ZeekrAuthError:
            await self._async_refresh_new_token()
            return await self._new_request(*args, **kwargs)

    async def _async_refresh_new_token(self) -> None:
        """Rotate the new account tokens using the stored refresh token."""
        if not self.refresh_token or not self.access_token:
            raise ZeekrAuthError("New account session expired and cannot be refreshed")
        response = await self._new_request(
            "POST",
            "/ms-user-auth/v1.0/auth/refreshToken",
            payload={
                "loginDeviceType": 1,
                "loginDeviceId": self.device_id,
                "loginPhoneBrand": "Apple",
                "loginSystem": "ios",
                "refreshToken": self.refresh_token,
                "accessToken": self.access_token,
            },
            headers={"Authorization": self.jwt_token},
        )
        try:
            self._expect_code(response, "000000")
            self._save_new_session(self._data(response))
        except ZeekrApiError as err:
            raise ZeekrAuthError("New account token refresh was rejected") from err
        await self._async_persist_tokens()

    async def _async_persist_tokens(self) -> None:
        """Persist rotated credentials without logging any token material."""
        if self._token_updated is not None:
            await self._token_updated(self.export_data())

    async def _gateway_request(
        self,
        method: str,
        path: str,
        params: Optional[Mapping[str, Any]] = None,
        payload: Any = None,
    ) -> Dict[str, Any]:
        """Send a signed request to the SMS and authorization-code gateway."""
        now_ms = str(int(time.time() * 1000))
        nonce = str(int(time.time() * 1000) % 100000000)
        headers = {
            "User-Agent": (
                f"ZeekrLife/4.0.2 (iPhone; iOS 17.4.1; Scale/3.00){self.device_id}"
            ),
            "request-original": "zeekr-app",
            "Accept-Language": "zh-Hans-CN;q=1, en-CN;q=0.9",
            "Content-Type": "application/json",
            "x_ca_secret": _gateway_secret(),
            "Accept": "*/*",
            "riskToken": _risk_token(),
            "Version": "2",
            "WorkspaceId": "prod",
            "x_ca_key": "APP-SIGN-SECRET-KEY",
            "app_type": "IOS",
            "app_version": "4.0.2",
            "phone_model": "iPhone13",
            "phone_version": "17.4.1",
            "x_gray_code": "gray74",
            "x_ca_timestamp": now_ms,
            "x_ca_nonce": nonce,
            "x_ca_sign": gateway_signature(now_ms, nonce, _gateway_secret()),
            "app_code": "toc_ios_zeekrapp",
            "Authorization": self.jwt_token,
            "device_id": self.device_id,
        }
        if not self.jwt_token:
            headers.pop("Authorization")
        return await self._send(BASE_GATEWAY, method, path, params, payload, headers)

    async def _legacy_request(
        self,
        method: str,
        path: str,
        params: Optional[Mapping[str, Any]] = None,
        payload: Any = None,
        expected_code: str = "000000",
    ) -> Dict[str, Any]:
        """Send a signed request to the older Zeekr account API."""
        now_ms = str(int(time.time() * 1000))
        nonce = str(uuid.uuid4()).upper()
        headers = {
            "content-type": "application/json",
            "x-api-signature-version": "1.0",
            "x-app-id": "ZEEKRAPP",
            "user-agent": "ZeekrLife/4.0.2 (iPhone; iOS 17.4.1; Scale/3.00)",
            "x-device-model": "iPhone",
            "x-device-manufacture": "Apple",
            "x-agent-type": "iOS",
            "x-device-type": "mobile",
            "platform": "NON-CMA",
            "x-env-type": "production",
            "accept-language": "zh-Hans-CN;q=1, en-CN;q=0.9",
            "x-agent-version": "17.4.1",
            "accept": "application/json;responseformat=3",
            "x-device-brand": "Apple",
            "x-operator-code": "ZEEKR",
            "x-device-identifier": self.device_id,
            "authorization": self.legacy_access_token,
            "x-client-id": self.client_id,
            "x-timestamp": now_ms,
            "x-api-signature-nonce": nonce,
        }
        headers["x-signature"] = legacy_signature(
            method, path, params, payload, now_ms, nonce, _legacy_secret()
        )
        response = await self._send(BASE_LEGACY, method, path, params, payload, headers)
        self._expect_code(response, expected_code)
        return response

    async def _new_request(
        self,
        method: str,
        path: str,
        base: str = BASE_NEW,
        params: Optional[Mapping[str, Any]] = None,
        payload: Any = None,
        headers: Optional[Mapping[str, str]] = None,
    ) -> Dict[str, Any]:
        """Send a signed request to a current vehicle, statistics, or auth endpoint."""
        timestamp = str(int(time.time() * 1000))
        nonce = str(uuid.uuid4()).upper()
        request_headers = {
            "X-APP-ID": APP_SIGNING_ID,
            "X-TIMESTAMP": timestamp,
            "X-API-SIGNATURE-VERSION": "2.0",
            "X-SIGNATURE": "",
            "Accept-Language": "zh-CN",
            "Content-Type": "application/json;charset=UTF-8",
            "X-PROJECT-ID": "ZEEKR",
            "X-P": "iOS",
            "X-DEVICE-ID": self.device_id,
            "X-APP-OS-VERSION": "4.9.9",
            "X-PLATFORM": "APP",
            "X-API-SIGNATURE-NONCE": nonce,
            "User-Agent": "ZeekrLife/2025061706 CFNetwork/3826.500.131 Darwin/24.5.0",
            "Authorization": self.access_token,
        }
        request_headers.update(headers or {})
        signed_headers = new_signature_headers(
            method,
            path,
            params,
            payload,
            request_headers,
            timestamp,
            nonce,
            _new_secret(),
            _vin_key(),
            _vin_iv(),
        )
        return await self._send(base, method, path, params, payload, signed_headers)

    async def _send(
        self,
        base: str,
        method: str,
        path: str,
        params: Optional[Mapping[str, Any]],
        payload: Any,
        headers: Mapping[str, str],
    ) -> Dict[str, Any]:
        """Send HTTP requests and convert transport errors without credentials."""
        url = request_url(base, path, params)
        try:
            async with self._session.request(
                method, url, json=payload, headers=dict(headers), timeout=25
            ) as response:
                if response.status in (401, 403):
                    raise ZeekrAuthError(
                        f"Zeekr API rejected authentication (HTTP {response.status})"
                    )
                if response.status >= 400:
                    raise ZeekrConnectionError(
                        f"Zeekr API returned HTTP {response.status}"
                    )
                result = await response.json(content_type=None)
        except ZeekrApiError:
            raise
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as err:
            raise ZeekrConnectionError("Unable to communicate with Zeekr API") from err
        if not isinstance(result, dict):
            raise ZeekrConnectionError("Zeekr API returned an invalid response")
        return result

    def _save_legacy_session(self, data: Mapping[str, Any]) -> None:
        """Update legacy account fields from a successful session response."""
        access_token = data.get("accessToken")
        refresh_token = data.get("refreshToken")
        if not access_token or not refresh_token:
            raise ZeekrApiError("Legacy session response did not contain both tokens")
        self.legacy_access_token = str(access_token)
        self.legacy_refresh_token = str(refresh_token)
        if data.get("userId"):
            self.user_id = str(data["userId"])
        if data.get("clientId"):
            self.client_id = str(data["clientId"])

    def _save_new_session(self, data: Mapping[str, Any]) -> None:
        """Update the current account token pair from a successful response."""
        access_token = data.get("accessToken")
        refresh_token = data.get("refreshToken")
        if not access_token or not refresh_token:
            raise ZeekrApiError(
                "Account response did not contain both access and refresh tokens"
            )
        self.access_token = str(access_token)
        self.refresh_token = str(refresh_token)

    @staticmethod
    def _data_value(response: Mapping[str, Any]) -> Any:
        """Read response data while preserving list payloads such as vehicle lists."""
        data = response.get("data")
        if data is None:
            raise ZeekrApiError("Zeekr API response did not contain data")
        return data

    @staticmethod
    def _data(response: Mapping[str, Any]) -> Dict[str, Any]:
        """Read an object-valued response data field and reject other shapes."""
        data = ZeekrApi._data_value(response)
        if not isinstance(data, dict):
            raise ZeekrApiError("Zeekr API response data was not an object")
        return data

    @staticmethod
    def _expect_code(response: Mapping[str, Any], expected: str) -> None:
        """Require the provider's documented flow-specific success code."""
        code = str(response.get("code", ""))
        if code != expected:
            message = str(response.get("msg", "request failed"))[:160]
            raise ZeekrApiError(
                f"Zeekr API returned code {code or 'missing'}: {message}"
            )


def _gateway_secret() -> str:
    """Return the app gateway signing key copied from the Node-RED formatter."""
    return "MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQCz09z6e9WOcNq+nUMX8Vq1Xe2EmJxuR3XbtureDCS90dfkok"


def _risk_token() -> str:
    """Return the app risk header value required by the SMS gateway."""
    return "G4y5f5YrG1BEGxRBBEKF73higM/lOd6e"


def _legacy_secret() -> str:
    """Return the old account API signing key copied from the Node-RED formatter."""
    return "e83a60805fa54de9bdfcb0f2d6bca757"


def _new_secret() -> str:
    """Return the current vehicle API signing key copied from Node-RED."""
    return "890efe3207af95348b95f66b2ee7da04"


def _vin_key() -> str:
    """Return the AES key used by the current vehicle API to encode VIN headers."""
    return "a01a6db985a2f5d4"


def _vin_iv() -> str:
    """Return the AES initialization vector used for VIN headers."""
    return "ed446b8b8845013d"
