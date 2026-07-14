"""Reports localization results to the Flask server that the Flutter app polls."""
import logging

import numpy as np
import requests

logger = logging.getLogger("pipeline.api_client")


class ApiClient:
    def __init__(self, base_url, timeout=1.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def post_localization(self, result):
        roll, pitch, yaw = result.orientation
        payload = {
            "x": float(result.position[0]),
            "y": float(result.position[1]),
            "z": float(result.position[2]),
            "yaw": float(np.degrees(yaw)),
            "pitch": float(np.degrees(pitch)),
            "roll": float(np.degrees(roll)),
            "confidence": float(result.confidence),
            "markers_detected": int(result.markers_detected),
        }
        try:
            requests.post(f"{self.base_url}/api/localization", json=payload, timeout=self.timeout)
        except requests.exceptions.RequestException as e:
            logger.debug("Failed to POST localization result: %s", e)
