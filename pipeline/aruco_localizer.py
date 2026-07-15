"""ArUco marker detection + per-marker camera pose estimation (PnP)."""
import logging
import os
from dataclasses import dataclass

import cv2
import numpy as np

from geometry import homogeneous, invert_homogeneous

logger = logging.getLogger("pipeline.aruco")


@dataclass
class MarkerDetection:
    marker_id: int
    camera_name: str
    distance_m: float
    T_marker_cam: np.ndarray  # pose of the camera, expressed in the marker's local frame


def _default_intrinsics(config):
    fx = fy = config.DEFAULT_FOCAL_LENGTH
    cx, cy = config.DEFAULT_FRAME_WIDTH / 2.0, config.DEFAULT_FRAME_HEIGHT / 2.0
    camera_matrix = np.array([[fx, 0, cx], [0, fy, cy], [0, 0, 1]], dtype="double")
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

        self._intrinsics_cache = {}
        self._warned_missing_calibration = set()

    def _intrinsics_for(self, camera_name):
        if camera_name in self._intrinsics_cache:
            return self._intrinsics_cache[camera_name]

        path = os.path.join(self.config.CALIBRATION_DIR, f"{camera_name}.npz")
        if os.path.exists(path):
            data = np.load(path)
            result = (data["camera_matrix"], data["dist_coeffs"])
            logger.info("[%s] loaded intrinsics from %s", camera_name, path)
        else:
            if camera_name not in self._warned_missing_calibration:
                logger.warning(
                    "[%s] no calibration file at %s, using uncalibrated defaults "
                    "(distance/position accuracy will be poor)", camera_name, path)
                self._warned_missing_calibration.add(camera_name)
            result = _default_intrinsics(self.config)

        self._intrinsics_cache[camera_name] = result
        return result

    def detect(self, camera_name, frame):
        """Detect all markers in `frame` and return a MarkerDetection per marker."""
        if frame is None:
            return []

        camera_matrix, dist_coeffs = self._intrinsics_for(camera_name)
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
            # T_cam_marker: transform that maps a point from the marker's local
            # frame into the camera's frame -- this is exactly solvePnP's [R|t].
            R, _ = cv2.Rodrigues(rvec)
            T_cam_marker = homogeneous(R, tvec)
            # T_marker_cam: the camera's own pose, expressed in the marker's
            # local frame (i.e. "where is the camera, as seen from the marker").
            T_marker_cam = invert_homogeneous(T_cam_marker)

            rvec_deg = np.degrees(rvec.flatten())
            logger.info(
                "[%s] marker %d: distance=%.3fm tvec=(%.3f, %.3f, %.3f)m rvec=(%.1f, %.1f, %.1f)deg "
                "corner_px=%s",
                camera_name, marker_id, distance, tvec[0][0], tvec[1][0], tvec[2][0],
                rvec_deg[0], rvec_deg[1], rvec_deg[2], corners[i][0][0].round(1).tolist(),
            )

            detections.append(MarkerDetection(
                marker_id=marker_id,
                camera_name=camera_name,
                distance_m=distance,
                T_marker_cam=T_marker_cam,
            ))
        return detections
