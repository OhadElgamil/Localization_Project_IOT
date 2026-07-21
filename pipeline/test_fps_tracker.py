"""Unit tests for fps_tracker.FpsTracker.

Run with: python -m unittest test_fps_tracker -v
"""
import unittest

from fps_tracker import FpsTracker


class TestFpsTracker(unittest.TestCase):

    def test_first_tick_has_no_rate_yet(self):
        tracker = FpsTracker()
        self.assertIsNone(tracker.tick(0.0))

    def test_two_ticks_give_instantaneous_rate(self):
        tracker = FpsTracker()
        tracker.tick(0.0)
        fps = tracker.tick(0.5)
        self.assertAlmostEqual(fps, 2.0)

    def test_steady_rate_is_reported_exactly(self):
        tracker = FpsTracker(window_size=10)
        fps = None
        for i in range(10):
            fps = tracker.tick(i * 0.1)  # 10 Hz
        self.assertAlmostEqual(fps, 10.0, places=6)

    def test_window_caps_history_so_rate_tracks_recent_behavior(self):
        """Run for a long time at 10 Hz, then switch to 2 Hz -- once the
        window (5 ticks) has fully rolled over, the reported rate should
        reflect only the new, slower pace, not a blend with the old one."""
        tracker = FpsTracker(window_size=5)
        t = 0.0
        for _ in range(50):
            t += 0.1  # 10 Hz
            tracker.tick(t)
        for _ in range(5):
            t += 0.5  # 2 Hz -- 5 more ticks fully replaces the window
        fps = None
        t2 = t
        for _ in range(5):
            t2 += 0.5
            fps = tracker.tick(t2)
        self.assertAlmostEqual(fps, 2.0, places=6)

    def test_non_positive_elapsed_returns_none(self):
        tracker = FpsTracker()
        tracker.tick(5.0)
        # A non-increasing timestamp shouldn't produce a divide-by-zero or
        # negative rate.
        self.assertIsNone(tracker.tick(5.0))


if __name__ == "__main__":
    unittest.main(verbosity=2)
