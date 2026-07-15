"""Plain data contracts shared between the detector, localization, and API layers.

Deliberately dependency-free (numpy only -- no cv2, no sockets) so
localization.py, and its tests, never need to import camera/network code.
"""
from dataclasses import dataclass, field

import numpy as np

INSUFFICIENT_MARKERS_ERROR = "not enough barcodes detected"


@dataclass
class MarkerDetection:
    marker_id: int
    camera_name: str
    distance_m: float
    T_marker_cam: np.ndarray  # camera's pose (world convention), in the marker's local frame


@dataclass
class LocalizationResult:
    position: np.ndarray = None        # (x, y, z) world meters; None on error
    orientation: tuple = None          # (roll, pitch, yaw) radians; None on error
    confidence: float = 0.0
    markers_detected: int = 0
    marker_ids: list = field(default_factory=list)
    error: str = None                  # None on success, else INSUFFICIENT_MARKERS_ERROR
