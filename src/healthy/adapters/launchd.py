"""launchd adapter for userland autorun installation."""

from __future__ import annotations

import os
import plistlib
import subprocess
from pathlib import Path

LABEL = "net.wygoda.healthy.autorun"
PLIST_PATH = Path("~/Library/LaunchAgents/net.wygoda.healthy.autorun.plist")
LOG_PATH = Path("~/Library/Logs/healthy/autorun.launchd.log")
ERROR_LOG_PATH = Path("~/Library/Logs/healthy/autorun.launchd.err.log")


def install_launch_agent(
    *,
    healthy_executable: str,
    sleep_threshold_minutes: float,
    network_timeout_minutes: float,
    plist_path: Path = PLIST_PATH,
) -> Path:
    """Write and load the user LaunchAgent."""

    path = plist_path.expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    LOG_PATH.expanduser().parent.mkdir(parents=True, exist_ok=True)
    payload = build_plist(
        healthy_executable=healthy_executable,
        sleep_threshold_minutes=sleep_threshold_minutes,
        network_timeout_minutes=network_timeout_minutes,
    )
    with path.open("wb") as file:
        plistlib.dump(payload, file)
    _run_launchctl(["bootstrap", _gui_domain(), str(path)], allow_failure=True)
    _run_launchctl(["enable", f"{_gui_domain()}/{LABEL}"], allow_failure=True)
    return path


def uninstall_launch_agent(*, plist_path: Path = PLIST_PATH) -> Path:
    """Unload and remove the user LaunchAgent."""

    path = plist_path.expanduser()
    _run_launchctl(["bootout", _gui_domain(), str(path)], allow_failure=True)
    if path.exists():
        path.unlink()
    return path


def launch_agent_installed(*, plist_path: Path = PLIST_PATH) -> bool:
    """Return whether the LaunchAgent plist exists."""

    return plist_path.expanduser().exists()


def build_plist(
    *,
    healthy_executable: str,
    sleep_threshold_minutes: float,
    network_timeout_minutes: float,
) -> dict[str, object]:
    """Build the launchd plist payload."""

    return {
        "Label": LABEL,
        "ProgramArguments": [
            healthy_executable,
            "autorun",
            "tick",
            "--sleep-threshold-minutes",
            str(sleep_threshold_minutes),
            "--network-timeout-minutes",
            str(network_timeout_minutes),
        ],
        "StartCalendarInterval": [{"Minute": minute} for minute in range(60)],
        "ProcessType": "Background",
        "LowPriorityIO": True,
        "StandardOutPath": str(LOG_PATH.expanduser()),
        "StandardErrorPath": str(ERROR_LOG_PATH.expanduser()),
    }


def _gui_domain() -> str:
    return f"gui/{os.getuid()}"


def _run_launchctl(args: list[str], *, allow_failure: bool = False) -> None:
    result = subprocess.run(["launchctl", *args], check=False, capture_output=True, text=True)
    if result.returncode and not allow_failure:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "launchctl failed")
