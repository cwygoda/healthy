"""Domain model for Garmin activity synchronization."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class RateLimitExceeded(RuntimeError):
    """Raised when Garmin keeps rejecting requests due to rate limiting."""


class DownloadFormat(StrEnum):
    """Activity file formats supported by Garmin Connect downloads."""

    ORIGINAL = "original"
    GPX = "gpx"
    TCX = "tcx"
    KML = "kml"
    CSV = "csv"

    @property
    def extension(self) -> str:
        """Return the file extension used for locally persisted downloads."""

        if self is DownloadFormat.ORIGINAL:
            # Garmin returns the original activity wrapped in a zip archive.
            return "zip"
        return self.value


@dataclass(frozen=True, slots=True)
class Activity:
    """A Garmin activity as the application needs to understand it."""

    id: str
    name: str
    start_time_local: str
    activity_type: str
    raw: dict[str, Any]

    @classmethod
    def from_garmin(cls, payload: dict[str, Any]) -> "Activity":
        activity_id = payload.get("activityId") or payload.get("id")
        if activity_id is None:
            raise ValueError(f"Garmin activity has no id: {payload!r}")

        activity_type = payload.get("activityType") or {}
        if isinstance(activity_type, dict):
            type_name = activity_type.get("typeKey") or activity_type.get("typeId") or "unknown"
        else:
            type_name = str(activity_type)

        return cls(
            id=str(activity_id),
            name=str(payload.get("activityName") or "Unnamed activity"),
            start_time_local=str(payload.get("startTimeLocal") or payload.get("startTimeGMT") or "unknown-time"),
            activity_type=str(type_name),
            raw=payload,
        )


@dataclass(frozen=True, slots=True)
class StoredActivity:
    """Information about a persisted activity download."""

    activity_id: str
    path: str
    metadata_path: str | None = None


@dataclass(frozen=True, slots=True)
class LoadedActivity:
    """An activity loaded from local storage."""

    activity_id: str
    content: bytes
    download_format: DownloadFormat
    path: str
    metadata_path: str | None = None


@dataclass(frozen=True, slots=True)
class DownloadSummary:
    """Outcome of an activity synchronization run."""

    inspected: int = 0
    downloaded: int = 0
    skipped_existing: int = 0
    failed: int = 0
    stopped_at_existing: bool = False
    rate_limited: bool = False
    saved_paths: tuple[str, ...] = ()
