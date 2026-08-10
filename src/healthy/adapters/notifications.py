"""Notification adapters."""

from __future__ import annotations

import subprocess


def show_macos_notification(title: str, message: str, subtitle: str | None = None) -> None:
    """Show a macOS notification via AppleScript."""

    script = f'display notification {_applescript_string(message)} with title {_applescript_string(title)}'
    if subtitle:
        script += f' subtitle {_applescript_string(subtitle)}'
    subprocess.run(["osascript", "-e", script], check=True)


def _applescript_string(value: str) -> str:
    escaped = value.replace('\\', '\\\\').replace('"', '\\"')
    return f'"{escaped}"'
