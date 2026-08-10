"""Application logic for wake-triggered autoruns."""

from __future__ import annotations

import json
import socket
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Callable


Clock = Callable[[], datetime]
Sleeper = Callable[[float], None]
NetworkProbe = Callable[[], bool]
Logger = Callable[[str], None]


@dataclass(frozen=True, slots=True)
class AutorunConfig:
    """Configuration for one autorun tick."""

    sleep_threshold_minutes: float = 30.0
    network_timeout_minutes: float = 10.0
    network_host: str = "connect.garmin.com"
    network_port: int = 443
    network_probe_timeout_seconds: float = 2.0


@dataclass(frozen=True, slots=True)
class AutorunTickResult:
    """Result of one autorun tick."""

    triggered: bool
    network_ready: bool = False
    gap_seconds: float | None = None
    message: str = ""


class AutorunStateStore:
    """JSON-backed state for wake gap detection."""

    def __init__(self, path: Path) -> None:
        self._path = path.expanduser()

    def read_last_tick(self) -> datetime | None:
        if not self._path.exists():
            return None
        try:
            payload = json.loads(self._path.read_text())
            value = payload.get("last_tick_at")
            if not isinstance(value, str):
                return None
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except (OSError, ValueError, json.JSONDecodeError):
            return None

    def write_last_tick(self, now: datetime) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"last_tick_at": _format_utc(now)}
        self._path.write_text(json.dumps(payload, indent=2) + "\n")


def run_wake_detection_tick(
    *,
    state_store: AutorunStateStore,
    config: AutorunConfig,
    log: Logger,
    clock: Clock = lambda: datetime.now(UTC),
    sleep: Sleeper = time.sleep,
    network_probe: NetworkProbe | None = None,
) -> AutorunTickResult:
    """Detect a wake gap and wait for network when autorun should fire."""

    now = clock()
    last_tick = state_store.read_last_tick()
    state_store.write_last_tick(now)

    if last_tick is None:
        log("autorun tick initialized")
        return AutorunTickResult(triggered=False, message="initialized")

    gap_seconds = (now - last_tick).total_seconds()
    threshold_seconds = config.sleep_threshold_minutes * 60
    if gap_seconds < threshold_seconds:
        log(f"autorun tick skipped; gap={gap_seconds:.0f}s threshold={threshold_seconds:.0f}s")
        return AutorunTickResult(triggered=False, gap_seconds=gap_seconds, message="below threshold")

    log(f"wake gap detected; gap={gap_seconds:.0f}s threshold={threshold_seconds:.0f}s")
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
        message = f"Wake gap: {_minutes(gap_seconds)} minutes. Network not ready."
        log("autorun network wait timed out")
        return AutorunTickResult(
            triggered=True,
            network_ready=False,
            gap_seconds=gap_seconds,
            message=message,
        )

    message = f"Wake gap: {_minutes(gap_seconds)} minutes. Network is ready."
    log("autorun wake detection complete")
    return AutorunTickResult(
        triggered=True,
        network_ready=True,
        gap_seconds=gap_seconds,
        message=message,
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


def _minutes(seconds: float) -> int:
    return round(seconds / 60)
