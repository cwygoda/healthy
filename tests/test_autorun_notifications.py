from __future__ import annotations

import unittest

from healthy.cli import _autorun_download_notification
from healthy.domain import DownloadSummary


class AutorunNotificationTests(unittest.TestCase):
    def test_downloaded_activity_message(self) -> None:
        self.assertEqual(
            _autorun_download_notification(DownloadSummary(downloaded=1)),
            ("Auto-run complete", "Downloaded 1 new activity"),
        )

    def test_downloaded_activities_message(self) -> None:
        self.assertEqual(
            _autorun_download_notification(DownloadSummary(downloaded=3)),
            ("Auto-run complete", "Downloaded 3 new activities"),
        )

    def test_no_activity_message(self) -> None:
        self.assertEqual(
            _autorun_download_notification(DownloadSummary(downloaded=0, skipped_existing=1)),
            ("Auto-run complete", "No new Garmin activity"),
        )

    def test_failure_message(self) -> None:
        self.assertEqual(
            _autorun_download_notification(DownloadSummary(failed=1)),
            ("Auto-run failed", "healthy auto-run failed — see log"),
        )


if __name__ == "__main__":
    unittest.main()
