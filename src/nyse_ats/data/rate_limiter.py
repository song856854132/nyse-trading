"""Thread-safe sliding-window rate limiter.

Used by all data adapters to respect upstream API rate limits:
- FinMind: 30 calls / minute
- EDGAR: 10 calls / second
"""

from __future__ import annotations

import threading
import time
from collections import deque


class SlidingWindowRateLimiter:
    """Sliding-window rate limiter with blocking and non-blocking acquire.

    Parameters
    ----------
    max_requests : int
        Maximum number of requests allowed within *window_seconds*.
    window_seconds : float
        Length of the sliding window in seconds.
    """

    def __init__(self, max_requests: int, window_seconds: float) -> None:
        if max_requests <= 0:
            raise ValueError("max_requests must be positive")
        if window_seconds <= 0:
            raise ValueError("window_seconds must be positive")
        self._max_requests = max_requests
        self._window_seconds = window_seconds
        self._timestamps: deque[float] = deque()
        self._lock = threading.Lock()

    @property
    def max_requests(self) -> int:
        return self._max_requests

    @property
    def window_seconds(self) -> float:
        return self._window_seconds

    def _purge_expired(self, now: float) -> None:
        """Remove timestamps older than the sliding window."""
        cutoff = now - self._window_seconds
        while self._timestamps and self._timestamps[0] <= cutoff:
            self._timestamps.popleft()

    def acquire(self) -> None:
        """Block until a rate-limit slot is available, then record the call."""
        while True:
            with self._lock:
                now = time.monotonic()
                self._purge_expired(now)
                if len(self._timestamps) < self._max_requests:
                    self._timestamps.append(now)
                    return
                # Calculate how long to wait for the oldest entry to expire
                wait_time = self._timestamps[0] + self._window_seconds - now
            # Sleep outside the lock so other threads can proceed
            if wait_time > 0:
                time.sleep(wait_time)

    def try_acquire(self) -> bool:
        """Non-blocking acquire. Returns True if a slot was available."""
        with self._lock:
            now = time.monotonic()
            self._purge_expired(now)
            if len(self._timestamps) < self._max_requests:
                self._timestamps.append(now)
                return True
            return False
