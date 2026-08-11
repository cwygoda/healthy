from __future__ import annotations

import json
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

from healthy.autorun import (
    AutorunConfig,
    AutorunDecision,
    AutorunStateStore,
    evaluate_autorun_tick,
    wait_for_network,
)

NOON = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


def _evaluate(
    *,
    state_store: AutorunStateStore,
    is_awake: bool = True,
    now: datetime = NOON,
    interval_minutes: float = 30.0,
    network_ready: bool = True,
    log: list[str] | None = None,
):
    return evaluate_autorun_tick(
        state_store=state_store,
        config=AutorunConfig(sync_interval_minutes=interval_minutes, network_timeout_minutes=0.0),
        log=(log if log is not None else []).append,
        is_awake=lambda: is_awake,
        clock=lambda: now,
        sleep=lambda seconds: None,
        network_probe=lambda: network_ready,
    )


class AutorunDecisionTests(unittest.TestCase):
    def test_dark_wake_never_downloads_even_when_sync_is_stale(self) -> None:
        """Regression: launchd runs a catch-up tick on every DarkWake."""

        with tempfile.TemporaryDirectory() as directory:
            store = AutorunStateStore(Path(directory) / "state.json")
            store.write_last_sync(datetime(2026, 1, 1, 0, 0, tzinfo=UTC))

            result = _evaluate(state_store=store, is_awake=False)

            self.assertIs(result.decision, AutorunDecision.DARK_WAKE)
            self.assertFalse(result.should_download)

    def test_full_wake_without_previous_sync_downloads(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = AutorunStateStore(Path(directory) / "state.json")

            result = _evaluate(state_store=store)

            self.assertIs(result.decision, AutorunDecision.READY)
            self.assertTrue(result.should_download)
            self.assertIsNone(result.staleness_seconds)

    def test_full_wake_with_stale_sync_downloads(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = AutorunStateStore(Path(directory) / "state.json")
            store.write_last_sync(datetime(2026, 1, 1, 11, 18, tzinfo=UTC))

            result = _evaluate(state_store=store)

            self.assertIs(result.decision, AutorunDecision.READY)
            self.assertEqual(result.staleness_seconds, 42 * 60)

    def test_full_wake_with_recent_sync_does_not_download(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = AutorunStateStore(Path(directory) / "state.json")
            store.write_last_sync(datetime(2026, 1, 1, 11, 50, tzinfo=UTC))

            result = _evaluate(state_store=store)

            self.assertIs(result.decision, AutorunDecision.RECENTLY_SYNCED)
            self.assertFalse(result.should_download)

    def test_unavailable_network_reports_without_downloading(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = AutorunStateStore(Path(directory) / "state.json")

            result = _evaluate(state_store=store, network_ready=False)

            self.assertIs(result.decision, AutorunDecision.NETWORK_UNAVAILABLE)
            self.assertFalse(result.should_download)

    def test_evaluation_does_not_advance_the_last_sync_timestamp(self) -> None:
        """Only a completed download may advance it, so failures retry."""

        with tempfile.TemporaryDirectory() as directory:
            store = AutorunStateStore(Path(directory) / "state.json")

            _evaluate(state_store=store)

            self.assertIsNone(store.read_last_sync())

    def test_quiet_decisions_do_not_write_log_lines(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = AutorunStateStore(Path(directory) / "state.json")
            store.write_last_sync(datetime(2026, 1, 1, 11, 50, tzinfo=UTC))
            logs: list[str] = []

            _evaluate(state_store=store, is_awake=False, log=logs)
            _evaluate(state_store=store, log=logs)

            self.assertEqual(logs, [])


class AutorunStateStoreTests(unittest.TestCase):
    def test_roundtrips_the_last_sync_timestamp(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = AutorunStateStore(Path(directory) / "nested" / "state.json")
            store.write_last_sync(NOON)

            self.assertEqual(store.read_last_sync(), NOON)

    def test_state_from_the_gap_based_version_counts_as_never_synced(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            path.write_text(json.dumps({"last_tick_at": "2026-01-01T12:00:00Z"}))

            self.assertIsNone(AutorunStateStore(path).read_last_sync())

    def test_unreadable_state_counts_as_never_synced(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            path.write_text("not json")

            self.assertIsNone(AutorunStateStore(path).read_last_sync())


class NetworkWaitTests(unittest.TestCase):
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
