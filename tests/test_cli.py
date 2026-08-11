from __future__ import annotations

import unittest
from pathlib import Path

from healthy.adapters.storage import StorageCompression
from healthy.cli_common import DEFAULT_ACTIVITY_DIR, DEFAULT_STORAGE_COMPRESSION


class CliDefaultsTests(unittest.TestCase):
    def test_default_activity_dir_uses_documents_activities(self) -> None:
        self.assertEqual(DEFAULT_ACTIVITY_DIR, Path("~/Documents/Activities"))

    def test_default_storage_compression_uses_xz(self) -> None:
        self.assertEqual(DEFAULT_STORAGE_COMPRESSION, StorageCompression.XZ)


if __name__ == "__main__":
    unittest.main()
