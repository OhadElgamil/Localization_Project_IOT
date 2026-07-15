"""Central configuration for the Pi-side localization pipeline.

Values marked TODO are placeholders — measure your actual rig and fill them
in before trusting the output. Everything else has a working default.
"""
import os
import cv2
from geometry import extrinsic_transform, invert_homogeneous

PIPELINE_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(PIPELINE_DIR)

# ---------------------------------------------------------------------------
# Network
# ---------------------------------------------------------------------------
# Must match `pi_port` hardcoded in ESP32/send_pictures_on_managers_command.ino.
# Changing this requires reflashing every camera, so leave it alone unless you
# also update the firmware.
CAMERA_TCP_HOST = "0.0.0.0"
CAMERA_TCP_PORT = 5000

# The Flask REST API used by the Flutter app (flutter_app/pi_server/server.py).
# It used to also default to port 5000, which collided with the camera TCP
# server above, so it now runs on 5001 (see that file + the Flutter app's
# ConnectionProvider default).
API_BASE_URL = "http://127.0.0.1:5001"

SNAP_TIMEOUT_S = 6.0       # UXGA (1600x1200) JPEGs are large; give the round trip room
CYCLE_SLEEP_S = 0.05       # gap between sampling cycles

# "DEBUG" logs every raw detection, distance, candidate pose, and POST
# payload -- verbose but exactly what you want while diagnosing bad output.
# Turn down to "INFO" for quieter day-to-day running once things check out.
LOG_LEVEL = "DEBUG"

# ---------------------------------------------------------------------------
# Marker map (shared with the Flutter app via the filesystem)
# ---------------------------------------------------------------------------
# The Android app POSTs marker positions to the Flask server, which writes
# this exact file. The pipeline reads it directly (no HTTP dependency), so
# it keeps working even if the Flask server isn't running.
MARKERS_FILE = os.path.join(REPO_ROOT, "flutter_app", "pi_server", "markers.json")

# ---------------------------------------------------------------------------
# ArUco / camera intrinsics
# ---------------------------------------------------------------------------
ARUCO_DICT = cv2.aruco.DICT_4X4_1000
MARKER_SIZE_M = 0.175  # TODO: must match the physical markers on the wall

# Per-camera calibration produced by calibration/calibration.py
# (np.savez with camera_matrix + dist_coeffs). Filename must be the upper-case
# camera name, e.g. calibration_data/FRONT.npz.
CALIBRATION_DIR = os.path.join(PIPELINE_DIR, "calibration_data")

# Fallback intrinsics used when no calibration file exists for a camera yet.
# Matches the UXGA (1600x1200) frame size configured in
# ESP_EYE/send_pictures_on_command/send_pictures_on_command.ino.
DEFAULT_FRAME_WIDTH = 1600
DEFAULT_FRAME_HEIGHT = 1200
DEFAULT_FOCAL_LENGTH = 1600.0

PICAM_WIDTH = 800
PICAM_HEIGHT = 600

# ---------------------------------------------------------------------------
# Camera extrinsics: where each camera is mounted relative to the robot's
# body-frame origin. This is Y-up (see geometry.py's module docstring):
# translation_m = (x, y, z) = forward/up/right in meters, rpy_deg = (roll,
# pitch, yaw) in degrees, yaw measured about the up (Y) axis, positive =
# counter-clockwise from the robot's forward axis (i.e. toward the left).
#
# Rig: a cube with one camera centered on each of 4 side faces, all at the
# same height as the reference point (the cube's center) -- so every camera's
# Y (up) offset is 0. FRONT/LEFT/RIGHT are named relative to PICAM, which is
# mounted on the REAR face -- so PICAM sits half a side-length *behind*
# center, facing backward (yaw 180 deg), not at the origin facing forward
# like a generic default would assume.
# TODO: confirm CUBE_SIDE_M is actually in meters for your rig.
# ---------------------------------------------------------------------------
CUBE_SIDE_M = 0.10  # 10x10 cube face -- assumed centimeters (10cm side)
CUBE_HALF_SIDE_M = CUBE_SIDE_M / 2.0

CAMERA_EXTRINSICS_RAW = {
    "FRONT": {"translation_m": (CUBE_HALF_SIDE_M, 0.0, 0.0), "rpy_deg": (0.0, 0.0, 0.0)},
    "LEFT":  {"translation_m": (0.0, 0.0, -CUBE_HALF_SIDE_M), "rpy_deg": (0.0, 0.0, 90.0)},
    "RIGHT": {"translation_m": (0.0, 0.0, CUBE_HALF_SIDE_M), "rpy_deg": (0.0, 0.0, -90.0)},
    "PICAM": {"translation_m": (-CUBE_HALF_SIDE_M, 0.0, 0.0), "rpy_deg": (0.0, 0.0, 180.0)},
}

# Sampling order. CameraManager.available_cameras() decides what's actually
# reachable each cycle; this just fixes a preference order. Reorder freely.
CAMERA_SAMPLE_ORDER = ["FRONT", "LEFT", "RIGHT", "PICAM"]


def _build_extrinsics():
    T_robot_cam = {}
    T_cam_robot = {}
    for name, spec in CAMERA_EXTRINSICS_RAW.items():
        T = extrinsic_transform(spec["translation_m"], spec["rpy_deg"])
        T_robot_cam[name] = T
        T_cam_robot[name] = invert_homogeneous(T)
    return T_robot_cam, T_cam_robot


T_ROBOT_CAM, T_CAM_ROBOT = _build_extrinsics()
