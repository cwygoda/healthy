"""Filesystem activity storage adapter."""

from __future__ import annotations

import io
import json
import lzma
import re
import zipfile
from dataclasses import asdict, dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from healthy.domain import Activity, DownloadFormat, LoadedActivity, StoredActivity


class StorageCompression(StrEnum):
    """Compression algorithms supported by filesystem storage."""

    NONE = "none"
    XZ = "xz"


@dataclass(frozen=True, slots=True)
class _StoredPayload:
    content: bytes
    extension: str
    extracted_from_archive: str | None = None
    original_filename: str | None = None


class FileActivityStorage:
    """Store activity files and metadata in a local directory."""

    manifest_name = "manifest.json"

    def __init__(self, root: Path, *, compression: StorageCompression | str = StorageCompression.NONE) -> None:
        self.root = root.expanduser()
        self.root.mkdir(parents=True, exist_ok=True)
        self.compression = StorageCompression(compression)
        self._manifest_path = self.root / self.manifest_name
        self._manifest = self._load_manifest()

    def has_activity(self, activity_id: str) -> bool:
        activity_id = str(activity_id)
        entry = self._manifest.get("activities", {}).get(activity_id)
        if isinstance(entry, dict):
            path = entry.get("path")
            if path and self._resolve_stored_path(path).exists():
                return True

        # Allow adopting an existing directory of downloaded files even before a
        # manifest exists. This keeps "stop at first local activity" useful for
        # hand-populated storage.
        return any(
            path.is_file()
            and path.name != self.manifest_name
            and path.suffix.lower() != ".json"
            and activity_id in path.stem
            for path in self.root.rglob(f"*{activity_id}*")
        )

    def load_activity(self, activity_id: str) -> LoadedActivity | None:
        """Load one activity's bytes from storage.

        Compressed files are transparently decompressed before being returned.
        XZ-compressed ``original`` downloads store the file that Garmin wrapped
        in its ZIP archive (normally FIT), not the ZIP container itself.
        """

        activity_id = str(activity_id)
        entry = self._manifest.get("activities", {}).get(activity_id)
        if isinstance(entry, dict):
            path_value = entry.get("path")
            if isinstance(path_value, str):
                path = self._resolve_stored_path(path_value)
                if path.exists():
                    return self._load_activity_path(activity_id, path, entry)

        for path in sorted(self.root.rglob(f"*{activity_id}*")):
            if path.is_file() and path.name != self.manifest_name and path.suffix.lower() != ".json":
                return self._load_activity_path(activity_id, path, {})
        return None

    def save_activity(
        self,
        activity: Activity,
        content: bytes,
        download_format: DownloadFormat,
    ) -> StoredActivity:
        filename_base = _activity_filename_base(activity)
        payload = _prepare_stored_payload(content, download_format, self.compression)
        activity_path = self.root / self._stored_filename(filename_base, payload.extension)

        # Make repeat saves explicit instead of silently overwriting unrelated
        # files; the normal flow calls has_activity before save_activity.
        activity_path = _next_available_path(activity_path)
        metadata_path = _metadata_path_for(activity_path)

        activity_path.write_bytes(payload.content)
        metadata_download: dict[str, Any] = {
            "format": download_format.value,
            "path": str(activity_path),
            "compression": None if self.compression is StorageCompression.NONE else self.compression.value,
        }
        if payload.extracted_from_archive is not None:
            metadata_download["extracted_from_archive"] = payload.extracted_from_archive
        if payload.original_filename is not None:
            metadata_download["original_filename"] = payload.original_filename

        metadata_path.write_text(
            json.dumps(
                {
                    "activity": asdict(activity),
                    "download": metadata_download,
                },
                indent=2,
                sort_keys=True,
                default=str,
            ),
            encoding="utf-8",
        )

        manifest_entry = {
            "id": activity.id,
            "name": activity.name,
            "start_time_local": activity.start_time_local,
            "activity_type": activity.activity_type,
            "format": download_format.value,
            "path": str(activity_path),
            "metadata_path": str(metadata_path),
            "compression": None if self.compression is StorageCompression.NONE else self.compression.value,
        }
        if payload.extracted_from_archive is not None:
            manifest_entry["extracted_from_archive"] = payload.extracted_from_archive
        if payload.original_filename is not None:
            manifest_entry["original_filename"] = payload.original_filename

        self._manifest.setdefault("activities", {})[activity.id] = manifest_entry
        self._write_manifest()

        return StoredActivity(
            activity_id=activity.id,
            path=str(activity_path),
            metadata_path=str(metadata_path),
        )

    def _load_activity_path(self, activity_id: str, path: Path, entry: dict[str, Any]) -> LoadedActivity:
        compression = entry.get("compression")
        content = path.read_bytes()
        if compression == StorageCompression.XZ.value or path.suffix.lower() == ".xz":
            content = lzma.decompress(content, format=lzma.FORMAT_XZ)

        metadata_path = entry.get("metadata_path") if isinstance(entry.get("metadata_path"), str) else None
        if metadata_path is None:
            adjacent_metadata_path = _metadata_path_for(path)
            if adjacent_metadata_path.exists():
                metadata_path = str(adjacent_metadata_path)

        return LoadedActivity(
            activity_id=activity_id,
            content=content,
            download_format=_download_format_for(path, entry),
            path=str(path),
            metadata_path=metadata_path,
        )

    def _stored_filename(self, filename_base: str, extension: str) -> str:
        filename = f"{filename_base}.{extension}"
        if self.compression is StorageCompression.XZ:
            return f"{filename}.xz"
        return filename

    def _resolve_stored_path(self, path: str) -> Path:
        candidate = Path(path).expanduser()
        if candidate.is_absolute() or candidate.exists():
            return candidate
        return self.root / candidate

    def _load_manifest(self) -> dict[str, Any]:
        if not self._manifest_path.exists():
            return {"activities": {}}
        try:
            payload = json.loads(self._manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {"activities": {}}
        if not isinstance(payload, dict):
            return {"activities": {}}
        if not isinstance(payload.get("activities"), dict):
            payload["activities"] = {}
        return payload

    def _write_manifest(self) -> None:
        _write_json_atomic(self._manifest_path, self._manifest)


class XzFileActivityStorage(FileActivityStorage):
    """Filesystem storage adapter that stores activity downloads as XZ."""

    def __init__(self, root: Path) -> None:
        super().__init__(root, compression=StorageCompression.XZ)


def _activity_filename_base(activity: Activity) -> str:
    start = _slug(activity.start_time_local).strip("-") or "unknown-time"
    activity_type = _slug(activity.activity_type).strip("-") or "activity"
    name = _slug(activity.name).strip("-") or "unnamed"
    return f"{start}_{activity.id}_{activity_type}_{name}"[:180]


def _slug(value: str) -> str:
    value = value.replace(":", "-").replace("/", "-")
    value = re.sub(r"[^A-Za-z0-9_.-]+", "-", value)
    value = re.sub(r"-+", "-", value)
    return value.strip(".-")


def _prepare_stored_payload(
    content: bytes,
    download_format: DownloadFormat,
    compression: StorageCompression,
) -> _StoredPayload:
    if compression is StorageCompression.NONE:
        return _StoredPayload(content=content, extension=download_format.extension)

    payload = _StoredPayload(content=content, extension=download_format.extension)
    if download_format is DownloadFormat.ORIGINAL:
        payload = _extract_single_zip_member(content)
    return _StoredPayload(
        content=lzma.compress(payload.content, format=lzma.FORMAT_XZ),
        extension=payload.extension,
        extracted_from_archive=payload.extracted_from_archive,
        original_filename=payload.original_filename,
    )


def _extract_single_zip_member(content: bytes) -> _StoredPayload:
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        names = [info.filename for info in archive.infolist() if not info.is_dir()]
        if len(names) != 1:
            raise ValueError(f"Expected Garmin original ZIP to contain one file, found {len(names)}")
        filename = names[0]
        return _StoredPayload(
            content=archive.read(filename),
            extension=_filename_extension(filename) or "fit",
            extracted_from_archive="zip",
            original_filename=filename,
        )



def _filename_extension(filename: str) -> str:
    suffix = Path(filename).suffix.lower().lstrip(".")
    return _slug(suffix) if suffix else ""


def _next_available_path(path: Path) -> Path:
    if not path.exists():
        return path

    suffix = "".join(path.suffixes[-2:]) if path.suffix.lower() == ".xz" and len(path.suffixes) >= 2 else path.suffix
    stem = path.name[: -len(suffix)] if suffix else path.name
    for index in range(1, 10_000):
        candidate = path.with_name(f"{stem}-{index}{suffix}")
        if not candidate.exists():
            return candidate

    raise RuntimeError(f"Could not find an available filename for {path}")


def _metadata_path_for(activity_path: Path) -> Path:
    if activity_path.suffix.lower() == ".xz":
        return activity_path.with_suffix("").with_suffix(".json")
    return activity_path.with_suffix(".json")


def _download_format_for(path: Path, entry: dict[str, Any]) -> DownloadFormat:
    format_value = entry.get("format")
    if isinstance(format_value, str):
        try:
            return DownloadFormat(format_value)
        except ValueError:
            pass

    suffixes = [suffix.lower().lstrip(".") for suffix in path.suffixes]
    if suffixes and suffixes[-1] == StorageCompression.XZ.value:
        suffixes.pop()
    extension = suffixes[-1] if suffixes else "zip"
    if extension in {"zip", "fit"}:
        return DownloadFormat.ORIGINAL
    try:
        return DownloadFormat(extension)
    except ValueError:
        return DownloadFormat.ORIGINAL


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    temporary_path = path.with_suffix(f"{path.suffix}.tmp")
    temporary_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )
    temporary_path.replace(path)
