"""Unit tests for geometry.multilaterate's `weights` parameter.

Run with: python -m unittest test_geometry -v
"""
import unittest

import numpy as np

from geometry import multilaterate


class TestMultilaterateWeights(unittest.TestCase):

    def _corrupted_scenario(self):
        """3 anchors, one distance deliberately corrupted (simulating a bad/
        noisy marker measurement). Returns (positions, distances, guess,
        true_point)."""
        true_point = np.array([1.0, 2.0, 1.5])
        positions = [np.array([0.0, 0.0, 0.0]), np.array([5.0, 0.0, 0.0]), np.array([0.0, 0.0, 5.0])]
        distances = [float(np.linalg.norm(true_point - p)) for p in positions]
        distances[1] += 1.0  # corrupt the second measurement
        guess = np.mean(positions, axis=0)
        return positions, distances, guess, true_point

    def test_weights_none_matches_explicit_uniform_weights(self):
        """Omitting `weights` (the default) must behave identically to
        passing all-ones -- locks in backward compatibility for existing
        callers that don't know about the parameter."""
        positions, distances, guess, _ = self._corrupted_scenario()
        no_weights = multilaterate(positions, distances, guess)
        uniform_weights = multilaterate(positions, distances, guess, weights=[1.0, 1.0, 1.0])
        np.testing.assert_allclose(no_weights, uniform_weights)

    def test_low_weight_reduces_pull_from_corrupted_measurement(self):
        """Down-weighting the corrupted measurement should land closer to
        the true point than trusting all three equally."""
        positions, distances, guess, true_point = self._corrupted_scenario()

        equal = multilaterate(positions, distances, guess)
        down_weighted = multilaterate(positions, distances, guess, weights=[1.0, 0.01, 1.0])

        equal_error = float(np.linalg.norm(equal - true_point))
        weighted_error = float(np.linalg.norm(down_weighted - true_point))
        self.assertLess(weighted_error, equal_error)

    def test_weights_compose_with_huber(self):
        """weights and use_huber are independent knobs that both apply at
        once (see multilaterate's docstring) rather than one overriding the
        other. Using both together should still converge to something
        finite and clearly better than trusting the corrupted measurement
        fully (i.e. neither knob enabled) -- not asserting it beats either
        mechanism alone, since huber and a distance-prior can each already
        handle this particular scenario well on their own, and stacking
        both isn't guaranteed to strictly improve on the better of the two."""
        positions, distances, guess, true_point = self._corrupted_scenario()

        neither = multilaterate(positions, distances, guess)
        huber_and_weighted = multilaterate(positions, distances, guess, use_huber=True, huber_delta=0.3,
                                            weights=[1.0, 0.01, 1.0])

        self.assertTrue(np.all(np.isfinite(huber_and_weighted)))
        neither_error = float(np.linalg.norm(neither - true_point))
        combined_error = float(np.linalg.norm(huber_and_weighted - true_point))
        self.assertLess(combined_error, neither_error)


if __name__ == "__main__":
    unittest.main(verbosity=2)
