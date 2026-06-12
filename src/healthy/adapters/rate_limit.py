"""Rate limiting and 429 retry support for Garmin API calls."""

from __future__ import annotations

import random
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import TypeVar

from garminconnect import GarminConnectTooManyRequestsError

from healthy.domain import RateLimitExceeded

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class RateLimitPolicy:
    """Client-side throttling and retry settings for Garmin requests."""

    request_delay: float = 1.0
    max_retries: int = 5
    initial_backoff: float = 60.0
    max_backoff: float = 900.0
    backoff_multiplier: float = 2.0
    jitter_ratio: float = 0.15

    def __post_init__(self) -> None:
        if self.request_delay < 0:
            raise ValueError("request_delay must be non-negative")
        if self.max_retries < 0:
            raise ValueError("max_retries must be non-negative")
        if self.initial_backoff < 0:
            raise ValueError("initial_backoff must be non-negative")
        if self.max_backoff < self.initial_backoff:
            raise ValueError("max_backoff must be greater than or equal to initial_backoff")
        if self.backoff_multiplier < 1:
            raise ValueError("backoff_multiplier must be at least 1")
        if self.jitter_ratio < 0:
            raise ValueError("jitter_ratio must be non-negative")


RateLimitCallback = Callable[[float, int, int, BaseException], None]


class GarminRateLimiter:
    """Apply a polite minimum request interval and retry Garmin 429s.

    Garmin Connect is not a public bulk export API. The goal here is to avoid
    bursts, honor rate-limit responses by backing off for minutes, and stop the
    sync if the limit persists after the configured retry budget.
    """

    def __init__(
        self,
        policy: RateLimitPolicy,
        *,
        on_retry: RateLimitCallback | None = None,
        sleeper: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._policy = policy
        self._on_retry = on_retry
        self._sleep = sleeper
        self._clock = clock
        self._last_request_started_at: float | None = None

    def call(self, operation: Callable[[], T]) -> T:
        for attempt in range(self._policy.max_retries + 1):
            self._wait_for_request_slot()
            try:
                return operation()
            except GarminConnectTooManyRequestsError as exc:
                if attempt >= self._policy.max_retries:
                    raise RateLimitExceeded(
                        "Garmin rate limit persisted after "
                        f"{self._policy.max_retries} retries. Try again later, "
                        "or increase --request-delay / reduce --page-size."
                    ) from exc

                delay = self._retry_delay(attempt)
                if self._on_retry is not None:
                    self._on_retry(delay, attempt + 1, self._policy.max_retries, exc)
                self._sleep(delay)

        # The loop always returns or raises, but keeps type checkers happy.
        raise RateLimitExceeded("Garmin rate limit retry loop ended unexpectedly")

    def _wait_for_request_slot(self) -> None:
        if self._last_request_started_at is not None and self._policy.request_delay:
            elapsed = self._clock() - self._last_request_started_at
            wait_for = self._policy.request_delay - elapsed
            if wait_for > 0:
                self._sleep(wait_for)

        self._last_request_started_at = self._clock()

    def _retry_delay(self, attempt: int) -> float:
        delay = min(
            self._policy.max_backoff,
            self._policy.initial_backoff * (self._policy.backoff_multiplier**attempt),
        )
        if delay <= 0 or self._policy.jitter_ratio == 0:
            return delay

        jitter = delay * self._policy.jitter_ratio
        return max(0.0, delay + random.uniform(-jitter, jitter))
