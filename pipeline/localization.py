"""Fuses per-marker camera detections into a single robot pose estimate.

Pure logic only -- no cv2, no sockets -- so this module and its tests never
need real cameras or images.

Strategy: exactly 3 markers (the 3 closest, by raw measured distance) are
used for a least-squares trilateration + orientation fusion. Fewer than 3
known markers seen this cycle is an explicit error, not a degraded estimate
(some earlier/other robots-in-this-family used partial 1- or 2-marker
fallbacks; this system doesn't -- see contracts.INSUFFICIENT_MARKERS_ERROR).
"""
import logging
from dataclasses import dataclass

import numpy as np

from geometry import rotation_matrix_to_euler, multilaterate, weighted_circular_mean
from contracts import LocalizationResult, INSUFFICIENT_MARKERS_ERROR

logger = logging.getLogger("pipeline.localization")

MIN_MARKERS = 3
TRILATERATION_COUNT = 3


def _v(arr, unit=""):
    return "(%.3f, %.3f, %.3f)%s" % (arr[0], arr[1], arr[2], unit)


def _rpy_deg(rpy):
    return "(roll=%.1f, pitch=%.1f, yaw=%.1f) deg" % tuple(np.degrees(rpy))


@dataclass
class _Candidate:
    marker_id: int
    marker_position: np.ndarray
    distance_m: float          # raw camera-to-marker distance (sensor-quality proxy, for selection)
    robot_distance_m: float    # marker-to-robot-center distance (for the trilateration solve)
    T_global_robot: np.ndarray


def build_candidates(detections, marker_map, camera_extrinsics):
    """One candidate per distinct known marker_id seen this cycle.

    camera_extrinsics: dict camera_name -> T_cam_robot (4x4; robot-frame
    points expressed in that camera's local frame -- i.e. the inverse of the
    camera's mounting pose on the robot).
    """
    by_marker = {}
    for det in detections:
        marker_pos = marker_map.get(det.marker_id)
        T_global_marker = marker_map.get_transform(det.marker_id)
        if marker_pos is None or T_global_marker is None:
            logger.warning(
                "[%s] detected marker %d but it's NOT in the marker map "
                "(known ids: %s) -> ignoring it",
                det.camera_name, det.marker_id, sorted(marker_map.known_ids()))
            continue

        T_cam_robot = camera_extrinsics.get(det.camera_name)
        if T_cam_robot is None:
            logger.warning("No extrinsics configured for camera %s, skipping", det.camera_name)
            continue

        # marker_position + (marker-orientation-rotated camera offset), done
        # as one matrix product: raw marker-frame point -> world (via
        # T_global_marker) -> camera -> robot.
        T_global_robot = T_global_marker @ det.T_marker_cam @ T_cam_robot

        # det.distance_m is camera-to-marker, measured from wherever that
        # specific camera is mounted -- not the robot's own center. When two
        # candidates come from different cameras with different mounting
        # offsets, feeding raw camera-to-marker distances into one
        # trilateration solve would implicitly (and wrongly) treat them as
        # measured from the same point. robot_distance_m re-derives the
        # range from the robot's own (already correctly composed) position
        # instead, so the trilateration solve is unbiased regardless of
        # which camera saw which marker.
        robot_distance_m = float(np.linalg.norm(T_global_robot[:3, 3] - marker_pos))

        candidate_rpy = rotation_matrix_to_euler(T_global_robot[:3, :3])
        logger.debug(
            "[%s] marker %d: map_pos=%s cam_dist=%.3fm robot_dist=%.3fm -> candidate robot pos=%s %s",
            det.camera_name, det.marker_id, _v(marker_pos, "m"), det.distance_m, robot_distance_m,
            _v(T_global_robot[:3, 3], "m"), _rpy_deg(candidate_rpy),
        )

        existing = by_marker.get(det.marker_id)
        if existing is None or det.distance_m < existing.distance_m:
            if existing is not None:
                logger.debug(
                    "marker %d seen by multiple cameras this cycle, keeping "
                    "the closer one (%s, %.3fm)", det.marker_id, det.camera_name, det.distance_m)
            by_marker[det.marker_id] = _Candidate(
                marker_id=det.marker_id, marker_position=marker_pos,
                distance_m=det.distance_m, robot_distance_m=robot_distance_m,
                T_global_robot=T_global_robot,
            )

    return list(by_marker.values())


def select_closest(candidates, k=TRILATERATION_COUNT):
    """The k candidates with the smallest raw measured distance_m (not
    distance to any estimated position -- that would be circular)."""
    return sorted(candidates, key=lambda c: c.distance_m)[:k]


def fuse(candidates):
    """Least-squares trilateration + orientation fusion over `candidates`
    (expected to be exactly TRILATERATION_COUNT long)."""
    marker_ids = [c.marker_id for c in candidates]
    positions = [c.marker_position for c in candidates]
    robot_distances = [c.robot_distance_m for c in candidates]
    poses = [c.T_global_robot for c in candidates]

    initial_guess = np.mean([T[:3, 3] for T in poses], axis=0)
    position = multilaterate(positions, robot_distances, initial_guess)

    ranges = np.linalg.norm(position - np.asarray(positions), axis=1)
    residual = float(np.mean(np.abs(ranges - np.asarray(robot_distances))))
    confidence = float(np.clip(0.95 - 0.5 * residual, 0.3, 0.95))

    # Weighting for orientation fusion uses raw camera-measured distance
    # (sensor-quality proxy: closer/larger-in-frame markers give sharper
    # angle estimates), not the robot-referenced range used for position.
    weights = [1.0 / max(c.distance_m, 1e-3) for c in candidates]
    rpys = [rotation_matrix_to_euler(T[:3, :3]) for T in poses]
    rpy = tuple(weighted_circular_mean([r[k] for r in rpys], weights) for k in range(3))

    logger.debug(
        "path=TRILATERATION markers=%s initial_guess=%s -> pos=%s "
        "range residual=%.3fm (measured-vs-solved distance, should be small)",
        marker_ids, _v(initial_guess, "m"), _v(position, "m"), residual,
    )

    return LocalizationResult(
        position=position, orientation=rpy, confidence=confidence,
        markers_detected=len(candidates), marker_ids=marker_ids, error=None,
    )


def estimate(detections, marker_map, camera_extrinsics,
             min_markers=MIN_MARKERS, k=TRILATERATION_COUNT):
    """Always returns a LocalizationResult -- never None, never raises.
    Insufficient markers is an expected, frequent runtime state, not an
    exceptional one; `result.error` carries the reason when it applies."""
    candidates = build_candidates(detections, marker_map, camera_extrinsics)

    if len(candidates) < min_markers:
        logger.info("Only %d known marker(s) seen this cycle (%s), need %d -> error",
                     len(candidates), [c.marker_id for c in candidates], min_markers)
        return LocalizationResult(
            position=None, orientation=None, confidence=0.0,
            markers_detected=len(candidates),
            marker_ids=[c.marker_id for c in candidates],
            error=INSUFFICIENT_MARKERS_ERROR,
        )

    result = fuse(select_closest(candidates, k))
    logger.info(
        "FUSION RESULT: n=%d ids=%s pos=%s %s conf=%.2f",
        result.markers_detected, result.marker_ids,
        _v(result.position, "m"), _rpy_deg(result.orientation), result.confidence,
    )
    return result
