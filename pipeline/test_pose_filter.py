"""Unit tests for pose_filter.PoseSmoother.

Run with: python -m unittest test_pose_filter -v
"""
import unittest

import numpy as np

from pose_filter import PoseSmoother


class TestPoseSmoother(unittest.TestCase):

    def test_first_update_seeds_directly(self):
        smoother = PoseSmoother()
        pos, rpy = smoother.update([1.0, 2.0, 3.0], (0.1, 0.2, 0.3), confidence=0.5)
        np.testing.assert_allclose(pos, [1.0, 2.0, 3.0])
        np.testing.assert_allclose(rpy, [0.1, 0.2, 0.3])

    def test_low_confidence_barely_moves_filter(self):
        smoother = PoseSmoother(min_alpha=0.1, max_alpha=0.9)
        smoother.update([0.0, 0.0, 0.0], (0.0, 0.0, 0.0), confidence=1.0)
        pos, _ = smoother.update([10.0, 0.0, 0.0], (0.0, 0.0, 0.0), confidence=0.0)
        # confidence=0 -> alpha = min_alpha = 0.1 -> moves 10% of the way
        np.testing.assert_allclose(pos, [1.0, 0.0, 0.0])

    def test_high_confidence_nearly_replaces_filter(self):
        smoother = PoseSmoother(min_alpha=0.1, max_alpha=0.9)
        smoother.update([0.0, 0.0, 0.0], (0.0, 0.0, 0.0), confidence=1.0)
        pos, _ = smoother.update([10.0, 0.0, 0.0], (0.0, 0.0, 0.0), confidence=1.0)
        # confidence=1 -> alpha = max_alpha = 0.9 -> moves 90% of the way
        np.testing.assert_allclose(pos, [9.0, 0.0, 0.0])

    def test_repeated_updates_converge_to_new_value(self):
        smoother = PoseSmoother(min_alpha=0.3, max_alpha=0.3)
        smoother.update([0.0, 0.0, 0.0], (0.0, 0.0, 0.0), confidence=1.0)
        pos = None
        for _ in range(100):
            pos, _ = smoother.update([5.0, -2.0, 1.0], (0.0, 0.0, 0.0), confidence=1.0)
        np.testing.assert_allclose(pos, [5.0, -2.0, 1.0], atol=1e-6)

    def test_orientation_wraps_the_short_way(self):
        """Seeded near +pi, nudged toward -pi+epsilon (the same physical
        direction, just past the wraparound) -- the filtered yaw should
        move a small step past the branch cut, not swing all the way back
        through 0."""
        smoother = PoseSmoother(min_alpha=0.5, max_alpha=0.5)
        near_pi = np.pi - 0.05
        smoother.update([0.0, 0.0, 0.0], (0.0, 0.0, near_pi), confidence=1.0)
        just_past = -np.pi + 0.05
        _, rpy = smoother.update([0.0, 0.0, 0.0], (0.0, 0.0, just_past), confidence=1.0)
        wrapped = (rpy[2] + np.pi) % (2 * np.pi) - np.pi
        # True angular gap here is 0.1 rad; blended halfway should land ~0.05
        # rad past near_pi (i.e. just past the +/-pi branch cut), not near 0.
        self.assertGreater(abs(wrapped), np.pi - 0.06)

    def test_reset_reseeds_directly(self):
        smoother = PoseSmoother()
        smoother.update([0.0, 0.0, 0.0], (0.0, 0.0, 0.0), confidence=1.0)
        smoother.reset()
        pos, rpy = smoother.update([7.0, 8.0, 9.0], (0.1, 0.1, 0.1), confidence=0.0)
        np.testing.assert_allclose(pos, [7.0, 8.0, 9.0])
        np.testing.assert_allclose(rpy, [0.1, 0.1, 0.1])


if __name__ == "__main__":
    unittest.main(verbosity=2)
