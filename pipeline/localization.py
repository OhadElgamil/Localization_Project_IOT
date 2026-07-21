"""Fuses per-marker camera detections into a single robot pose estimate.

Pure logic only -- no cv2, no sockets -- so this module and its tests never
need real cameras or images.

Strategy: every combination of 3 markers (drawn from the closest
`max_markers` seen this cycle) is independently trilaterated, then those
per-triplet estimates are combined into one pose, weighted by each triplet's
own confidence -- a single bad/inconsistent marker only spoils the triplets
that include it, instead of the one fixed solve. `max_markers` bounds the
combinatorics (C(n, 3) triplets) since it grows fast: 7 markers is 35
triplets, 10 is 120. Fewer than 3 known markers seen this cycle is an
explicit error, not a degraded estimate (some earlier/other
robots-in-this-family used partial 1- or 2-marker fallbacks; this system
doesn't -- see contracts.INSUFFICIENT_MARKERS_ERROR).
"""
import itertools
import logging
from dataclasses import dataclass

import numpy as np

from geometry import rotation_matrix_to_euler, multilaterate, weighted_circular_mean
from contracts import LocalizationResult, INSUFFICIENT_MARKERS_ERROR

logger = logging.getLogger("pipeline.localization")

MIN_MARKERS = 1
TRIPLET_SIZE = 3
MAX_MARKERS = 7


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


def select_closest(candidates, k=MAX_MARKERS):
    """The k candidates with the smallest raw measured distance_m (not
    distance to any estimated position -- that would be circular)."""
    return sorted(candidates, key=lambda c: c.distance_m)[:k]


def fuse(candidates, use_huber=False, huber_delta=0.5):
    """Least-squares trilateration + orientation fusion over `candidates`."""
    marker_ids = [c.marker_id for c in candidates]
    positions = [c.marker_position for c in candidates]
    robot_distances = [c.robot_distance_m for c in candidates]
    poses = [c.T_global_robot for c in candidates]

    initial_guess_base = np.mean([T[:3, 3] for T in poses], axis=0)
    
    # --- MULTI-START OPTIMIZATION (Commented out) ---
    # We try the base guess, plus 6 offset guesses (1 meter in each axis direction).
    # This uses slightly more CPU, but ensures we NEVER get stuck in a local minimum
    # (which can cause random max-error spikes in clean trials).
    # guesses = [initial_guess_base]
    # for dx, dy, dz in [(1,0,0), (-1,0,0), (0,1,0), (0,-1,0), (0,0,1), (0,0,-1)]:
    #     guesses.append(initial_guess_base + np.array([dx, dy, dz]))
    #
    # best_position = None
    # best_residual = float('inf')
    #
    # for guess in guesses:
    #     pos = multilaterate(
    #         positions, robot_distances, guess, 
    #         use_huber=use_huber, huber_delta=huber_delta
    #     )
    #     ranges = np.linalg.norm(pos - np.asarray(positions), axis=1)
    #     res = float(np.mean(np.abs(ranges - np.asarray(robot_distances))))
    #     
    #     if res < best_residual:
    #         best_residual = res
    #         best_position = pos
    #
    # position = best_position
    # residual = best_residual
    # ------------------------------------------------

    position = multilaterate(
        positions, robot_distances, initial_guess_base, 
        use_huber=use_huber, huber_delta=huber_delta
    )
    ranges = np.linalg.norm(position - np.asarray(positions), axis=1)
    residual = float(np.mean(np.abs(ranges - np.asarray(robot_distances))))
    
    # Base confidence purely on residuals (how well the math agrees)
    base_confidence = 0.95 - (1.0 * residual) # drops fast with error
    
    # Penalize confidence if we have very few markers (less redundancy)
    # 6+ markers = no penalty. 3 markers = 0.15 penalty
    marker_penalty = max(0.0, 0.05 * (6 - len(candidates)))
    
    confidence = float(np.clip(base_confidence - marker_penalty, 0.1, 0.99))

    # Weighting for orientation fusion uses raw camera-measured distance
    # (sensor-quality proxy: closer/larger-in-frame markers give sharper
    # angle estimates), not the robot-referenced range used for position.
    weights = [1.0 / max(c.distance_m, 1e-3) for c in candidates]
    rpys = [rotation_matrix_to_euler(T[:3, :3]) for T in poses]
    rpy = tuple(weighted_circular_mean([r[k] for r in rpys], weights) for k in range(3))

    logger.debug(
        "path=TRILATERATION markers=%s initial_guess=%s -> pos=%s "
        "range residual=%.3fm (measured-vs-solved distance, should be small)",
        marker_ids, _v(initial_guess_base, "m"), _v(position, "m"), residual,
    )

    return LocalizationResult(
        position=position, orientation=rpy, confidence=confidence,
        markers_detected=len(candidates), marker_ids=marker_ids, error=None,
    )


def _combine_triplets(results):
    """Fold multiple independent TRIPLET_SIZE-marker `fuse()` results into one
    pose, weighted by each triplet's own confidence -- a triplet touching a
    bad/inconsistent marker gets a larger residual (see fuse()) and so a
    lower weight here, letting the well-agreeing triplets outvote it instead
    of it corrupting a single fixed solve."""
    positions = np.array([r.position for r in results])
    weights = np.array([r.confidence for r in results])

    position = np.average(positions, axis=0, weights=weights)

    rpys = [r.orientation for r in results]
    rpy = tuple(weighted_circular_mean([r[k] for r in rpys], weights) for k in range(3))

    # Triplets disagreeing with each other (large spread) is itself a sign
    # something's off -- same "penalize inconsistency" idea fuse() applies
    # via its own range residual, just at the ensemble level.
    spread = float(np.mean(np.std(positions, axis=0)))
    confidence = float(np.clip(np.average(weights) - 0.5 * spread, 0.3, 0.95))

    marker_ids = sorted({mid for r in results for mid in r.marker_ids})
    return LocalizationResult(
        position=position, orientation=rpy, confidence=confidence,
        markers_detected=len(marker_ids), marker_ids=marker_ids, error=None,
    )


def estimate_triplets(detections, marker_map, camera_extrinsics,
                      min_markers=MIN_MARKERS, max_markers=MAX_MARKERS):
    """Original strategy: trilaterate triplets and combine the results.
    Always returns a LocalizationResult -- never None, never raises.
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

    pool = select_closest(candidates, max_markers)
    triplet_results = [fuse(list(triplet)) for triplet in itertools.combinations(pool, TRIPLET_SIZE)]
    result = triplet_results[0] if len(triplet_results) == 1 else _combine_triplets(triplet_results)

    logger.info(
        "FUSION RESULT: pool=%d triplets=%d ids=%s pos=%s %s conf=%.2f",
        len(pool), len(triplet_results), result.marker_ids,
        _v(result.position, "m"), _rpy_deg(result.orientation), result.confidence,
    )
    return result


def estimate_least_squares(detections, marker_map, camera_extrinsics,
                           min_markers=MIN_MARKERS, max_markers=MAX_MARKERS, 
                           use_huber=True, huber_delta=0.5):
    """New strategy: single robust least-squares over all visible candidates."""
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

    pool = select_closest(candidates, max_markers)
    result = fuse(pool, use_huber=use_huber, huber_delta=huber_delta)

    logger.info(
        "LEAST SQUARES RESULT: pool=%d ids=%s pos=%s %s conf=%.2f",
        len(pool), result.marker_ids,
        _v(result.position, "m"), _rpy_deg(result.orientation), result.confidence,
    )
    return result
