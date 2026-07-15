"""Fuses per-marker camera detections into a single robot pose estimate.

Strategy depends on how many *distinct* known markers were seen this cycle:
  1 marker  -> direct pose: solvePnP already gives full translation +
               rotation of the camera relative to the marker, which (once
               chained through the marker's known global position and the
               camera's mounting extrinsics) is a complete 6DOF robot pose.
               No triangulation is possible with one marker, so this is the
               PnP pose as-is.
  2 markers -> the two known distances constrain the robot to a circle (the
               intersection of two spheres centered on the markers). We pick
               the point on that circle closest to the orientation-derived
               pose estimate (the average of the two single-marker PnP
               poses), i.e. distance gives the circle, orientation resolves
               the remaining ambiguity along it ("half triangulation").
  3+ markers -> full multilateration: least-squares solve for the position
               whose distance to every marker matches the measured range,
               seeded from the PnP-pose average. Orientation is the
               inverse-distance-weighted circular mean of the individual
               PnP-derived orientations.
"""
import logging
from dataclasses import dataclass

import numpy as np

from geometry import (
    rotation_matrix_to_euler,
    two_sphere_intersection_circle,
    closest_point_on_circle,
    multilaterate,
    weighted_circular_mean,
)

logger = logging.getLogger("pipeline.localization")


def _v(arr, unit=""):
    """Compact, fixed-precision formatting for a 3-vector, for log lines."""
    return "(%.3f, %.3f, %.3f)%s" % (arr[0], arr[1], arr[2], unit)


def _rpy_deg(rpy):
    return "(roll=%.1f, pitch=%.1f, yaw=%.1f) deg" % tuple(np.degrees(rpy))


@dataclass
class LocalizationResult:
    position: np.ndarray       # (x, y, z) in the global/marker-map frame
    orientation: tuple         # (roll, pitch, yaw) radians
    confidence: float          # 0..1
    markers_detected: int
    marker_ids: list


