"""Loads the known global positions of ArUco markers.

Reads the same markers.json that flutter_app/pi_server/server.py writes when
the Android app pushes a calibration. Reloading is based on the file's mtime
so edits made by the Flask server (or the app, or a human) show up on the
next localization cycle without restarting the pipeline.
"""
import json
import logging
import os

import numpy as np

logger = logging.getLogger("pipeline.marker_map")


class MarkerMap:
    def __init__(self, path):
        self.path = path
        self._positions = {}
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
            self._positions = {
                int(m["id"]): np.array([m["x"], m["y"], m["z"]], dtype=float)
                for m in raw
            }
            self._mtime = mtime
            logger.info("Reloaded marker map: %d markers", len(self._positions))
        except (OSError, ValueError, KeyError) as e:
            logger.warning("Failed to reload marker map from %s: %s", self.path, e)

    def get(self, marker_id):
        return self._positions.get(marker_id)

    def known_ids(self):
        return set(self._positions.keys())
