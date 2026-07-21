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
        # Default is CORNER_REFINE_NONE (raw, integer-pixel corners). Sub-pixel
        # refinement tightens corner localization, which feeds directly into
        # solvePnP's pose accuracy -- this is close to a free accuracy win.
        params.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX
        params.cornerRefinementWinSize = 5
        params.cornerRefinementMaxIterations = 30
        params.cornerRefinementMinAccuracy = 0.05
        # Default (0.03) drops any marker under ~3% of the frame's perimeter,
        # i.e. markers that are far away or at a shallow angle -- silently
        # shrinking the usable marker count every cycle. Triangulation only
        # benefits from more markers, and MAX_TRIANGULATION_MARKERS already
        # bounds the triplet combinatorics, so let smaller/farther ones through.
        params.minMarkerPerimeterRate = 0.02
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
            raw_matrix, dist_coeffs, img_shape = self._calibrated_cache[camera_name]
        else:
            cam_id = "PI" if camera_name == "PICAM" else camera_name
            path = os.path.join(self.config.CALIBRATION_DIR, f"calibration_data_{cam_id}.npz")
            if os.path.exists(path):
                data = np.load(path)
                raw_matrix = data["camera_matrix"]
                dist_coeffs = data["dist_coeffs"]
                img_shape = data["img_shape"] if "img_shape" in data else None
                self._calibrated_cache[camera_name] = (raw_matrix, dist_coeffs, img_shape)
                logger.info("[%s] loaded intrinsics from %s", camera_name, path)
            else:
                raw_matrix = None

        if raw_matrix is not None:
            camera_matrix = np.copy(raw_matrix)
            if img_shape is not None:
                h, w = frame.shape[:2]
                if img_shape[0] != w or img_shape[1] != h:
                    logger.warning(
                        "[%s] Frame size %dx%d doesn't match calibration size %dx%d. Scaling intrinsics...",
                        camera_name, w, h, img_shape[0], img_shape[1]
                    )
                    scale_x = w / img_shape[0]
                    scale_y = h / img_shape[1]
                    camera_matrix[0, 0] *= scale_x  # fx
                    camera_matrix[0, 2] *= scale_x  # cx
                    camera_matrix[1, 1] *= scale_y  # fy
                    camera_matrix[1, 2] *= scale_y  # cy
            return camera_matrix, dist_coeffs

        # No calibration file: derive fresh from *this* frame's actual shape
        # every call (deliberately not cached, unlike the calibrated branch --
        # cheap to build, and sidesteps staleness if resolution ever changes).
        if camera_name not in self._warned_missing_calibration:
            logger.warning(
                "[%s] no calibration file at %s, assuming a perfect camera "
                "(focal_length = frame width, no distortion)", camera_name, path)
            self._warned_missing_calibration.add(camera_name)
        return _assumed_intrinsics(frame)

    def _solve_marker_pose(self, image_points, camera_matrix, dist_coeffs):
        """Solve one marker's pose with IPPE_SQUARE -- the solver built for
        flat 4-point square markers, instead of the generic iterative solver
        cv2.solvePnP defaults to. A planar square is inherently ambiguous at
        shallow viewing angles (two distinct tilts can reproject almost
        equally well); solvePnPGeneric returns every candidate plus each
        one's reprojection error, so the genuinely better solution can be
        picked instead of silently trusting whichever one a single-solution
        API happens to return.
        """
        try:
            count, rvecs, tvecs, errors = cv2.solvePnPGeneric(
                self._obj_points, image_points, camera_matrix, dist_coeffs,
                flags=cv2.SOLVEPNP_IPPE_SQUARE)
        except cv2.error:
            count = 0
        if count:
            best = int(np.argmin(errors))
            return rvecs[best], tvecs[best]

        # Fallback for degenerate corner configurations IPPE_SQUARE rejects outright.
        success, rvec, tvec = cv2.solvePnP(image_points=image_points, objectPoints=self._obj_points,
                                            cameraMatrix=camera_matrix, distCoeffs=dist_coeffs)
        return (rvec, tvec) if success else (None, None)

    def detect(self, camera_name, frame):
        """Detect all markers in `frame` and return a MarkerDetection per marker."""
        if frame is None:
            return []

        camera_matrix, dist_coeffs = self._intrinsics_for(camera_name, frame)
        corners, ids, _ = self._detector.detectMarkers(frame)
        if ids is None:
            logger.debug("[%s] frame %dx%d: no markers detected", camera_name, frame.shape[1], frame.shape[0])
            return []
        # Older cv2 returns ids shaped (N, 1); newer builds (e.g.
        # opencv-contrib-python 5.x) return a flat (N,) array. Normalize once
        # here so indexing below doesn't care which one we got.
        ids = np.asarray(ids).reshape(-1)

        logger.debug("[%s] frame %dx%d: raw marker ids seen = %s",
                     camera_name, frame.shape[1], frame.shape[0], [int(i) for i in ids])

        detections = []
        for i in range(len(ids)):
            marker_id = int(ids[i])
            rvec, tvec = self._solve_marker_pose(corners[i][0], camera_matrix, dist_coeffs)
            if rvec is None:
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
