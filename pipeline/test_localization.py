"""Unit tests for the triangulation/fusion logic, using fabricated inputs only.

No real images, cameras, or sockets anywhere in this file. Marker positions
and ArUco-detector-style outputs (MarkerDetection: marker_id, camera_name,
distance_m, and the camera's pose in the marker's local frame) are fabricated
directly. Every geometry-based test works backward from a chosen ground-truth
robot pose through the exact production composition
(T_global_robot = T_global_marker @ T_marker_cam @ T_cam_robot) to derive the
detection a real ArucoDetector would have produced, then asserts estimate()
recovers that same ground truth -- so these are genuine round-trip checks,
not hand-computed expected values that could themselves contain a mistake.

Run with: python -m unittest test_localization -v
"""
import json
import os
import tempfile
import unittest

import numpy as np

from geometry import (
    homogeneous, invert_homogeneous, extrinsic_transform,
    euler_to_rotation_matrix, CAM_CV_TO_WORLD, MARKER_RAW_TO_WORLD,
)
from contracts import MarkerDetection, INSUFFICIENT_MARKERS_ERROR
from marker_map import MarkerMap
import localization


def make_marker_map(test_case, entries):
    """entries: list of dicts {id, x, y, z, roll_deg?, pitch_deg?, yaw_deg?}.
    Writes a real markers.json-shaped temp file and loads it through the
    actual MarkerMap class (not a hand-rolled fake), so these tests exercise
    the real marker-map parsing + world-conversion logic, not a duplicate of it.
    """
    fd, path = tempfile.mkstemp(suffix=".json")
    with os.fdopen(fd, "w") as f:
        json.dump(entries, f)
    test_case.addCleanup(os.remove, path)
    return MarkerMap(path)


def identity_extrinsics(names):
    T = extrinsic_transform((0.0, 0.0, 0.0), (0.0, 0.0, 0.0))
    return {name: invert_homogeneous(T) for name in names}


def ground_truth_pose(position, rpy_deg):
    R = euler_to_rotation_matrix(*np.radians(rpy_deg))
    return homogeneous(R, np.asarray(position, dtype=float))


def fabricate_detection(marker_id, camera_name, marker_map, T_global_robot_true, camera_extrinsics):
    """Work backward through T_global_robot = T_global_marker @ T_marker_cam @ T_cam_robot
    to derive the T_marker_cam / distance_m a real ArucoDetector would have produced."""
    T_global_marker = marker_map.get_transform(marker_id)
    T_cam_robot = camera_extrinsics[camera_name]
    T_marker_cam = invert_homogeneous(T_global_marker) @ T_global_robot_true @ invert_homogeneous(T_cam_robot)
    distance = float(np.linalg.norm(T_marker_cam[:3, 3]))
    return MarkerDetection(marker_id=marker_id, camera_name=camera_name,
                            distance_m=distance, T_marker_cam=T_marker_cam)


def assert_pose_close(test_case, result, expected_position, expected_rpy_deg, pos_atol=1e-3, rot_atol=1e-3):
    test_case.assertIsNone(result.error)
    np.testing.assert_allclose(result.position, expected_position, atol=pos_atol)
    R_actual = euler_to_rotation_matrix(*result.orientation)
    R_expected = euler_to_rotation_matrix(*np.radians(expected_rpy_deg))
    np.testing.assert_allclose(R_actual, R_expected, atol=rot_atol)


class TestAxisConvention(unittest.TestCase):
    """Locks down the fix: identity orientation faces world -Z, up stays up.
    This is the test that would have caught the original basis-mismatch bug.
    """

    def test_camera_identity_faces_world_neg_z(self):
        raw_forward = np.array([0.0, 0.0, 1.0])  # OpenCV camera forward-into-scene
        np.testing.assert_allclose(CAM_CV_TO_WORLD @ raw_forward, [0, 0, -1], atol=1e-9)

    def test_camera_up_stays_up(self):
        raw_up = np.array([0.0, -1.0, 0.0])  # OpenCV camera "up" = -Y (Y is down)
        np.testing.assert_allclose(CAM_CV_TO_WORLD @ raw_up, [0, 1, 0], atol=1e-9)

    def test_marker_identity_faces_world_neg_z(self):
        raw_facing = np.array([0.0, 0.0, 1.0])  # ArUco marker's own Z = toward viewer
        np.testing.assert_allclose(MARKER_RAW_TO_WORLD @ raw_facing, [0, 0, -1], atol=1e-9)

    def test_marker_up_stays_up(self):
        raw_up = np.array([0.0, 1.0, 0.0])
        np.testing.assert_allclose(MARKER_RAW_TO_WORLD @ raw_up, [0, 1, 0], atol=1e-9)


