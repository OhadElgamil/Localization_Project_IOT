"""Rotation/transform math shared by the ArUco detector and the localization engine.

World convention:
- Axes are X, Y (up), Z, right-handed (X cross Y = Z).
- No axis is specially labeled "forward". Instead, by convention, an object at
  identity orientation (roll=pitch=yaw=0) faces along world -Z.
- Yaw rotates about Y (up), pitch about Z, roll about X:
  R = Ry(yaw) @ Rz(pitch) @ Rx(roll).
- Poses are 4x4 homogeneous transforms T = [[R, t], [0, 1]]. T_a_b means "pose
  of frame b expressed in frame a": a point p_b in frame b's local coordinates
  maps to frame a via p_a = T_a_b @ p_b.

Two fixed correction matrices convert raw, externally-defined local axes into
this world convention. Both are the unique proper (det=+1, no mirroring)
rotation satisfying "facing -> -Z, up -> +Y, preserve right-handedness" for
their respective raw frame:

- CAM_CV_TO_WORLD: cv2.solvePnP returns rotations in OpenCV's own camera frame
  (X=right, Y=down, Z=forward-into-scene) -- intrinsic to how OpenCV's pinhole
  model works, not a choice made here. Physically: raw camera-forward (+Z_cv)
  maps to world -Z, raw camera-down (+Y_cv) maps to world -Y, and (forced by
  right-handedness) raw camera-right (+X_cv) maps to world +X. That gives the
  coordinate-conversion matrix diag(1, -1, -1) -- a 180 deg rotation about X.

- MARKER_RAW_TO_WORLD: the ArUco corner convention (also used elsewhere in
  this repo, e.g. aruco_detection.py) defines a marker's local frame as
  X=right-on-marker, Y=up-on-marker, Z=toward-whoever-is-looking-at-it (its
  facing direction). Physically: raw marker-facing (+Z_raw) maps to world -Z,
  raw marker-up (+Y_raw) maps to world +Y, and (forced by right-handedness)
  raw marker-right (+X_raw) maps to world -X. That gives diag(-1, 1, -1) -- a
  180 deg rotation about Y.

Both matrices are applied once, at the point where raw solvePnP/ArUco output
first enters the system (aruco_localizer.py and marker_map.py respectively) --
everything downstream only ever deals in the world convention.
"""
import numpy as np

CAM_CV_TO_WORLD = np.diag([1.0, -1.0, -1.0])
MARKER_RAW_TO_WORLD = np.diag([-1.0, 1.0, -1.0])


def homogeneous(R: np.ndarray, t: np.ndarray) -> np.ndarray:
    T = np.eye(4)
    T[:3, :3] = R
    T[:3, 3] = np.asarray(t).flatten()
    return T


def invert_homogeneous(T: np.ndarray) -> np.ndarray:
    R = T[:3, :3]
    t = T[:3, 3]
    T_inv = np.eye(4)
    T_inv[:3, :3] = R.T
    T_inv[:3, 3] = -R.T @ t
    return T_inv


def euler_to_rotation_matrix(roll: float, pitch: float, yaw: float) -> np.ndarray:
    """R = Ry(yaw) @ Rz(pitch) @ Rx(roll); see module docstring for axes."""
    cr, sr = np.cos(roll), np.sin(roll)
    cp, sp = np.cos(pitch), np.sin(pitch)
    cy, sy = np.cos(yaw), np.sin(yaw)
    Ry = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]])
    Rz = np.array([[cp, -sp, 0], [sp, cp, 0], [0, 0, 1]])
    Rx = np.array([[1, 0, 0], [0, cr, -sr], [0, sr, cr]])
    return Ry @ Rz @ Rx


def rotation_matrix_to_euler(R: np.ndarray):
    """Inverse of euler_to_rotation_matrix. Returns (roll, pitch, yaw) radians."""
    sp = np.clip(R[1, 0], -1.0, 1.0)
    pitch = np.arcsin(sp)
    if abs(sp) < 0.99999:
        yaw = np.arctan2(-R[2, 0], R[0, 0])
        roll = np.arctan2(-R[1, 2], R[1, 1])
    else:
        # Gimbal lock (pitch ~ +/-90 deg): roll and yaw become coupled, so we
        # fix roll = 0 and solve for yaw from the remaining coupled terms.
        roll = 0.0
        if sp > 0:
            yaw = np.arctan2(R[2, 1], R[2, 2])
        else:
            yaw = np.arctan2(-R[2, 1], R[2, 2])
    return roll, pitch, yaw


def extrinsic_transform(translation_m, rpy_deg) -> np.ndarray:
    """Build T_robot_cam (camera pose expressed in the robot body frame) from a
    mounting offset in meters and roll/pitch/yaw in degrees, world convention."""
    roll, pitch, yaw = np.radians(rpy_deg)
    R = euler_to_rotation_matrix(roll, pitch, yaw)
    return homogeneous(R, np.asarray(translation_m, dtype=float))


def multilaterate(positions, distances, initial_guess, iterations=50) -> np.ndarray:
    """Levenberg-Marquardt solve for the point whose distance to each
    `positions[i]` best matches `distances[i]` in a least-squares sense.

    Wall-mounted markers at a consistent height are a completely realistic
    layout, but that makes them coplanar -- which makes plain Gauss-Newton
    numerically unstable: the Jacobian is nearly singular in the out-of-plane
    direction near the solution (two mirror-image points on either side of
    the plane satisfy the ranges almost equally well), so a fixed, small
    damping term isn't enough to stop tiny floating-point noise from being
    amplified into a large, wrong step in that direction. Adaptive damping
    (reject any step that doesn't actually reduce the residual, increasing
    damping and retrying instead) fixes this: near a coplanar configuration
    it keeps shrinking the step until it degenerates to "stay put" rather
    than jumping to the mirror solution.
    """
    positions = np.asarray(positions, dtype=float)
    distances = np.asarray(distances, dtype=float)
    p = np.array(initial_guess, dtype=float)
    lam = 1e-2

    def residuals_at(point):
        ranges = np.linalg.norm(point - positions, axis=1)
        ranges = np.where(ranges < 1e-9, 1e-9, ranges)
        return ranges - distances

    r = residuals_at(p)
    cost = float(r @ r)

    for _ in range(iterations):
        diffs = p - positions
        ranges = np.linalg.norm(diffs, axis=1)
        ranges = np.where(ranges < 1e-9, 1e-9, ranges)
        J = diffs / ranges[:, None]
        JTJ = J.T @ J
        JTr = J.T @ r

        step = None
        for _ in range(12):  # inner loop: grow damping until a step actually helps
            try:
                candidate_step = np.linalg.solve(JTJ + lam * np.eye(3), -JTr)
            except np.linalg.LinAlgError:
                lam *= 10
                continue
            p_new = p + candidate_step
            r_new = residuals_at(p_new)
            cost_new = float(r_new @ r_new)
            if cost_new < cost:
                step = candidate_step
                p, r, cost = p_new, r_new, cost_new
                lam = max(lam / 5.0, 1e-6)
                break
            lam *= 5.0
        if step is None:
            break  # no improving step even at high damping -- converged
        if np.linalg.norm(step) < 1e-9:
            break
    return p


def weighted_circular_mean(angles, weights) -> float:
    angles = np.asarray(angles, dtype=float)
    weights = np.asarray(weights, dtype=float)
    if weights.sum() <= 0:
        weights = np.ones_like(weights)
    s = np.sum(weights * np.sin(angles))
    c = np.sum(weights * np.cos(angles))
    return float(np.arctan2(s, c))
