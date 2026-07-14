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

SNAP_TIMEOUT_S = 3.0       # how long to wait for one ESP32-CAM SNAP round trip
CYCLE_SLEEP_S = 0.05       # gap between sampling cycles

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
ARUCO_DICT = cv2.aruco.DICT_4X4_50
MARKER_SIZE_M = 0.05  # TODO: must match the physical markers on the wall

# Per-camera calibration produced by calibration/calibration.py
# (np.savez with camera_matrix + dist_coeffs). Filename must be the upper-case
# camera name, e.g. calibration_data/FRONT.npz.
CALIBRATION_DIR = os.path.join(PIPELINE_DIR, "calibration_data")

# Fallback intrinsics used when no calibration file exists for a camera yet.
# Matches the SVGA (800x600) frame size configured in the ESP32 firmware.
DEFAULT_FRAME_WIDTH = 800
DEFAULT_FRAME_HEIGHT = 600
DEFAULT_FOCAL_LENGTH = 800.0

PICAM_WIDTH = 800
PICAM_HEIGHT = 600

# ---------------------------------------------------------------------------
# Camera extrinsics: where each camera is mounted relative to the robot's
# body-frame origin. translation_m = (x, y, z) forward/left/up in meters,
# rpy_deg = (roll, pitch, yaw) in degrees, yaw measured counter-clockwise
# from the robot's forward axis.
# TODO: measure your actual rig and update these.
# ---------------------------------------------------------------------------
CAMERA_EXTRINSICS_RAW = {
    "FRONT": {"translation_m": (0.0, 0.0, 0.0), "rpy_deg": (0.0, 0.0, 0.0)},
    "LEFT":  {"translation_m": (0.0, 0.0, 0.0), "rpy_deg": (0.0, 0.0, 90.0)},
    "RIGHT": {"translation_m": (0.0, 0.0, 0.0), "rpy_deg": (0.0, 0.0, -90.0)},
    "PICAM": {"translation_m": (0.0, 0.0, 0.0), "rpy_deg": (0.0, 0.0, 0.0)},
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
