from __future__ import annotations

import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from healthy.adapters import notifications
from healthy.adapters.notifications import (
    NOTIFICATION_GROUP,
    _notification_script,
    _terminal_notifier_command,
    find_terminal_notifier,
    show_macos_notification,
)

TERMINAL_NOTIFIER_PATH = "/opt/homebrew/bin/terminal-notifier"
LAUNCHD_PATH = "/usr/bin:/bin:/usr/sbin:/sbin"


class TerminalNotifierCommandTests(unittest.TestCase):
    def test_notifications_share_one_group_so_the_previous_one_is_replaced(self) -> None:
        command = _terminal_notifier_command(TERMINAL_NOTIFIER_PATH, "healthy", "Downloaded 3 new activities", None)

        self.assertEqual(
            command,
            [
                TERMINAL_NOTIFIER_PATH,
                "-group",
                NOTIFICATION_GROUP,
                "-title",
                "healthy",
                "-message",
                "Downloaded 3 new activities",
            ],
        )

    def test_subtitle_is_passed_through(self) -> None:
        command = _terminal_notifier_command(TERMINAL_NOTIFIER_PATH, "healthy", "message", "Auto-run complete")

        self.assertEqual(command[-2:], ["-subtitle", "Auto-run complete"])


class NotificationScriptTests(unittest.TestCase):
    def test_title_and_message(self) -> None:
        self.assertEqual(
            _notification_script("healthy", "No new Garmin activity", None),
            'display notification "No new Garmin activity" with title "healthy"',
        )

    def test_subtitle_is_appended(self) -> None:
        self.assertEqual(
            _notification_script("healthy", "message", "Auto-run failed"),
            'display notification "message" with title "healthy" subtitle "Auto-run failed"',
        )

    def test_quotes_are_escaped(self) -> None:
        self.assertEqual(
            _notification_script("healthy", 'say "hi"', None),
            'display notification "say \\"hi\\"" with title "healthy"',
        )


class FindTerminalNotifierTests(unittest.TestCase):
    def setUp(self) -> None:
        self.homebrew_bin = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.homebrew_bin)
        self.empty_bin = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.empty_bin)

    def _install_terminal_notifier(self) -> Path:
        executable = self.homebrew_bin / "terminal-notifier"
        executable.touch(mode=0o755)
        return executable

    def test_found_in_homebrew_prefix_when_path_is_the_bare_launchd_one(self) -> None:
        executable = self._install_terminal_notifier()

        with (
            mock.patch.dict(os.environ, {"PATH": str(self.empty_bin)}),
            mock.patch.object(notifications, "HOMEBREW_BIN_DIRS", (str(self.homebrew_bin),)),
        ):
            self.assertEqual(find_terminal_notifier(), str(executable))

    def test_path_wins_over_homebrew_prefix(self) -> None:
        self._install_terminal_notifier()
        on_path = self.empty_bin / "terminal-notifier"
        on_path.touch(mode=0o755)

        with (
            mock.patch.dict(os.environ, {"PATH": str(self.empty_bin)}),
            mock.patch.object(notifications, "HOMEBREW_BIN_DIRS", (str(self.homebrew_bin),)),
        ):
            self.assertEqual(find_terminal_notifier(), str(on_path))

    def test_returns_none_when_not_installed_anywhere(self) -> None:
        with (
            mock.patch.dict(os.environ, {"PATH": str(self.empty_bin)}),
            mock.patch.object(notifications, "HOMEBREW_BIN_DIRS", (str(self.homebrew_bin),)),
        ):
            self.assertIsNone(find_terminal_notifier())


class ShowNotificationTests(unittest.TestCase):
    def test_prefers_terminal_notifier_when_installed(self) -> None:
        with (
            mock.patch.object(notifications.shutil, "which", return_value=TERMINAL_NOTIFIER_PATH),
            mock.patch.object(notifications.subprocess, "run") as run,
        ):
            show_macos_notification("healthy", "message", "Auto-run complete")

        run.assert_called_once_with(
            _terminal_notifier_command(TERMINAL_NOTIFIER_PATH, "healthy", "message", "Auto-run complete"),
            check=True,
        )

    def test_falls_back_to_applescript_when_missing(self) -> None:
        with (
            mock.patch.object(notifications.shutil, "which", return_value=None),
            mock.patch.object(notifications.subprocess, "run") as run,
        ):
            show_macos_notification("healthy", "message", "Auto-run complete")

        run.assert_called_once_with(
            ["osascript", "-e", _notification_script("healthy", "message", "Auto-run complete")],
            check=True,
        )


if __name__ == "__main__":
    unittest.main()
