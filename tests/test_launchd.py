from __future__ import annotations

import unittest

from healthy.adapters.launchd import LABEL, build_plist


class LaunchdTests(unittest.TestCase):
    def test_build_plist_runs_autorun_tick_every_calendar_minute(self) -> None:
        payload = build_plist(
            healthy_executable="/Users/me/.local/bin/healthy",
            sleep_threshold_minutes=30,
            network_timeout_minutes=10,
        )

        self.assertEqual(payload["Label"], LABEL)
        self.assertEqual(
            payload["ProgramArguments"],
            [
                "/Users/me/.local/bin/healthy",
                "autorun",
                "tick",
                "--sleep-threshold-minutes",
                "30",
                "--network-timeout-minutes",
                "10",
            ],
        )
        self.assertEqual(payload["StartCalendarInterval"], [{"Minute": minute} for minute in range(60)])
        self.assertEqual(payload["ProcessType"], "Background")


if __name__ == "__main__":
    unittest.main()
