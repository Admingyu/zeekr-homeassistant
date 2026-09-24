"""Constants shared by the Zeekr Home Assistant integration."""

from datetime import timedelta

DOMAIN = "zeekr"
NAME = "Zeekr"
PLATFORMS = ["sensor", "binary_sensor", "device_tracker", "button", "switch"]
SCAN_INTERVAL = timedelta(seconds=60)

CONF_MOBILE = "mobile"
CONF_DEVICE_ID = "device_id"
CONF_JWT_TOKEN = "jwt_token"
CONF_USER_ID = "user_id"
CONF_CLIENT_ID = "client_id"
CONF_ACCESS_TOKEN = "access_token"
CONF_REFRESH_TOKEN = "refresh_token"
CONF_VEHICLES = "vehicles"

BASE_GATEWAY = "https://api-gw-toc.zeekrlife.com"
BASE_LEGACY = "https://api.zeekrline.com"
BASE_NEW = "https://snc-tsp-api.zeekrlife.com"
BASE_STATIC = "https://snc-static.zeekrlife.com"

APP_ID = "ZEEKRCNCH001M0001"
APP_SIGNING_ID = "ZEEKRCNCH001M0000"

WS_LIST_VEHICLES = f"{DOMAIN}/list_vehicles"
WS_START_SENTINEL = f"{DOMAIN}/start_sentinel"

