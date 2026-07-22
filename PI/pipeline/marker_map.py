"""Loads the known global positions (and orientations) of ArUco markers.

Reads the same markers.json that flutter_app/pi_server/server.py writes when
the Android app pushes a calibration. Reloading is based on the file's mtime
so edits made by the Flask server (or the app, or a human) show up on the
next localization cycle without restarting the pipeline.

Each entry is {id, x, y, z, roll_deg?, pitch_deg?, yaw_deg?}. The rpy fields
are optional and default to 0 (marker faces world -Z, see geometry.py) so
older markers.json files without them still load.
"""
import json
import logging
import os

import numpy as np

from geometry import euler_to_rotation_matrix, homogeneous, MARKER_RAW_TO_WORLD

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
                R_placement = euler_to_rotation_matrix(*np.radians(rpy_deg))
                # Raw ArUco-frame points -> world convention -> placed at pos.
                T_global_marker = homogeneous(R_placement, pos) @ homogeneous(MARKER_RAW_TO_WORLD, np.zeros(3))
                positions[mid] = pos
                transforms[mid] = T_global_marker
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
        transform mapping raw ArUco-frame points to world coordinates."""
        return self._transforms.get(marker_id)

    def known_ids(self):
        return set(self._positions.keys())
