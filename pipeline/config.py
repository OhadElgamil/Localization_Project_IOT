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

MAX_TRIANGULATION_MARKERS = 7  # localization.py trilaterates every 3-marker
                                # combination among the closest N seen this
                                # cycle and fuses the results; N is capped
                                # here since combinations grow fast (C(N,3):
                                # 7 -> 35 triplets, 10 -> 120).

SNAP_TIMEOUT_S = 1.5       # per-camera SNAP round trip timeout: cameras are now
                           # sampled in parallel (see pipeline.py), so this is
                           # also the worst-case cycle time if one camera hangs.
                           # Kept comfortably under the server's staleness
                           # threshold (flutter_app/pi_server/server.py) so a
                           # single flaky camera can't false-flag the whole
                           # pipeline as disconnected -- it's just skipped for
                           # that cycle instead, and picked up again next time.
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
# (np.savez with camera_matrix + dist_coeffs). Filename must be calibration_data_ID.npz
# where ID is the upper-case camera name (e.g., FRONT, LEFT, RIGHT, PI),
# placed in the directory below. Cameras without a file are assumed perfect:
# intrinsics are derived from each captured frame's actual shape instead.
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
# Rig: reference point at the center of a 10cm x 10cm square, all cameras at
# that same height (y offset 0 for all). One camera sits at the midpoint of
# each edge, facing straight outward. FRONT/LEFT/RIGHT are named relative to
# PICAM, which sits on the rear edge. Half the square's side (0.05m) sets
# each translation; each yaw is whatever rotation makes that camera face
# straight outward from its own edge, solved against the -Z-at-identity
# convention above.
# TODO: if the rig geometry changes (different size, different arrangement),
# recompute these -- this config makes no assumption about rig shape, these
# specific numbers are just this rig's measurements.
# ---------------------------------------------------------------------------
CAMERA_EXTRINSICS_RAW = {
    "FRONT": {"translation_m": (0.05, 0.0, 0.0), "rpy_deg": (0.0, 0.0, -90.0)},
    "LEFT":  {"translation_m": (0.0, 0.0, -0.05), "rpy_deg": (0.0, 0.0, 0.0)},
    "RIGHT": {"translation_m": (0.0, 0.0, 0.05), "rpy_deg": (0.0, 0.0, 180.0)},
    "PICAM": {"translation_m": (-0.05, 0.0, 0.0), "rpy_deg": (0.0, 0.0, 90.0)},
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
