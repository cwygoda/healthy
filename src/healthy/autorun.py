"""Application logic for wake-triggered autoruns."""

from __future__ import annotations

import json
import socket
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Callable


Clock = Callable[[], datetime]
Sleeper = Callable[[float], None]
NetworkProbe = Callable[[], bool]
WakeProbe = Callable[[], bool]
Logger = Callable[[str], None]


class AutorunDecision(StrEnum):
    """Outcome of evaluating one autorun tick."""

    DARK_WAKE = "dark wake"
    RECENTLY_SYNCED = "recently synced"
    NETWORK_UNAVAILABLE = "network unavailable"
    READY = "ready"


@dataclass(frozen=True, slots=True)
class AutorunConfig:
    """Configuration for one autorun tick."""

    sync_interval_minutes: float = 30.0
    network_timeout_minutes: float = 10.0
    network_host: str = "connect.garmin.com"
    network_port: int = 443
    network_probe_timeout_seconds: float = 2.0


@dataclass(frozen=True, slots=True)
class AutorunTickResult:
    """Result of evaluating one autorun tick."""

    decision: AutorunDecision
    staleness_seconds: float | None = None
    message: str = ""

    @property
    def should_download(self) -> bool:
        return self.decision is AutorunDecision.READY


class AutorunStateStore:
    """JSON-backed record of the last successful sync."""

    def __init__(self, path: Path) -> None:
        self._path = path.expanduser()

    def read_last_sync(self) -> datetime | None:
        if not self._path.exists():
            return None
        try:
            payload = json.loads(self._path.read_text())
            value = payload.get("last_successful_sync_at")
            if not isinstance(value, str):
                return None
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except (OSError, ValueError, json.JSONDecodeError):
            return None

    def write_last_sync(self, now: datetime) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"last_successful_sync_at": _format_utc(now)}
        self._path.write_text(json.dumps(payload, indent=2) + "\n")


def evaluate_autorun_tick(
    *,
    state_store: AutorunStateStore,
    config: AutorunConfig,
    log: Logger,
    is_awake: WakeProbe,
    clock: Clock = lambda: datetime.now(UTC),
    sleep: Sleeper = time.sleep,
    network_probe: NetworkProbe | None = None,
) -> AutorunTickResult:
    """Decide whether this tick should download, waiting for network if so.

    Staleness is measured from the last *successful* sync rather than from the
    previous tick. Tick gaps are useless as a trigger because launchd runs a
    catch-up tick on every DarkWake, which on a sleeping Mac is every few
    minutes, so a gap never accumulates.

    Ticks that decide against downloading stay silent. They fire roughly once a
    minute forever, and logging them buries the lines that matter.
    """

    if not is_awake():
        return AutorunTickResult(
            decision=AutorunDecision.DARK_WAKE,
            message="Dark wake. Nothing to do.",
        )

    now = clock()
    last_sync = state_store.read_last_sync()
    staleness_seconds = None if last_sync is None else (now - last_sync).total_seconds()
    interval_seconds = config.sync_interval_minutes * 60
    if staleness_seconds is not None and staleness_seconds < interval_seconds:
        return AutorunTickResult(
            decision=AutorunDecision.RECENTLY_SYNCED,
            staleness_seconds=staleness_seconds,
            message=f"Synced {_minutes(staleness_seconds)} minutes ago. Nothing to do.",
        )

    log(f"sync due; {_describe_staleness(staleness_seconds)} interval={interval_seconds:.0f}s")
    probe = network_probe or make_tcp_network_probe(
        host=config.network_host,
        port=config.network_port,
        timeout_seconds=config.network_probe_timeout_seconds,
    )
    network_ready = wait_for_network(
        probe=probe,
        timeout_seconds=config.network_timeout_minutes * 60,
        sleep=sleep,
        log=log,
    )
    if not network_ready:
        return AutorunTickResult(
            decision=AutorunDecision.NETWORK_UNAVAILABLE,
            staleness_seconds=staleness_seconds,
            message="Network not ready.",
        )

    return AutorunTickResult(
        decision=AutorunDecision.READY,
        staleness_seconds=staleness_seconds,
        message="Network is ready.",
    )


def wait_for_network(
    *,
    probe: NetworkProbe,
    timeout_seconds: float,
    sleep: Sleeper = time.sleep,
    log: Logger = lambda message: None,
) -> bool:
    """Wait for network with short, low-resource backoff."""

    deadline = time.monotonic() + timeout_seconds
    delays = [0, 2, 5, 10, 20, 30]
    attempt = 0
    while True:
        if probe():
            log(f"network ready after attempt={attempt + 1}")
            return True
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            log("network wait timed out")
            return False
        delay = delays[attempt] if attempt < len(delays) else 30
        attempt += 1
        if delay > 0:
            sleep(min(delay, remaining))


def make_tcp_network_probe(*, host: str, port: int, timeout_seconds: float) -> NetworkProbe:
    """Create a cheap TCP connectivity probe."""

    def probe() -> bool:
        try:
            with socket.create_connection((host, port), timeout=timeout_seconds):
                return True
        except OSError:
            return False

    return probe


def append_log(path: Path) -> Logger:
    """Create a simple append-only file logger."""

    expanded = path.expanduser()

    def log(message: str) -> None:
        expanded.parent.mkdir(parents=True, exist_ok=True)
        timestamp = _format_utc(datetime.now(UTC))
        with expanded.open("a") as file:
            file.write(f"{timestamp} {message}\n")

    return log


def _format_utc(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _describe_staleness(staleness_seconds: float | None) -> str:
    if staleness_seconds is None:
        return "never synced;"
    return f"last sync {staleness_seconds:.0f}s ago;"


def _minutes(seconds: float) -> int:
    return round(seconds / 60)
