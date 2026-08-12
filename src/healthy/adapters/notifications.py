"""Notification adapters."""

from __future__ import annotations

import os
import shutil
import subprocess

NOTIFICATION_GROUP = "net.wygoda.healthy"
TERMINAL_NOTIFIER = "terminal-notifier"
HOMEBREW_BIN_DIRS = ("/opt/homebrew/bin", "/usr/local/bin")


def show_macos_notification(title: str, message: str, subtitle: str | None = None) -> None:
    """Show a macOS notification, replacing any earlier one healthy posted.

    AppleScript cannot dismiss or replace a delivered notification, so notifications stack up
    on every autorun. terminal-notifier groups them, keeping at most one healthy notification
    on screen; without it installed we fall back to a stacking AppleScript notification.
    """

    terminal_notifier = find_terminal_notifier()
    if terminal_notifier is None:
        subprocess.run(["osascript", "-e", _notification_script(title, message, subtitle)], check=True)
        return
    subprocess.run(
        _terminal_notifier_command(terminal_notifier, title, message, subtitle),
        check=True,
    )


def find_terminal_notifier() -> str | None:
    """Locate terminal-notifier, also looking outside PATH.

    launchd hands the autorun agent a bare PATH of /usr/bin:/bin:/usr/sbin:/sbin, so a
    Homebrew-installed terminal-notifier is invisible to a plain PATH lookup and every
    scheduled run would silently fall back to stacking AppleScript notifications.
    """

    on_path = shutil.which(TERMINAL_NOTIFIER)
    if on_path:
        return on_path
    return shutil.which(TERMINAL_NOTIFIER, path=os.pathsep.join(HOMEBREW_BIN_DIRS))


def _terminal_notifier_command(
    executable: str,
    title: str,
    message: str,
    subtitle: str | None,
) -> list[str]:
    command = [executable, "-group", NOTIFICATION_GROUP, "-title", title, "-message", message]
    if subtitle:
        command += ["-subtitle", subtitle]
    return command


def _notification_script(title: str, message: str, subtitle: str | None) -> str:
    script = f'display notification {_applescript_string(message)} with title {_applescript_string(title)}'
    if subtitle:
        script += f' subtitle {_applescript_string(subtitle)}'
    return script


def _applescript_string(value: str) -> str:
    escaped = value.replace('\\', '\\\\').replace('"', '\\"')
    return f'"{escaped}"'
