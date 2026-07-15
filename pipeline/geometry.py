"""Pose/rotation math shared by the ArUco detector and the localization engine.

Conventions:
- All poses are 4x4 homogeneous transforms T = [[R, t], [0, 1]].
- T_a_b means "pose of frame b expressed in frame a": a point p_b in frame b's
  local coordinates maps to frame a via p_a = T_a_b @ p_b.
- World/robot axes are **Y-up**: X = forward, Y = up, Z = right (right-handed:
  X cross Y = Z). This matches the project's OptiTrack ground-truth frame.
- Euler angles are roll (about X/forward), pitch (about Z/right), yaw (about
  Y/up) -- i.e. yaw is the compass-heading rotation, matching the "up" axis
  above: R = Ry(yaw) @ Rz(pitch) @ Rx(roll). Units: radians in, radians out.
  A positive yaw of +90 deg rotates "forward" toward -Z (left).
"""
import numpy as np


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
    """Inverse of euler_to_rotation_matrix. Returns (roll, pitch, yaw)."""
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
    mounting offset in meters and roll/pitch/yaw in degrees."""
    roll, pitch, yaw = np.radians(rpy_deg)
    R = euler_to_rotation_matrix(roll, pitch, yaw)
    return homogeneous(R, np.asarray(translation_m, dtype=float))


def two_sphere_intersection_circle(c1: np.ndarray, r1: float, c2: np.ndarray, r2: float):
    """Intersection of two spheres (centers c1/c2, radii r1/r2) is a circle.
    Returns (circle_center, unit_normal, circle_radius). If the spheres don't
    actually intersect (bad/noisy distance measurements), the radius is
    clamped to 0 and the center is the point on the c1-c2 line consistent
    with r1, which is still a reasonable degenerate estimate.
    """
    d_vec = c2 - c1
    d = np.linalg.norm(d_vec)
    if d < 1e-9:
        return c1.copy(), np.array([1.0, 0.0, 0.0]), 0.0
    unit = d_vec / d
    a = (r1 ** 2 - r2 ** 2 + d ** 2) / (2 * d)
    h_sq = max(r1 ** 2 - a ** 2, 0.0)
    center = c1 + a * unit
    return center, unit, float(np.sqrt(h_sq))


def closest_point_on_circle(center: np.ndarray, normal: np.ndarray, radius: float, ref_point: np.ndarray) -> np.ndarray:
    if radius < 1e-9:
        return center.copy()
    v = ref_point - center
    v_proj = v - np.dot(v, normal) * normal
    norm = np.linalg.norm(v_proj)
    if norm < 1e-9:
        # ref_point sits on the circle's axis; any in-plane direction works.
        arbitrary = np.array([1.0, 0.0, 0.0]) if abs(normal[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
        direction = np.cross(normal, arbitrary)
        direction /= np.linalg.norm(direction)
    else:
        direction = v_proj / norm
    return center + radius * direction


def multilaterate(positions, distances, initial_guess, iterations=25) -> np.ndarray:
    """Gauss-Newton solve for the point whose distance to each `positions[i]`
    best matches `distances[i]` in a least-squares sense. Levenberg-damped so
    it stays stable for near-collinear/near-coplanar marker layouts.
    """
    positions = np.asarray(positions, dtype=float)
    distances = np.asarray(distances, dtype=float)
    p = np.array(initial_guess, dtype=float)
    lam = 1e-3
    for _ in range(iterations):
        diffs = p - positions
        ranges = np.linalg.norm(diffs, axis=1)
        ranges = np.where(ranges < 1e-6, 1e-6, ranges)
        residuals = ranges - distances
        J = diffs / ranges[:, None]
        JTJ = J.T @ J + lam * np.eye(3)
        JTr = J.T @ residuals
        try:
            step = np.linalg.solve(JTJ, -JTr)
        except np.linalg.LinAlgError:
            break
        p = p + step
        if np.linalg.norm(step) < 1e-6:
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
