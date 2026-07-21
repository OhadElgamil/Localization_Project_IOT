"""Tracks the pipeline's own cycle rate (sample + detect + localize + post),
so the app can show how live/responsive the feed currently is.

A single instantaneous 1/dt would be too jittery to read (cycle time varies
with however many cameras answered in time this round); FpsTracker instead
keeps a short rolling window of recent tick timestamps and reports the
average rate across that window.

Pure logic, no cv2/sockets -- mirrors the rest of this module set. Takes the
current time as an explicit argument rather than calling time.monotonic()
itself, so it's deterministic to unit test.
"""
from collections import deque

DEFAULT_WINDOW_SIZE = 20


class FpsTracker:
    def __init__(self, window_size=DEFAULT_WINDOW_SIZE):
        self._window_size = window_size
        self._timestamps = deque(maxlen=window_size)

    def tick(self, now):
        """Record one completed cycle at time `now` (seconds, any
        monotonically increasing clock). Returns the current windowed FPS
        estimate, or None if there isn't yet enough history (fewer than 2
        ticks -- a rate needs at least one interval)."""
        self._timestamps.append(now)
        if len(self._timestamps) < 2:
            return None
        elapsed = self._timestamps[-1] - self._timestamps[0]
        if elapsed <= 0:
            return None
        intervals = len(self._timestamps) - 1
        return intervals / elapsed
