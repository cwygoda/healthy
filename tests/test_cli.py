from __future__ import annotations

import unittest
from pathlib import Path

from healthy.cli import DEFAULT_ACTIVITY_DIR


class CliDefaultsTests(unittest.TestCase):
    def test_default_activity_dir_uses_documents_activities(self) -> None:
        self.assertEqual(DEFAULT_ACTIVITY_DIR, Path("~/Documents/Activities"))


if __name__ == "__main__":
    unittest.main()