class TestTriangulation(unittest.TestCase):

    def test_basic_three_markers(self):
        true_pos = (2.0, 0.5, -3.0)
        true_rpy_deg = (0.0, 0.0, 40.0)
        T_true = ground_truth_pose(true_pos, true_rpy_deg)

        mm = make_marker_map(self, [
            {"id": 1, "x": 0.0, "y": 0.0, "z": 0.0},
            {"id": 2, "x": 5.0, "y": 0.0, "z": 0.0},
            {"id": 3, "x": 0.0, "y": 0.0, "z": 5.0},
        ])
        extrinsics = identity_extrinsics(["FRONT"])
        detections = [fabricate_detection(mid, "FRONT", mm, T_true, extrinsics) for mid in (1, 2, 3)]

        result = localization.estimate_least_squares(detections, mm, extrinsics)
        self.assertEqual(result.markers_detected, 3)
        assert_pose_close(self, result, true_pos, true_rpy_deg)

    def test_rotated_markers(self):
        """Proves the general SE(3) composition works for arbitrary rotations
        (not simplified to 2D), per the requirement that the code not assume
        any particular marker orientation."""
        true_pos = (1.0, 0.2, 2.0)
        true_rpy_deg = (10.0, 5.0, 70.0)
        T_true = ground_truth_pose(true_pos, true_rpy_deg)

        mm = make_marker_map(self, [
            {"id": 1, "x": 0.0, "y": 0.0, "z": 0.0, "yaw_deg": 180.0},
            {"id": 2, "x": 4.0, "y": 0.0, "z": 1.0, "pitch_deg": 45.0},
            {"id": 3, "x": 0.0, "y": 0.0, "z": 4.0, "roll_deg": 180.0, "yaw_deg": -90.0},
        ])
        extrinsics = identity_extrinsics(["FRONT"])
        detections = [fabricate_detection(mid, "FRONT", mm, T_true, extrinsics) for mid in (1, 2, 3)]

        result = localization.estimate_least_squares(detections, mm, extrinsics)
        self.assertEqual(result.markers_detected, 3)
        assert_pose_close(self, result, true_pos, true_rpy_deg)

    def test_pool_cap_excludes_far_markers(self):
        true_pos = (2.0, 0.5, -3.0)
        true_rpy_deg = (0.0, 0.0, 40.0)
        T_true = ground_truth_pose(true_pos, true_rpy_deg)

        mm = make_marker_map(self, [
            {"id": 1, "x": 0.0, "y": 0.0, "z": 0.0},
            {"id": 2, "x": 5.0, "y": 0.0, "z": 0.0},
            {"id": 3, "x": 0.0, "y": 0.0, "z": 5.0},
            {"id": 99, "x": 100.0, "y": 0.0, "z": 100.0},  # decoy, also in the map
        ])
        extrinsics = identity_extrinsics(["FRONT"])
        detections = [fabricate_detection(mid, "FRONT", mm, T_true, extrinsics) for mid in (1, 2, 3)]

        # Decoy: real geometry would put it far away and consistent, but we
        # deliberately fabricate a huge distance_m so it's provably NOT one
        # of the closest max_markers, regardless of its (irrelevant) pose
        # contribution. max_markers=3 here so the pool has no room for it.
        decoy = MarkerDetection(marker_id=99, camera_name="FRONT", distance_m=999.0,
                                 T_marker_cam=homogeneous(np.eye(3), np.array([0.0, 0.0, 999.0])))
        detections.append(decoy)

        result = localization.estimate_least_squares(detections, mm, extrinsics, max_markers=3)
        self.assertEqual(result.markers_detected, 3)
        self.assertNotIn(99, result.marker_ids)
        assert_pose_close(self, result, true_pos, true_rpy_deg)

    def test_more_than_three_combines_all_triplets(self):
        """With more than 3 markers in the pool, every 3-marker combination
        is trilaterated and fused. Since these fabricated detections are all
        exactly consistent with one ground-truth pose (no measurement
        noise), every triplet independently recovers the same true pose, so
        the combined estimate should too. This exercises estimate_triplets
        specifically (the legacy multi-triplet strategy) -- estimate_least_
        squares, the current production default, doesn't form triplets at
        all, so this triplet-combination path has its own test."""
        true_pos = (2.0, 0.5, -3.0)
        true_rpy_deg = (0.0, 0.0, 40.0)
        T_true = ground_truth_pose(true_pos, true_rpy_deg)

        mm = make_marker_map(self, [
            {"id": 1, "x": 0.0, "y": 0.0, "z": 0.0},
            {"id": 2, "x": 5.0, "y": 0.0, "z": 0.0},
            {"id": 3, "x": 0.0, "y": 0.0, "z": 5.0},
            {"id": 4, "x": 5.0, "y": 0.0, "z": 5.0},
        ])
        extrinsics = identity_extrinsics(["FRONT"])
        detections = [fabricate_detection(mid, "FRONT", mm, T_true, extrinsics) for mid in (1, 2, 3, 4)]

        result = localization.estimate_triplets(detections, mm, extrinsics)  # default max_markers=7
        self.assertEqual(result.markers_detected, 4)
        assert_pose_close(self, result, true_pos, true_rpy_deg)

    def test_one_bad_marker_among_many_is_outvoted(self):
        """7 markers: 6 consistent with the true pose, 1 (id=7) fabricated
        from a wildly different pose (simulating a bad map entry or a
        misdetection). Triplets not touching marker 7 are the majority
        (C(6,3)=20 of the 35 total) and all recover the true pose exactly,
        so the median-based outlier guard in _combine_triplets should reject
        the marker-7-touching triplets rather than let them drag the fused
        result away from true_pos. estimate_triplets specifically, since
        this outlier guard lives in the triplet-combination path."""
        true_pos = (2.0, 0.5, -3.0)
        true_rpy_deg = (0.0, 0.0, 40.0)
        T_true = ground_truth_pose(true_pos, true_rpy_deg)
        T_bad = ground_truth_pose((true_pos[0] + 5.0, true_pos[1], true_pos[2] + 5.0), true_rpy_deg)

        mm = make_marker_map(self, [
            {"id": mid, "x": float(mid), "y": 0.0, "z": float(mid)} for mid in range(1, 7)
        ] + [{"id": 7, "x": 7.0, "y": 0.0, "z": 7.0}])
        extrinsics = identity_extrinsics(["FRONT"])

        detections = [fabricate_detection(mid, "FRONT", mm, T_true, extrinsics) for mid in range(1, 7)]
        detections.append(fabricate_detection(7, "FRONT", mm, T_bad, extrinsics))

        result = localization.estimate_triplets(detections, mm, extrinsics)  # default max_markers=7
        self.assertNotIn(7, result.marker_ids)
        assert_pose_close(self, result, true_pos, true_rpy_deg)

    def test_default_pool_still_excludes_far_decoy(self):
        """A decoy far outside even the default (7-marker) pool should still
        be excluded, same guarantee as test_pool_cap_excludes_far_markers
        but against the real default instead of an explicit small cap."""
        true_pos = (2.0, 0.5, -3.0)
        true_rpy_deg = (0.0, 0.0, 40.0)
        T_true = ground_truth_pose(true_pos, true_rpy_deg)

        real_ids = list(range(1, 8))  # 7 real markers -> fills the default pool on its own
        mm = make_marker_map(self, [
            {"id": mid, "x": float(mid), "y": 0.0, "z": float(mid)} for mid in real_ids
        ] + [{"id": 99, "x": 100.0, "y": 0.0, "z": 100.0}])
        extrinsics = identity_extrinsics(["FRONT"])
        detections = [fabricate_detection(mid, "FRONT", mm, T_true, extrinsics) for mid in real_ids]

        decoy = MarkerDetection(marker_id=99, camera_name="FRONT", distance_m=999.0,
                                 T_marker_cam=homogeneous(np.eye(3), np.array([0.0, 0.0, 999.0])))
        detections.append(decoy)

        result = localization.estimate_least_squares(detections, mm, extrinsics)  # default max_markers=7
        self.assertEqual(result.markers_detected, 7)
        self.assertNotIn(99, result.marker_ids)
        assert_pose_close(self, result, true_pos, true_rpy_deg)

    def test_zero_markers_is_an_error(self):
        """MIN_MARKERS=1: estimate_least_squares only needs a single visible
        marker to produce an estimate (see test_one_or_two_markers_still_
        produce_an_estimate below) -- zero is the actual floor now, not
        three."""
        mm = make_marker_map(self, [
            {"id": 1, "x": 0.0, "y": 0.0, "z": 0.0},
            {"id": 2, "x": 5.0, "y": 0.0, "z": 0.0},
        ])
        extrinsics = identity_extrinsics(["FRONT"])

        result = localization.estimate_least_squares([], mm, extrinsics)
        self.assertEqual(result.error, INSUFFICIENT_MARKERS_ERROR)
        self.assertIsNone(result.position)
        self.assertIsNone(result.orientation)
        self.assertEqual(result.markers_detected, 0)

    def test_one_or_two_markers_still_produce_an_estimate(self):
        """Unlike estimate_triplets (needs at least TRIPLET_SIZE=3 markers to
        form even one triplet), estimate_least_squares' single robust solve
        over the whole pool works down to MIN_MARKERS=1 -- with exactly-
        consistent fabricated detections, it still recovers the true pose
        even from just 1 or 2 markers."""
        true_pos = (2.0, 0.5, -3.0)
        true_rpy_deg = (0.0, 0.0, 40.0)
        T_true = ground_truth_pose(true_pos, true_rpy_deg)

        mm = make_marker_map(self, [
            {"id": 1, "x": 0.0, "y": 0.0, "z": 0.0},
            {"id": 2, "x": 5.0, "y": 0.0, "z": 0.0},
        ])
        extrinsics = identity_extrinsics(["FRONT"])

        for n in (1, 2):
            with self.subTest(n=n):
                detections = [fabricate_detection(mid, "FRONT", mm, T_true, extrinsics)
                              for mid in (1, 2)[:n]]
                result = localization.estimate_least_squares(detections, mm, extrinsics)
                self.assertIsNone(result.error)
                self.assertEqual(result.markers_detected, n)
                assert_pose_close(self, result, true_pos, true_rpy_deg)

    def test_non_identity_camera_extrinsics(self):
        """Each marker seen by a different, non-identity-mounted camera --
        proves the extrinsics composition and per-camera-name lookup are
        both correct, independent of any particular rig shape."""
        true_pos = (0.5, 0.3, 1.5)
        true_rpy_deg = (0.0, 0.0, 15.0)
        T_true = ground_truth_pose(true_pos, true_rpy_deg)

        mm = make_marker_map(self, [
            {"id": 1, "x": 0.0, "y": 0.0, "z": 0.0},
            {"id": 2, "x": 6.0, "y": 0.0, "z": 0.0},
            {"id": 3, "x": 0.0, "y": 0.0, "z": 6.0},
        ])

        extrinsics = {
            "FRONT": invert_homogeneous(extrinsic_transform((0.05, 0.0, 0.0), (0.0, 0.0, 0.0))),
            "LEFT": invert_homogeneous(extrinsic_transform((0.0, 0.0, -0.05), (0.0, 0.0, 90.0))),
            "RIGHT": invert_homogeneous(extrinsic_transform((0.0, 0.0, 0.05), (0.0, 0.0, -90.0))),
        }
        detections = [
            fabricate_detection(1, "FRONT", mm, T_true, extrinsics),
            fabricate_detection(2, "LEFT", mm, T_true, extrinsics),
            fabricate_detection(3, "RIGHT", mm, T_true, extrinsics),
        ]

        result = localization.estimate_least_squares(detections, mm, extrinsics)
        self.assertEqual(result.markers_detected, 3)
        assert_pose_close(self, result, true_pos, true_rpy_deg)

    def test_duplicate_marker_keeps_closer_camera(self):
        """Same marker seen by two cameras this cycle -- the closer
        (presumably more accurate) detection should win the dedup."""
        true_pos = (1.0, 0.0, 1.0)
        true_rpy_deg = (0.0, 0.0, 0.0)
        T_true = ground_truth_pose(true_pos, true_rpy_deg)

        mm = make_marker_map(self, [
            {"id": 1, "x": 0.0, "y": 0.0, "z": 0.0},
            {"id": 2, "x": 5.0, "y": 0.0, "z": 0.0},
            {"id": 3, "x": 0.0, "y": 0.0, "z": 5.0},
        ])
        extrinsics = identity_extrinsics(["FRONT", "LEFT"])

        good = fabricate_detection(1, "FRONT", mm, T_true, extrinsics)
        # A "bad" duplicate for marker 1 from another camera, with a larger
        # measured distance -- it should lose the dedup to `good`.
        bad = MarkerDetection(marker_id=1, camera_name="LEFT", distance_m=good.distance_m + 10.0,
                               T_marker_cam=homogeneous(np.eye(3), np.array([50.0, 50.0, 50.0])))
        detections = [good, bad,
                      fabricate_detection(2, "FRONT", mm, T_true, extrinsics),
                      fabricate_detection(3, "FRONT", mm, T_true, extrinsics)]

        result = localization.estimate_least_squares(detections, mm, extrinsics)
        assert_pose_close(self, result, true_pos, true_rpy_deg)


if __name__ == "__main__":
    unittest.main(verbosity=2)
