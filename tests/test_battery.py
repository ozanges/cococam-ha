"""Verify read-only battery collection and its persistent cache."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, call, patch

from bridge.battery import Battery, parse_battery


class BatteryTest(unittest.TestCase):
    def test_cloudedge_values_and_unknown_charging(self):
        self.assertEqual(parse_battery({"154": {"value": "78"}, "156": 1}),
                         {"percent": 78, "charging": True})
        self.assertEqual(parse_battery({154: 0}), {"percent": 0, "charging": None})
        self.assertIsNone(parse_battery({"154": 101, "156": 0}))
        self.assertIsNone(parse_battery({"154": True}))

    def test_collect_without_opening_video_and_scope_cache(self):
        config = {"email": "camera@example.invalid", "camera_name": "Garage"}
        api = Mock()
        api.get_camera_devices.return_value = [
            {"deviceName": "Other", "snNum": "other"},
            {"deviceName": "Garage", "snNum": "fixture"},
        ]
        api.get_battery_info.return_value = {"154": 78, "156": 0}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "battery.json"
            battery = Battery(config, path)
            with patch("bridge.battery.cloud_client", return_value=(api, {})):
                sample = battery.read()
            self.assertEqual(api.mock_calls, [
                call.login(), call.get_camera_devices(), call.get_battery_info("fixture"),
            ])
            battery.save(sample)
            snapshot = Battery(config, path).snapshot()
            self.assertEqual(snapshot, {
                "percent": 78, "charging": False, "observed_at": sample["observed_at"],
            })
            self.assertIsNone(Battery(config | {"camera_name": "Other"}, path).snapshot())
