from __future__ import annotations

import io
import json
import lzma
import tempfile
import unittest
import zipfile
from pathlib import Path

from healthy.adapters.storage import FileActivityStorage, StorageCompression
from healthy.domain import Activity, DownloadFormat


class FileActivityStorageTests(unittest.TestCase):
    def test_xz_storage_extracts_original_zip_member_and_loads_original_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            storage = FileActivityStorage(root, compression=StorageCompression.XZ)
            activity = _activity("123")
            fit_content = b"fake fit payload"
            zip_content = _zip_with_single_file("123_ACTIVITY.fit", fit_content)

            stored = storage.save_activity(activity, zip_content, DownloadFormat.ORIGINAL)
            stored_path = Path(stored.path)

            self.assertEqual(stored_path.suffixes[-2:], [".fit", ".xz"])
            self.assertEqual(lzma.decompress(stored_path.read_bytes()), fit_content)

            loaded = storage.load_activity("123")
            self.assertIsNotNone(loaded)
            assert loaded is not None
            self.assertEqual(loaded.content, fit_content)
            self.assertEqual(loaded.download_format, DownloadFormat.ORIGINAL)

            metadata = json.loads(Path(stored.metadata_path or "").read_text())
            self.assertEqual(metadata["download"]["compression"], "xz")
            self.assertEqual(metadata["download"]["extracted_from_archive"], "zip")
            self.assertEqual(metadata["download"]["original_filename"], "123_ACTIVITY.fit")


def _activity(activity_id: str) -> Activity:
    return Activity(
        id=activity_id,
        name="Berlin Running",
        start_time_local="2026-06-14 12:34:56",
        activity_type="running",
        raw={"activityId": activity_id},
    )


def _zip_with_single_file(filename: str, content: bytes) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(filename, content)
    return buffer.getvalue()


if __name__ == "__main__":
    unittest.main()
