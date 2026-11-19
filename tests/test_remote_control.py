"""Golden tests for remote-control bodies copied from the Zeekr app."""

import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parents[1] / "custom_components" / "zeekr"))

from remote_control import (
    climate_payload,
    custom_payload,
    door_payload,
    find_vehicle_payload,
    seat_heating_payload,
    sentry_payload,
    steering_wheel_heating_payload,
)


class RemoteControlPayloadTests(unittest.TestCase):
    """Keep every body byte-identical to the app request it was copied from."""

    def test_find_vehicle(self) -> None:
        """Flash the horn and lights with an empty command verb."""
        self.assertEqual(
            find_vehicle_payload(),
            {
                "command": "",
                "serviceId": "RHL",
                "setting": {
                    "serviceParameters": [
                        {"key": "rhl", "value": "horn-light-flash"}
                    ]
                },
            },
        )

    def test_climate_start_and_stop(self) -> None:
        """Send string values for the AC flag, target, and duration."""
        self.assertEqual(
            climate_payload(True, 22, 15),
            {
                "command": "start",
                "serviceId": "ZAF",
                "setting": {
                    "serviceParameters": [
                        {"key": "AC", "value": "true"},
                        {"key": "AC.temp", "value": "22.0"},
                        {"key": "AC.duration", "value": "15"},
                    ]
                },
            },
        )
        self.assertEqual(
            climate_payload(False),
            {
                "command": "start",
                "serviceId": "ZAF",
                "setting": {"serviceParameters": [{"key": "AC", "value": "false"}]},
            },
        )

    def test_doors(self) -> None:
        """Lock sends RDL and unlock sends RDU with the same door parameter."""
        self.assertEqual(door_payload(True)["serviceId"], "RDL")
        self.assertEqual(door_payload(False)["serviceId"], "RDU")
        self.assertEqual(
            door_payload(True)["setting"]["serviceParameters"],
            [{"key": "door", "value": "all"}],
        )

    def test_seat_heating(self) -> None:
        """Address the driver seat as SH.11 with string values."""
        self.assertEqual(
            seat_heating_payload(True, 3, 15),
            {
                "command": "start",
                "serviceId": "ZAF",
                "setting": {
                    "serviceParameters": [
                        {"key": "SH.11", "value": "true"},
                        {"key": "SH.11.level", "value": "3"},
                        {"key": "SH.11.duration", "value": "15"},
                    ]
                },
            },
        )
        self.assertEqual(
            seat_heating_payload(False)["setting"]["serviceParameters"],
            [{"key": "SH.11", "value": "false"}],
        )

    def test_steering_wheel_heating(self) -> None:
        """Use the app's boolean flag, an empty command, and a numeric duration."""
        self.assertEqual(
            steering_wheel_heating_payload(True, 3, 15),
            {
                "command": "",
                "serviceId": "ZAF",
                "setting": {
                    "serviceParameters": [
                        {"key": "SW", "value": True},
                        {"key": "SW.level", "value": "3"},
                        {"key": "SW.duration", "value": 15},
                    ]
                },
            },
        )
        self.assertEqual(
            steering_wheel_heating_payload(False)["setting"]["serviceParameters"],
            [{"key": "SW", "value": False}],
        )

    def test_modelled_options_are_optional(self) -> None:
        """Omit target, level, and duration when the caller leaves them unset."""
        climate_keys = [
            item["key"]
            for item in climate_payload(True)["setting"]["serviceParameters"]
        ]
        seat_keys = [
            item["key"]
            for item in seat_heating_payload(True)["setting"]["serviceParameters"]
        ]
        self.assertEqual(climate_keys, ["AC"])
        self.assertEqual(seat_keys, ["SH.11"])

    def test_sentry_and_custom(self) -> None:
        """Keep the existing RSM body and support unmodelled commands."""
        self.assertEqual(
            sentry_payload(True),
            {
                "command": "start",
                "serviceId": "RSM",
                "setting": {"serviceParameters": [{"key": "rsm", "value": "6"}]},
            },
        )
        self.assertEqual(sentry_payload(False)["command"], "stop")
        self.assertEqual(
            custom_payload("start", "ZAF", {"AC": "true"}),
            {
                "command": "start",
                "serviceId": "ZAF",
                "setting": {"serviceParameters": [{"key": "AC", "value": "true"}]},
            },
        )


if __name__ == "__main__":
    unittest.main()