class LocalizationEngine:
    def __init__(self, config):
        self.config = config

    def estimate(self, detections, marker_map):
        """detections: list of aruco_localizer.MarkerDetection from this cycle."""
        candidates = self._to_robot_candidates(detections, marker_map)
        if not candidates:
            logger.debug("No usable (known-marker) detections this cycle -> no result")
            return None

        n = len(candidates)
        logger.debug("Fusing %d known-marker candidate(s): ids=%s",
                     n, [c[0] for c in candidates])
        if n == 1:
            result = self._from_single(candidates)
        elif n == 2:
            result = self._from_pair(candidates)
        else:
            result = self._from_many(candidates)

        logger.info(
            "FUSION RESULT: n=%d ids=%s pos=%s %s conf=%.2f",
            result.markers_detected, result.marker_ids,
            _v(result.position, "m"), _rpy_deg(result.orientation), result.confidence,
        )
        return result

    # -- Build one robot-pose candidate per known marker seen this cycle --------
    def _to_robot_candidates(self, detections, marker_map):
        by_marker = {}
        for det in detections:
            marker_pos = marker_map.get(det.marker_id)
            if marker_pos is None:
                logger.warning(
                    "[%s] detected marker %d but it's NOT in the marker map "
                    "(known ids: %s) -> ignoring it",
                    det.camera_name, det.marker_id, sorted(marker_map.known_ids()))
                continue

            # T_global_marker carries the marker's own orientation (from
            # marker_map, defaulting to identity if a marker has no
            # roll/pitch/yaw set) as well as its position, so this correctly
            # rotates the camera's marker-local pose into the global frame
            # instead of just translating it -- required whenever markers
            # aren't all mounted facing the exact same way.
            T_global_marker = marker_map.get_transform(det.marker_id)
            T_global_cam = T_global_marker @ det.T_marker_cam

            T_robot_cam_inv = self.config.T_CAM_ROBOT.get(det.camera_name)
            if T_robot_cam_inv is None:
                logger.warning("No extrinsics configured for camera %s, skipping", det.camera_name)
                continue
            T_global_robot = T_global_cam @ T_robot_cam_inv

            candidate_rpy = rotation_matrix_to_euler(T_global_robot[:3, :3])
            logger.debug(
                "[%s] marker %d: map_pos=%s dist=%.3fm -> candidate robot pos=%s %s",
                det.camera_name, det.marker_id, _v(marker_pos, "m"), det.distance_m,
                _v(T_global_robot[:3, 3], "m"), _rpy_deg(candidate_rpy),
            )

            # If the same marker is seen by more than one camera this cycle,
            # keep whichever detection is closer (larger-in-frame => more
            # accurate pose estimate).
            existing = by_marker.get(det.marker_id)
            if existing is None or det.distance_m < existing[1]:
                if existing is not None:
                    logger.debug(
                        "marker %d seen by multiple cameras this cycle, keeping "
                        "the closer one (%s, %.3fm)", det.marker_id, det.camera_name, det.distance_m)
                by_marker[det.marker_id] = (T_global_robot, det.distance_m, marker_pos)

        return list(by_marker.items())  # [(marker_id, (T, distance, marker_pos)), ...]

    def _from_single(self, candidates):
        marker_id, (T, distance, marker_pos) = candidates[0]
        rpy = rotation_matrix_to_euler(T[:3, :3])
        confidence = float(np.clip(0.85 - 0.03 * distance, 0.2, 0.85))
        logger.debug(
            "path=SINGLE marker=%d marker_map_pos=%s distance=%.3fm -> pos=%s",
            marker_id, _v(marker_pos, "m"), distance, _v(T[:3, 3], "m"),
        )
        return LocalizationResult(
            position=T[:3, 3], orientation=rpy, confidence=confidence,
            markers_detected=1, marker_ids=[marker_id],
        )

    def _from_pair(self, candidates):
        (id1, (T1, d1, p1)), (id2, (T2, d2, p2)) = candidates
        ref_point = (T1[:3, 3] + T2[:3, 3]) / 2.0

        center, normal, radius = two_sphere_intersection_circle(p1, d1, p2, d2)
        position = closest_point_on_circle(center, normal, radius, ref_point)

        weights = [1.0 / max(d1, 1e-3), 1.0 / max(d2, 1e-3)]
        rpy1 = rotation_matrix_to_euler(T1[:3, :3])
        rpy2 = rotation_matrix_to_euler(T2[:3, :3])
        rpy = tuple(
            weighted_circular_mean([rpy1[k], rpy2[k]], weights) for k in range(3)
        )

        pose_disagreement = float(np.linalg.norm(T1[:3, 3] - T2[:3, 3]))
        logger.debug(
            "path=PAIR marker%d(pos=%s d=%.3fm)->pos=%s marker%d(pos=%s d=%.3fm)->pos=%s "
            "| independent single-marker pose disagreement=%.3fm (should be ~0 if geometry/units "
            "are consistent) | sphere-intersection circle center=%s radius=%.3fm ref_point=%s "
            "-> chosen pos=%s",
            id1, _v(p1, "m"), d1, _v(T1[:3, 3], "m"),
            id2, _v(p2, "m"), d2, _v(T2[:3, 3], "m"),
            pose_disagreement,
            _v(center, "m"), radius, _v(ref_point, "m"), _v(position, "m"),
        )
        if pose_disagreement > 0.5:
            logger.warning(
                "Markers %d and %d disagree by %.2fm on where the camera is when computed "
                "independently. If OptiTrack ground truth doesn't match either estimate, check "
                "MARKER_SIZE_M, each marker's position AND roll/pitch/yaw in the marker map, and "
                "the camera extrinsics in config.py.",
                id1, id2, pose_disagreement,
            )

        confidence = 0.6
        return LocalizationResult(
            position=position, orientation=rpy, confidence=confidence,
            markers_detected=2, marker_ids=[id1, id2],
        )

    def _from_many(self, candidates):
        marker_ids = [c[0] for c in candidates]
        positions = [c[1][2] for c in candidates]
        distances = [c[1][1] for c in candidates]
        poses = [c[1][0] for c in candidates]

        initial_guess = np.mean([T[:3, 3] for T in poses], axis=0)
        position = multilaterate(positions, distances, initial_guess)

        # Fit residual as a rough confidence signal: how well does the solved
        # point actually match the measured ranges?
        ranges = np.linalg.norm(position - np.asarray(positions), axis=1)
        residual = float(np.mean(np.abs(ranges - np.asarray(distances))))
        confidence = float(np.clip(0.95 - 0.5 * residual, 0.3, 0.95))

        weights = [1.0 / max(d, 1e-3) for d in distances]
        rpys = [rotation_matrix_to_euler(T[:3, :3]) for T in poses]
        rpy = tuple(
            weighted_circular_mean([r[k] for r in rpys], weights) for k in range(3)
        )

        logger.debug(
            "path=MULTILATERATION markers=%s initial_guess=%s -> pos=%s "
            "per-marker range residual=%.3fm (measured-vs-solved distance, should be small)",
            marker_ids, _v(initial_guess, "m"), _v(position, "m"), residual,
        )

        return LocalizationResult(
            position=position, orientation=rpy, confidence=confidence,
            markers_detected=len(candidates), marker_ids=marker_ids,
        )
