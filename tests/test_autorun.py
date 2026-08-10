from __future__ import annotations

import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

from healthy.autorun import AutorunConfig, AutorunStateStore, run_wake_detection_tick, wait_for_network


class AutorunTests(unittest.TestCase):
    def test_first_tick_initializes_state_without_triggering(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            logs: list[str] = []
            result = run_wake_detection_tick(
                state_store=AutorunStateStore(Path(directory) / "state.json"),
                config=AutorunConfig(),
                log=logs.append,
                clock=lambda: datetime(2026, 1, 1, tzinfo=UTC),
            )

            self.assertFalse(result.triggered)
            self.assertIn("initialized", logs[0])

    def test_short_gap_does_not_trigger(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = AutorunStateStore(Path(directory) / "state.json")
            store.write_last_tick(datetime(2026, 1, 1, 10, 0, tzinfo=UTC))

            result = run_wake_detection_tick(
                state_store=store,
                config=AutorunConfig(sleep_threshold_minutes=30),
                log=lambda message: None,
                clock=lambda: datetime(2026, 1, 1, 10, 10, tzinfo=UTC),
            )

            self.assertFalse(result.triggered)

    def test_long_gap_waits_for_network_without_notifying(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = AutorunStateStore(Path(directory) / "state.json")
            store.write_last_tick(datetime(2026, 1, 1, 10, 0, tzinfo=UTC))

            result = run_wake_detection_tick(
                state_store=store,
                config=AutorunConfig(sleep_threshold_minutes=30),
                log=lambda message: None,
                clock=lambda: datetime(2026, 1, 1, 10, 42, tzinfo=UTC),
                network_probe=lambda: True,
            )

            self.assertTrue(result.triggered)
            self.assertTrue(result.network_ready)
            self.assertIn("Wake gap: 42 minutes", result.message)

    def test_network_wait_retries_with_backoff(self) -> None:
        attempts = iter([False, False, True])
        sleeps: list[float] = []

        ready = wait_for_network(
            probe=lambda: next(attempts),
            timeout_seconds=60,
            sleep=sleeps.append,
        )

        self.assertTrue(ready)
        self.assertEqual(sleeps, [2])


if __name__ == "__main__":
    unittest.main()
