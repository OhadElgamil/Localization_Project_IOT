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
# Must match `pi_port` hardcoded in the ESP32-CAM/ESP-EYE firmware. Changing
# this requires reflashing every camera, so leave it alone unless you also
# update the firmware.
CAMERA_TCP_HOST = "0.0.0.0"
CAMERA_TCP_PORT = 5000

# The Flask REST API used by the Flutter app (flutter_app/pi_server/server.py).
# Runs on 5001, not 5000, since the camera TCP server above owns port 5000.
API_BASE_URL = "http://127.0.0.1:5001"

SNAP_TIMEOUT_S = 6.0       # per-camera SNAP round trip timeout
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
MARKER_SIZE_M = 0.175  # must match the physical markers on the wall

# Per-camera calibration produced by calibration/calibration.py
# (np.savez with camera_matrix + dist_coeffs). Filename must be the upper-case
# camera name, e.g. calibration_data/FRONT.npz. Cameras without a file are
# assumed perfect: intrinsics are derived from each captured frame's actual
# shape instead (see aruco_localizer.py).
CALIBRATION_DIR = os.path.join(PIPELINE_DIR, "calibration_data")

PICAM_WIDTH = 800
PICAM_HEIGHT = 600

# ---------------------------------------------------------------------------
# Camera extrinsics: where each camera is mounted relative to the robot's own
# body-frame origin (pick any fixed point on the rig, e.g. the same point
# your ground-truth system's rigid body is defined around).
#
# World/robot convention (see geometry.py): X, Y (up), Z, right-handed. No
# axis is "forward" by itself -- an object at rpy=(0,0,0) faces world -Z.
# translation_m = (x, y, z) offset in meters. rpy_deg = (roll, pitch, yaw) in
# degrees; yaw rotates about Y (up).
#
# TODO: these are placeholders. Measure your actual rig (translation offset
# + mounting rotation for each camera) and replace every entry below. Do not
# assume any particular rig shape -- this config makes no assumption about
# how many cameras there are or how they're arranged.
# ---------------------------------------------------------------------------
CAMERA_EXTRINSICS_RAW = {
    "FRONT": {"translation_m": (0.0, 0.0, 0.0), "rpy_deg": (0.0, 0.0, 0.0)},
    "LEFT":  {"translation_m": (0.0, 0.0, 0.0), "rpy_deg": (0.0, 0.0, 0.0)},
    "RIGHT": {"translation_m": (0.0, 0.0, 0.0), "rpy_deg": (0.0, 0.0, 0.0)},
    "PICAM": {"translation_m": (0.0, 0.0, 0.0), "rpy_deg": (0.0, 0.0, 0.0)},
}

# Sampling order. CameraManager.available_cameras() decides what's actually
# reachable each cycle; this just fixes a preference order. Reorder freely.
CAMERA_SAMPLE_ORDER = ["FRONT", "LEFT", "RIGHT", "PICAM"]


def _build_extrinsics():
    T_cam_robot = {}
    for name, spec in CAMERA_EXTRINSICS_RAW.items():
        T_robot_cam = extrinsic_transform(spec["translation_m"], spec["rpy_deg"])
        T_cam_robot[name] = invert_homogeneous(T_robot_cam)
    return T_cam_robot


T_CAM_ROBOT = _build_extrinsics()
