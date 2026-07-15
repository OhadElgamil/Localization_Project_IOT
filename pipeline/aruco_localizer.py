"""ArUco marker detection + per-marker camera pose estimation (PnP).

Camera intrinsics: if a calibration file exists for a camera
(calibration_data/<NAME>.npz, produced by calibration/calibration.py), it's
used. Otherwise the camera is assumed "perfect" (no distortion) and its
intrinsics are derived directly from the actual captured frame's shape --
focal_length = frame width in pixels, principal point = frame center --
matching the pattern already used in this repo's aruco_detection.py.
"""
import logging
import os

import cv2
import numpy as np

from geometry import homogeneous, invert_homogeneous, CAM_CV_TO_WORLD
from contracts import MarkerDetection

logger = logging.getLogger("pipeline.aruco")


def _assumed_intrinsics(frame):
    h, w = frame.shape[:2]
    focal_length = float(w)  # matches aruco_detection.py: focal_length = img.shape[1]
    cx, cy = w / 2.0, h / 2.0
    camera_matrix = np.array([[focal_length, 0, cx], [0, focal_length, cy], [0, 0, 1]], dtype="double")
    dist_coeffs = np.zeros((5, 1))
    return camera_matrix, dist_coeffs


class ArucoDetector:
    def __init__(self, config):
        self.config = config
        aruco_dict = cv2.aruco.getPredefinedDictionary(config.ARUCO_DICT)
        params = cv2.aruco.DetectorParameters()
        self._detector = cv2.aruco.ArucoDetector(aruco_dict, params)

        half = config.MARKER_SIZE_M / 2.0
        self._obj_points = np.array([
            [-half, half, 0],
            [half, half, 0],
            [half, -half, 0],
            [-half, -half, 0],
        ], dtype=np.float32)

        self._calibrated_cache = {}
        self._warned_missing_calibration = set()

    def _intrinsics_for(self, camera_name, frame):
        if camera_name in self._calibrated_cache:
            return self._calibrated_cache[camera_name]

        path = os.path.join(self.config.CALIBRATION_DIR, f"{camera_name}.npz")
        if os.path.exists(path):
            data = np.load(path)
            result = (data["camera_matrix"], data["dist_coeffs"])
            self._calibrated_cache[camera_name] = result
            logger.info("[%s] loaded intrinsics from %s", camera_name, path)
            return result

        # No calibration file: derive fresh from *this* frame's actual shape
        # every call (deliberately not cached, unlike the calibrated branch --
        # cheap to build, and sidesteps staleness if resolution ever changes).
        if camera_name not in self._warned_missing_calibration:
            logger.warning(
                "[%s] no calibration file at %s, assuming a perfect camera "
                "(focal_length = frame width, no distortion)", camera_name, path)
            self._warned_missing_calibration.add(camera_name)
        return _assumed_intrinsics(frame)

    def detect(self, camera_name, frame):
        """Detect all markers in `frame` and return a MarkerDetection per marker."""
        if frame is None:
            return []

        camera_matrix, dist_coeffs = self._intrinsics_for(camera_name, frame)
        corners, ids, _ = self._detector.detectMarkers(frame)
        if ids is None:
            logger.debug("[%s] frame %dx%d: no markers detected", camera_name, frame.shape[1], frame.shape[0])
            return []

        logger.debug("[%s] frame %dx%d: raw marker ids seen = %s",
                     camera_name, frame.shape[1], frame.shape[0], [int(i[0]) for i in ids])

        detections = []
        for i in range(len(ids)):
            marker_id = int(ids[i][0])
            success, rvec, tvec = cv2.solvePnP(
                self._obj_points, corners[i][0], camera_matrix, dist_coeffs)
            if not success:
                logger.warning("[%s] marker %d: solvePnP failed", camera_name, marker_id)
                continue

            distance = float(np.linalg.norm(tvec))

            # Raw solvePnP output is in OpenCV's camera convention (X=right,
            # Y=down, Z=forward-into-scene). Convert to world convention
            # before this leaves the function -- everything downstream only
            # ever deals in world-convention axes.
            R, _ = cv2.Rodrigues(rvec)
            T_cvcam_marker = homogeneous(R, tvec)
            T_worldcam_marker = homogeneous(CAM_CV_TO_WORLD, np.zeros(3)) @ T_cvcam_marker
            T_marker_cam = invert_homogeneous(T_worldcam_marker)

            logger.info(
                "[%s] marker %d: distance=%.3fm raw_tvec=(%.3f, %.3f, %.3f)m",
                camera_name, marker_id, distance, tvec[0][0], tvec[1][0], tvec[2][0],
            )

            detections.append(MarkerDetection(
                marker_id=marker_id,
                camera_name=camera_name,
                distance_m=distance,
                T_marker_cam=T_marker_cam,
            ))
        return detections
