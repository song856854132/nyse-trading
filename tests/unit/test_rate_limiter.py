"""Tests for nyse_ats.data.rate_limiter — thread-safe sliding window.

Validates:
- Single request passes immediately
- Rate limit blocks after max_requests
- Sliding window releases after period expires
- Thread safety under concurrent acquire
- try_acquire non-blocking behavior
"""

from __future__ import annotations

import threading
import time

import pytest

from nyse_ats.data.rate_limiter import SlidingWindowRateLimiter


class TestSlidingWindowInit:
    """Constructor validation."""

    def test_valid_construction(self) -> None:
        rl = SlidingWindowRateLimiter(max_requests=10, window_seconds=1.0)
        assert rl.max_requests == 10
        assert rl.window_seconds == 1.0

    def test_rejects_zero_max_requests(self) -> None:
        with pytest.raises(ValueError, match="max_requests"):
            SlidingWindowRateLimiter(max_requests=0, window_seconds=1.0)

    def test_rejects_negative_window(self) -> None:
        with pytest.raises(ValueError, match="window_seconds"):
            SlidingWindowRateLimiter(max_requests=5, window_seconds=-1.0)


class TestAcquire:
    """Blocking acquire behavior."""

    def test_single_request_passes_immediately(self) -> None:
        rl = SlidingWindowRateLimiter(max_requests=5, window_seconds=60.0)
        start = time.monotonic()
        rl.acquire()
        elapsed = time.monotonic() - start
        # Should return in well under 100ms
        assert elapsed < 0.1

    def test_max_requests_pass_without_blocking(self) -> None:
        rl = SlidingWindowRateLimiter(max_requests=5, window_seconds=60.0)
        start = time.monotonic()
        for _ in range(5):
            rl.acquire()
        elapsed = time.monotonic() - start
        assert elapsed < 0.1

    def test_blocks_after_max_requests(self) -> None:
        """After max_requests, the next acquire must block until window slides."""
        rl = SlidingWindowRateLimiter(max_requests=3, window_seconds=0.2)

        for _ in range(3):
            rl.acquire()

        start = time.monotonic()
        rl.acquire()  # This should block ~0.2s
        elapsed = time.monotonic() - start
        # Should have waited approximately window_seconds
        assert elapsed >= 0.15, f"Expected blocking, got {elapsed:.3f}s"

    def test_sliding_window_releases_over_time(self) -> None:
        """After the window period, slots become available again."""
        rl = SlidingWindowRateLimiter(max_requests=2, window_seconds=0.15)

        rl.acquire()
        rl.acquire()
        # Window is full

        time.sleep(0.2)  # Wait for window to expire

        start = time.monotonic()
        rl.acquire()
        elapsed = time.monotonic() - start
        # Should pass immediately since old entries expired
        assert elapsed < 0.1


class TestTryAcquire:
    """Non-blocking try_acquire behavior."""

    def test_returns_true_when_available(self) -> None:
        rl = SlidingWindowRateLimiter(max_requests=5, window_seconds=60.0)
        assert rl.try_acquire() is True

    def test_returns_false_when_exhausted(self) -> None:
        rl = SlidingWindowRateLimiter(max_requests=2, window_seconds=60.0)
        assert rl.try_acquire() is True
        assert rl.try_acquire() is True
        assert rl.try_acquire() is False

    def test_does_not_block(self) -> None:
        rl = SlidingWindowRateLimiter(max_requests=1, window_seconds=60.0)
        rl.try_acquire()

        start = time.monotonic()
        result = rl.try_acquire()
        elapsed = time.monotonic() - start

        assert result is False
        assert elapsed < 0.05  # Must return immediately


class TestThreadSafety:
    """Concurrent access to the rate limiter."""

    def test_concurrent_acquire_respects_limit(self) -> None:
        """Multiple threads should not exceed max_requests within the window."""
        rl = SlidingWindowRateLimiter(max_requests=5, window_seconds=1.0)
        results: list[float] = []
        lock = threading.Lock()

        def worker() -> None:
            rl.acquire()
            with lock:
                results.append(time.monotonic())

        threads = [threading.Thread(target=worker) for _ in range(5)]
        start = time.monotonic()
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        # All 5 should have completed within the window
        assert len(results) == 5
        # All timestamps should be close to start (within window)
        for ts in results:
            assert ts - start < 1.0

    def test_concurrent_overflow_causes_blocking(self) -> None:
        """7 threads competing for 3 slots should cause 4 to block."""
        rl = SlidingWindowRateLimiter(max_requests=3, window_seconds=0.3)
        completion_times: list[float] = []
        lock = threading.Lock()
        start_time = time.monotonic()

        def worker() -> None:
            rl.acquire()
            with lock:
                completion_times.append(time.monotonic() - start_time)

        threads = [threading.Thread(target=worker) for _ in range(7)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        assert len(completion_times) == 7
        # At least some completions should be delayed
        completion_times.sort()
        # First 3 should be fast, later ones should be delayed
        assert completion_times[0] < 0.15
        assert completion_times[-1] >= 0.2
