"""macOS power state adapters."""

from __future__ import annotations

import contextlib
import os
import subprocess
from typing import Iterator

GRAPHICS_CAPABILITY = "Graphics"
SYSTEMSTATE_TIMEOUT_SECONDS = 5.0


def is_fully_awake() -> bool:
    """Return whether the Mac is in a full wake rather than a DarkWake.

    macOS advertises the Graphics capability on every full wake and on no
    DarkWake, so it cleanly separates "the user is back" from the maintenance
    wakes that fire every few minutes while the lid is closed.

    Fails open: an unreadable power state returns True so a `pmset` change can
    never silently disable autorun. A spurious run during DarkWake is harmless
    because the download holds a power assertion.
    """

    capabilities = _read_system_capabilities()
    if capabilities is None:
        return True
    return GRAPHICS_CAPABILITY in capabilities


def parse_system_capabilities(output: str) -> frozenset[str] | None:
    """Parse capability names out of `pmset -g systemstate` output.

    Returns None when no capabilities line is present, meaning "unknown".
    """

    for line in output.splitlines():
        if "Capabilities" not in line:
            continue
        _, separator, capabilities = line.rpartition(":")
        if not separator:
            continue
        names = capabilities.split()
        if names:
            return frozenset(names)
    return None


@contextlib.contextmanager
def power_assertion() -> Iterator[None]:
    """Hold an idle-sleep assertion for the duration of the block.

    Without this, a download started during a short wake window is killed when
    the Mac goes back to sleep. This cannot prevent clamshell sleep, so a sync
    can still be cut short by closing the lid.
    """

    try:
        process = subprocess.Popen(["caffeinate", "-i", "-w", str(os.getpid())])
    except OSError:
        yield
        return
    try:
        yield
    finally:
        process.terminate()
        with contextlib.suppress(subprocess.SubprocessError):
            process.wait(timeout=SYSTEMSTATE_TIMEOUT_SECONDS)


def _read_system_capabilities() -> frozenset[str] | None:
    try:
        result = subprocess.run(
            ["pmset", "-g", "systemstate"],
            check=False,
            capture_output=True,
            text=True,
            timeout=SYSTEMSTATE_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode:
        return None
    return parse_system_capabilities(result.stdout)
