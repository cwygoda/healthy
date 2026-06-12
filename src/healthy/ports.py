"""Ports used by the hexagonal application core."""

from __future__ import annotations

from typing import Protocol

from healthy.domain import Activity, DownloadFormat, LoadedActivity, StoredActivity


class GarminActivityPort(Protocol):
    """Outbound port for Garmin activity listing/downloading."""

    def list_activities(
        self,
        *,
        start: int,
        limit: int,
        activity_type: str | None = None,
    ) -> list[Activity]:
        """Return activities ordered as Garmin provides them, newest first."""

    def download_activity(self, activity_id: str, download_format: DownloadFormat) -> bytes:
        """Download one activity file from Garmin."""


class ActivityStoragePort(Protocol):
    """Outbound port for local activity persistence."""

    def has_activity(self, activity_id: str) -> bool:
        """Return True when the activity already exists locally."""

    def save_activity(
        self,
        activity: Activity,
        content: bytes,
        download_format: DownloadFormat,
    ) -> StoredActivity:
        """Persist an activity download and metadata."""

    def load_activity(self, activity_id: str) -> LoadedActivity | None:
        """Load a persisted activity download, or None when absent."""
