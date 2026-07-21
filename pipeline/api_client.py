"""Reports localization results (success or error) to the Flask server the app polls."""
import logging

import numpy as np
import requests

logger = logging.getLogger("pipeline.api_client")


class ApiClient:
    def __init__(self, base_url, timeout=1.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def post_localization(self, result, camera_response_times=None, fps=None):
        marker_ids = [int(mid) for mid in result.marker_ids]
        camera_times = {
            name: (float(t) if t is not None else None)
            for name, t in (camera_response_times or {}).items()
        }
        fps_value = float(fps) if fps is not None else None
        if result.error is not None:
            payload = {
                "error": result.error,
                "markers_detected": int(result.markers_detected),
                "marker_ids": marker_ids,
                "camera_response_times_s": camera_times,
                "fps": fps_value,
            }
        else:
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
                "marker_ids": marker_ids,
                "camera_response_times_s": camera_times,
                "fps": fps_value,
                "error": None,
            }

        logger.debug("POST %s/api/localization payload=%s", self.base_url, payload)
        try:
            resp = requests.post(f"{self.base_url}/api/localization", json=payload, timeout=self.timeout)
            logger.debug("POST response: %s %s", resp.status_code, resp.text[:200])
        except requests.exceptions.RequestException as e:
            logger.warning("Failed to POST localization result: %s", e)
