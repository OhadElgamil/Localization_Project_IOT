"""Loads the known global positions (and orientations) of ArUco markers.

Reads the same markers.json that flutter_app/pi_server/server.py writes when
the Android app pushes a calibration. Reloading is based on the file's mtime
so edits made by the Flask server (or the app, or a human) show up on the
next localization cycle without restarting the pipeline.

Each entry is {id, x, y, z, roll_deg?, pitch_deg?, yaw_deg?}. The rpy fields
are optional and default to 0 (identity orientation) so older markers.json
files without them still load -- but any marker that isn't mounted facing
"straight forward" in the world frame needs its real orientation set, or its
pose contribution to the fused result will be wrong. See geometry.py's module
docstring for the axis/angle convention (Y-up, degrees).
"""
import json
import logging
import os

import numpy as np

from geometry import euler_to_rotation_matrix, homogeneous

logger = logging.getLogger("pipeline.marker_map")


class MarkerMap:
    def __init__(self, path):
        self.path = path
        self._positions = {}
        self._transforms = {}
        self._mtime = None
        self.reload()

    def reload(self):
        try:
            mtime = os.path.getmtime(self.path)
        except OSError:
            if self._positions:
                logger.warning("Marker map file missing at %s, keeping last known map", self.path)
            return

        if mtime == self._mtime:
            return

        try:
            with open(self.path, "r") as f:
                raw = json.load(f)
            positions = {}
            transforms = {}
            for m in raw:
                mid = int(m["id"])
                pos = np.array([m["x"], m["y"], m["z"]], dtype=float)
                rpy_deg = (
                    float(m.get("roll_deg", 0.0)),
                    float(m.get("pitch_deg", 0.0)),
                    float(m.get("yaw_deg", 0.0)),
                )
                R = euler_to_rotation_matrix(*np.radians(rpy_deg))
                positions[mid] = pos
                transforms[mid] = homogeneous(R, pos)
            self._positions = positions
            self._transforms = transforms
            self._mtime = mtime
            logger.info("Reloaded marker map from %s: %d markers", self.path, len(self._positions))
            for mid in sorted(self._positions):
                pos = self._positions[mid]
                logger.info("  marker %s: pos=(x=%.3f, y=%.3f, z=%.3f)m", mid, *pos)
        except (OSError, ValueError, KeyError) as e:
            logger.warning("Failed to reload marker map from %s: %s", self.path, e)

    def get(self, marker_id):
        """Marker's global (x, y, z) position only."""
        return self._positions.get(marker_id)

    def get_transform(self, marker_id):
        """Marker's full global pose (position + orientation) as a 4x4
        transform. Falls back to identity rotation at that marker's position
        if the marker or its orientation isn't known."""
        T = self._transforms.get(marker_id)
        if T is not None:
            return T
        pos = self._positions.get(marker_id)
        return homogeneous(np.eye(3), pos) if pos is not None else None

    def known_ids(self):
        return set(self._positions.keys())
