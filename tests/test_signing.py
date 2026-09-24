"""Golden tests for deterministic request-signing cases."""

import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parents[1] / "custom_components" / "zeekr"))

from signing import (
    compact_json,
    gateway_signature,
    legacy_signature,
    new_signature_headers,
    request_url,
)


class SigningTests(unittest.TestCase):
    """Keep the three app signing formats stable with synthetic credentials."""

    def test_gateway_signature(self) -> None:
        """Sign gateway timestamp and nonce in lexical order."""
        self.assertEqual(
            gateway_signature("1700000000000", "42", "secret"),
            "672d02798ef29593644181f5e546433d6baab59e",
        )

    def test_legacy_signature(self) -> None:
        """Sign a deterministic legacy login request including query and body hashes."""
        self.assertEqual(
            legacy_signature(
                "POST",
                "/auth/account/session/secure",
                {"identity_type": "zeekr"},
                {"authCode": "sample"},
                "1700000000000",
                "NONCE",
                "secret",
            ),
            "gAY9YfD0GdJJqZFI4ANngo0bACQ=",
        )

    def test_new_signature_and_url(self) -> None:
        """Sign sorted headers, query, compact JSON, and verify URL encoding."""
        headers = {
            "X-APP-ID": "APP",
            "Content-Type": "application/json;charset=UTF-8",
            "X-API-SIGNATURE-NONCE": "NONCE",
            "X-TIMESTAMP": "1700000000000",
            "X-API-SIGNATURE-VERSION": "2.0",
            "X-PROJECT-ID": "ZEEKR",
            "Authorization": "TOKEN",
            "Accept-Language": "zh-CN",
            "X-DEVICE-ID": "DEVICE",
            "X-PLATFORM": "APP",
        }
        signed = new_signature_headers(
            "POST",
            "/example",
            {"a": "x y", "b": "z"},
            {"ok": True},
            headers,
            "1700000000000",
            "NONCE",
            "secret",
            "0123456789abcdef",
            "abcdef0123456789",
        )
        self.assertEqual(signed["X-SIGNATURE"], "qyK9HNLZb+SCMsCmmV2oMspvmtPtoWVggSBG7ja1xoE=")
        self.assertNotIn("X-VIN", signed)
        self.assertEqual(compact_json({"ok": True}), '{"ok":true}')
        self.assertEqual(
            request_url("https://example", "/x", {"a": "x y", "region": "%2B86"}),
            "https://example/x?a=x%20y&region=%252B86",
        )
        self.assertEqual(
            request_url("https://example", "/x", {"region": "+86"}),
            "https://example/x?region=%2B86",
        )


if __name__ == "__main__":
    unittest.main()
