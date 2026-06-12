"""Garmin Connect adapter."""

from __future__ import annotations

from getpass import getpass
from pathlib import Path
from typing import Any, Callable

from garminconnect import Garmin

from healthy.adapters.rate_limit import GarminRateLimiter, RateLimitCallback, RateLimitPolicy
from healthy.domain import Activity, DownloadFormat


class GarminConnectActivityClient:
    """Adapter around the ``garminconnect`` package."""

    def __init__(self, api: Garmin, rate_limiter: GarminRateLimiter) -> None:
        self._api = api
        self._rate_limiter = rate_limiter

    @classmethod
    def login(
        cls,
        *,
        tokenstore: Path,
        email: str | None = None,
        password: str | None = None,
        prompt_mfa: Callable[[], str] | None = None,
        is_cn: bool = False,
        rate_limit_policy: RateLimitPolicy | None = None,
        on_rate_limit_retry: RateLimitCallback | None = None,
    ) -> "GarminConnectActivityClient":
        tokenstore = tokenstore.expanduser()
        tokenstore.mkdir(parents=True, exist_ok=True)
        api = Garmin(
            email=email,
            password=password,
            is_cn=is_cn,
            prompt_mfa=prompt_mfa or _default_mfa_prompt,
        )
        api.login(str(tokenstore))
        return cls(
            api,
            GarminRateLimiter(
                rate_limit_policy or RateLimitPolicy(),
                on_retry=on_rate_limit_retry,
            ),
        )

    def list_activities(
        self,
        *,
        start: int,
        limit: int,
        activity_type: str | None = None,
    ) -> list[Activity]:
        payload = self._rate_limiter.call(
            lambda: self._api.get_activities(
                start=start,
                limit=limit,
                activitytype=activity_type,
            )
        )
        return [Activity.from_garmin(item) for item in _activity_items(payload)]

    def download_activity(self, activity_id: str, download_format: DownloadFormat) -> bytes:
        garmin_format = _to_garmin_download_format(self._api, download_format)
        return self._rate_limiter.call(
            lambda: self._api.download_activity(activity_id, dl_fmt=garmin_format)
        )


def _to_garmin_download_format(api: Garmin, download_format: DownloadFormat) -> Any:
    return {
        DownloadFormat.ORIGINAL: api.ActivityDownloadFormat.ORIGINAL,
        DownloadFormat.GPX: api.ActivityDownloadFormat.GPX,
        DownloadFormat.TCX: api.ActivityDownloadFormat.TCX,
        DownloadFormat.KML: api.ActivityDownloadFormat.KML,
        DownloadFormat.CSV: api.ActivityDownloadFormat.CSV,
    }[download_format]


def _activity_items(payload: dict[str, Any] | list[Any]) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]

    for key in ("activities", "activityList", "results", "data"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]

    return []


def _default_mfa_prompt() -> str:
    return getpass("Garmin MFA code: ")
