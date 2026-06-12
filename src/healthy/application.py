"""Application use cases."""

from __future__ import annotations

from typing import Callable

from healthy.domain import Activity, DownloadFormat, DownloadSummary, RateLimitExceeded
from healthy.ports import ActivityStoragePort, GarminActivityPort


ProgressCallback = Callable[[str, Activity], None]


class DownloadActivitiesUseCase:
    """Download activities from Garmin into local storage.

    By default this behaves like an incremental sync: Garmin activities are read
    newest-first and synchronization stops at the first activity already present
    in local storage. With ``all_missing=True`` the scan continues past existing
    activities and downloads every missing activity it encounters.
    """

    def __init__(
        self,
        garmin: GarminActivityPort,
        storage: ActivityStoragePort,
        *,
        on_progress: ProgressCallback | None = None,
    ) -> None:
        self._garmin = garmin
        self._storage = storage
        self._on_progress = on_progress

    def execute(
        self,
        *,
        download_format: DownloadFormat,
        all_missing: bool = False,
        page_size: int = 20,
        max_activities: int | None = None,
        activity_type: str | None = None,
    ) -> DownloadSummary:
        if page_size < 1:
            raise ValueError("page_size must be at least 1")
        if max_activities is not None and max_activities < 1:
            raise ValueError("max_activities must be at least 1 when provided")

        start = 0
        inspected = 0
        downloaded = 0
        skipped_existing = 0
        failed = 0
        saved_paths: list[str] = []

        while max_activities is None or inspected < max_activities:
            remaining = None if max_activities is None else max_activities - inspected
            limit = page_size if remaining is None else min(page_size, remaining)
            try:
                activities = self._garmin.list_activities(
                    start=start,
                    limit=limit,
                    activity_type=activity_type,
                )
            except RateLimitExceeded:
                return DownloadSummary(
                    inspected=inspected,
                    downloaded=downloaded,
                    skipped_existing=skipped_existing,
                    failed=failed,
                    rate_limited=True,
                    saved_paths=tuple(saved_paths),
                )
            if not activities:
                break

            for activity in activities:
                if max_activities is not None and inspected >= max_activities:
                    break

                inspected += 1
                if self._storage.has_activity(activity.id):
                    skipped_existing += 1
                    self._emit("exists", activity)
                    if not all_missing:
                        return DownloadSummary(
                            inspected=inspected,
                            downloaded=downloaded,
                            skipped_existing=skipped_existing,
                            failed=failed,
                            stopped_at_existing=True,
                            saved_paths=tuple(saved_paths),
                        )
                    continue

                self._emit("download", activity)
                try:
                    content = self._garmin.download_activity(activity.id, download_format)
                    stored = self._storage.save_activity(activity, content, download_format)
                    saved_paths.append(stored.path)
                    downloaded += 1
                    self._emit("saved", activity)
                except RateLimitExceeded:
                    failed += 1
                    self._emit("rate_limited", activity)
                    return DownloadSummary(
                        inspected=inspected,
                        downloaded=downloaded,
                        skipped_existing=skipped_existing,
                        failed=failed,
                        rate_limited=True,
                        saved_paths=tuple(saved_paths),
                    )
                except Exception:
                    failed += 1
                    self._emit("failed", activity)

            if len(activities) < limit:
                break
            start += len(activities)

        return DownloadSummary(
            inspected=inspected,
            downloaded=downloaded,
            skipped_existing=skipped_existing,
            failed=failed,
            stopped_at_existing=False,
            saved_paths=tuple(saved_paths),
        )

    def _emit(self, event: str, activity: Activity) -> None:
        if self._on_progress is not None:
            self._on_progress(event, activity)
