"""Cross-cycle smoothing for localization output.

Every pipeline cycle solves an independent pose from scratch -- correct, but
real corner-pixel noise means consecutive cycles' raw positions jitter even
when the rig is stationary. PoseSmoother folds each new pose into a running
estimate with an exponential moving average, scaled by that cycle's own
`confidence` so a shaky, low-confidence read nudges the output less than a
sharp one.

Pure logic, no cv2/sockets -- mirrors the rest of this module set.
"""
import numpy as np

DEFAULT_MIN_ALPHA = 0.15
DEFAULT_MAX_ALPHA = 0.9


def _wrap_angle(delta):
    """Wrap an angle difference into (-pi, pi] so blending crosses the
    +/-pi branch cut the short way instead of the long way around."""
    return (delta + np.pi) % (2 * np.pi) - np.pi


class PoseSmoother:
    """Confidence-gated EMA over (position, orientation).

    `alpha` (the new-measurement's weight) scales linearly with confidence
    between min_alpha and max_alpha: a low-confidence cycle barely moves the
    filtered pose, a high-confidence one nearly replaces it. There's no time
    decay term -- cycle spacing is small and roughly fixed (config.
    CYCLE_SLEEP_S), so a plain confidence-scaled alpha is enough without a
    full timestamped Kalman filter.
    """

    def __init__(self, min_alpha=DEFAULT_MIN_ALPHA, max_alpha=DEFAULT_MAX_ALPHA):
        self.min_alpha = min_alpha
        self.max_alpha = max_alpha
        self._position = None
        self._orientation = None

    def reset(self):
        """Discard filter state -- the next update() seeds it directly
        instead of blending, e.g. after a known teleport/restart."""
        self._position = None
        self._orientation = None

    def update(self, position, orientation, confidence):
        """position: (3,) array-like world meters. orientation: (roll,
        pitch, yaw) radians. Returns the filtered (position, orientation)
        tuple. The first call (or the first call after reset()) seeds the
        filter directly, since there's nothing yet to blend with."""
        position = np.asarray(position, dtype=float)
        orientation = np.asarray(orientation, dtype=float)

        if self._position is None:
            self._position = position.copy()
            self._orientation = orientation.copy()
        else:
            alpha = self.min_alpha + (self.max_alpha - self.min_alpha) * np.clip(confidence, 0.0, 1.0)
            self._position = self._position + alpha * (position - self._position)
            self._orientation = self._orientation + alpha * _wrap_angle(orientation - self._orientation)

        return self._position.copy(), tuple(self._orientation)
