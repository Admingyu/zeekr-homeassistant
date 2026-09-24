"""Request signing helpers ported from the companion Node-RED flow."""

import base64
import hashlib
import hmac
import json
import re
from typing import Any, Dict, Mapping, Optional, Tuple
from urllib.parse import quote, urlencode


def compact_json(payload: Any) -> str:
    """Serialize a request body the same way JavaScript JSON.stringify does."""
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def gateway_signature(timestamp: str, nonce: str, secret: str) -> str:
    """Sign the gateway timestamp and nonce using the app's SHA-1 scheme."""
    combined = "".join(sorted((timestamp, nonce, secret)))
    return hashlib.sha1(combined.encode("utf-8")).hexdigest()


def _encoded_query(params: Optional[Mapping[str, Any]]) -> str:
    """Encode query parameters using the legacy API's sorted-key convention."""
    if not params:
        return ""
    pairs = [(key, params[key]) for key in sorted(params)]
    return urlencode(pairs, doseq=True)


def legacy_signature(
    method: str,
    path: str,
    params: Optional[Mapping[str, Any]],
    payload: Any,
    timestamp: str,
    nonce: str,
    secret: str,
) -> str:
    """Return the HMAC-SHA1 signature used by the older account endpoints."""
    body_md5 = base64.b64encode(
        hashlib.md5(compact_json(payload).encode("utf-8")).digest()
    ).decode("ascii") if payload is not None else base64.b64encode(
        hashlib.md5(b"").digest()
    ).decode("ascii")
    canonical = "\n".join(
        (
            "application/json;responseformat=3",
            f"x-api-signature-nonce:{nonce}",
            "x-api-signature-version:1.0",
            "",
            _encoded_query(params),
            body_md5,
            timestamp,
            method.upper(),
            path,
        )
    )
    signature = hmac.new(
        secret.encode("utf-8"), canonical.encode("utf-8"), hashlib.sha1
    ).digest()
    return base64.b64encode(signature).decode("ascii")


def _encrypt_vin(vin: str, key: str, iv: str) -> str:
    """Encrypt a VIN with AES-CBC/PKCS7 as required by the newer API."""
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

    raw = vin.encode("utf-8")
    pad_size = 16 - (len(raw) % 16)
    padded = raw + bytes((pad_size,)) * pad_size
    encryptor = Cipher(
        algorithms.AES(key.encode("utf-8")), modes.CBC(iv.encode("utf-8"))
    ).encryptor()
    encrypted = encryptor.update(padded) + encryptor.finalize()
    return base64.b64encode(encrypted).decode("ascii")


def new_signature_headers(
    method: str,
    path: str,
    params: Optional[Mapping[str, Any]],
    payload: Any,
    headers: Mapping[str, str],
    timestamp: str,
    nonce: str,
    app_secret: str,
    vin_key: str,
    vin_iv: str,
) -> Dict[str, str]:
    """Build signed headers for the current Zeekr vehicle API."""
    signed_headers = dict(headers)
    for key in list(signed_headers):
        if key.lower() == "x-vin" and signed_headers[key]:
            signed_headers[key] = _encrypt_vin(signed_headers[key], vin_key, vin_iv)

    signable = {
        "x-app-id",
        "content-type",
        "x-api-signature-nonce",
        "x-timestamp",
        "x-api-signature-version",
        "x-project-id",
        "authorization",
        "accept-language",
        "x-vin",
        "x-device-id",
        "x-platform",
    }
    names = sorted(
        (key for key in signed_headers if key.lower() in signable),
        key=lambda key: key.lower(),
    )
    header_part = "".join(
        f"{key.lower()}:{signed_headers[key]}\n"
        for key in names
        if not (key.lower() in ("x-vin", "authorization") and not signed_headers[key])
    )
    query_part = ""
    if params:
        query_values = []
        for key in sorted(params):
            value = params[key]
            if isinstance(value, str):
                value = value.replace("*", "%2A")
                value = re.sub(r"%2f", "/", value, flags=re.IGNORECASE)
                value = re.sub(r"%3f", "?", value, flags=re.IGNORECASE)
            query_values.append(f"{key}={value}")
        query_part = "&".join(query_values) + "\n"
    content_type = next(
        (
            value
            for key, value in signed_headers.items()
            if key.lower() == "content-type"
        ),
        "",
    )
    body_part = ""
    if "application/json" in content_type.lower() and payload is not None:
        body_part = base64.b64encode(
            hashlib.md5(compact_json(payload).encode("utf-8")).digest()
        ).decode("ascii") + "\n"
    canonical = f"{header_part}{query_part}{body_part}{method.upper()}\n{path}"
    signature = hmac.new(
        app_secret.encode("utf-8"), canonical.encode("utf-8"), hashlib.sha256
    ).digest()
    signed_headers["X-SIGNATURE"] = base64.b64encode(signature).decode("ascii")
    return signed_headers


def request_url(base: str, path: str, params: Optional[Mapping[str, Any]]) -> str:
    """Join an API path and encode its parameters without dropping empty values."""
    if not params:
        return f"{base}{path}"
    query = urlencode(params, doseq=True, quote_via=quote, safe="~")
    return f"{base}{path}?{query}"
