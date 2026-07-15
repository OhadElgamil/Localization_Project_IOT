# Pipeline

The Pi-side manager for the ArUco localization rig. Run with:

```
python3 pipeline.py
```

## Architecture

```
camera_link.py   CameraManager: TCP server for the 3 ESP32-CAMs + built-in PiCam
aruco_localizer.py  ArucoDetector: marker detection + per-marker PnP pose
marker_map.py    MarkerMap: reads flutter_app/pi_server/markers.json (live reload)
localization.py  LocalizationEngine: fuses 1/2/3+ marker observations into a pose
api_client.py    ApiClient: POSTs results to the Flask server for the Flutter app
geometry.py      Shared rotation/transform/trilateration math
config.py        All ports, paths, and calibration/extrinsics settings
pipeline.py      Orchestrator / entry point
```

## Camera wire protocol

Matches `ESP_EYE/send_pictures_on_command/send_pictures_on_command.ino` (the confirmed hardware
in use — ESP-EYE boards, UXGA/1600x1200 frames). The older AI-Thinker sketch at
`ESP32/send_pictures_on_managers_command/send_pictures_on_managers_command.ino` speaks a
compatible subset of the same protocol and also works.

1. Each camera opens a TCP connection to the Pi on port 5000 and keeps it open.
2. It sends a handshake identifying itself: `ID:FRONT\n` / `ID:LEFT\n` / `ID:RIGHT\n`, immediately
   followed by a `READY\n` line (the ESP-EYE firmware sends both; `camera_link.py` drains the
   `READY\n` if present with a short timeout, so it also works with firmware that only sends `ID:`).
3. The Pi sends `SNAP\n` whenever it wants a frame from that camera.
4. The camera replies with a decimal length line, then exactly that many bytes of JPEG.
5. If a camera drops, the firmware reconnects on its own every 2s; the manager just keeps accepting.

This is a pull/request-response design (the "ask and wait" fallback you described) rather
than a continuous push stream — each named camera slot holds one live connection, and
`CameraManager.sample(name)` blocks for a single SNAP round trip. `pipeline.py` samples
whichever cameras are currently connected, concurrently, every cycle, so you effectively
get "pick any camera, in any order, whenever you want" without needing the firmware to
support real streaming.

The built-in Pi camera is captured separately (`picamera2`, falling back to
`rpicam-still`/`libcamera-still`, falling back to `cv2.VideoCapture(0)` for dev machines)
and exposed under the name `PICAM`.

## Coordinate convention (Y-up)

The whole pipeline, the marker map, and the Flutter app all use the **same Y-up, right-handed
frame**, matching the project's OptiTrack ground truth: **X = forward, Y = up, Z = right**.
Euler angles are `(roll, pitch, yaw)` in degrees: **roll** about X (forward), **pitch** about Z
(right), **yaw** about Y (up) — yaw is the compass-heading rotation, positive = counter-clockwise
from forward (rotates forward toward -Z / left). See `geometry.py`'s module docstring for the
exact math. If you ever add a new coordinate producer (a different mocap system, a different
app), it must use this same convention or positions/orientations will silently be wrong in a
way that can look like "garbage" without being an outright crash.

## Things you must configure before trusting the output

- **`config.MARKER_SIZE_M`** — must match the physical size of the printed markers.
- **`config.CAMERA_EXTRINSICS_RAW`** — where each camera is physically mounted relative to
  the robot's own origin (translation in meters + roll/pitch/yaw in degrees, Y-up convention
  above). Measure your actual rig and update these, or multi-camera fusion will be
  systematically biased.
- **Per-marker orientation** — each marker in the app now has roll/pitch/yaw fields (degrees,
  same convention) in addition to x/y/z, defaulting to 0. If two markers are mounted facing
  different directions (e.g. on different walls) and their orientation isn't set correctly,
  fusing detections from both will be wrong — this was the #1 suspect for "garbage" 2-marker
  results before orientation support existed, since the pipeline previously had no choice but
  to assume every marker faced the same way.
- **Per-camera intrinsics** — run `calibration/calibration.py` for each camera and drop the
  resulting `.npz` (with `camera_matrix` + `dist_coeffs`) into `pipeline/calibration_data/`
  as `FRONT.npz`, `LEFT.npz`, `RIGHT.npz`, `PICAM.npz`. Any camera without a file falls back
  to an uncalibrated default (a logged warning) — usable for testing, not for real distances.

## Marker map

Markers are defined by the Android app and stored at `flutter_app/pi_server/markers.json`
(the Flask server writes this file when the app calibrates). Each entry is
`{id, x, y, z, roll_deg, pitch_deg, yaw_deg}` — the `*_deg` fields are optional and default to
0 for markers saved before orientation support existed. The pipeline reads the file directly
and reloads it whenever it changes — no HTTP dependency, so it keeps working even if the Flask
server is down.

## Localization strategy

- **1 known marker seen** → direct 6DOF pose from that marker's PnP solve, rotated by the
  marker's own orientation from the map (distance + full roll/pitch/yaw).
- **2 known markers seen** → the two measured distances put the robot on a circle (the
  intersection of two spheres centered on the markers); the point on that circle closest
  to the orientation-informed pose estimate is picked ("half triangulation" + orientation
  disambiguation).
- **3+ known markers seen** → full least-squares multilateration on the measured distances,
  with orientation as the confidence-weighted circular mean of each marker's PnP orientation.

In all three cases, each marker's contribution is computed as `T_global_marker @ T_marker_cam`
(marker's own global pose composed with the camera's pose in that marker's local frame), not a
naive translation — so markers facing different directions fuse correctly as long as their
orientation is set in the map.

## Debug logging

`config.LOG_LEVEL = "DEBUG"` (the default) logs, every cycle: raw marker IDs seen per camera,
each marker's distance/tvec/rvec, the marker-map lookup used, each per-marker candidate robot
pose, which fusion path ran and its intermediates, the final result, and the exact JSON POSTed
to Flask. Drop it to `"INFO"` for quieter day-to-day running once things check out. Watch
specifically for `independent single-marker pose disagreement` in the 2-marker path — if two
markers give wildly different independent position estimates, check `MARKER_SIZE_M`, each
marker's position/orientation in the map, and the camera extrinsics, in that order.

## Cross-repo changes made alongside this rewrite (and why)

The old `pipeline.py` was built against a different, stale ESP32 prototype
(`esp32cam_constant_stream.ino`, UDP broadcast trigger) that doesn't match the firmware
that's actually in the repo now. While rebuilding around the real protocol, two blocking
bugs surfaced outside this folder and were fixed:

- **`flutter_app/pi_server/server.py`** — defined `get_localization` twice (Flask would
  refuse to start) and had no `POST /api/localization` route, so results had nowhere to go.
  Fixed the duplicate route and added the POST endpoint, wired to the existing
  `update_localization()` helper (now also carries pitch/roll, not just yaw).
- **Port conflict** — the ESP32 firmware has the camera TCP port (5000) hardcoded, and the
  Flask API defaulted to the same port 5000. Reflashing three physical boards to free up
  5000 is far more disruptive than moving the app's API, so the Flask server now runs on
  **5001** (`flutter_app/pi_server/server.py` and the Flutter app's default port in
  `connection_provider.dart` were both updated). If you've already got the app configured
  against 5000, update it in Settings.
- **ESP32 firmware handshake** — `send_pictures_on_managers_command.ino` originally sent a
  bare `READY\n` line. Updated it to send `ID:<NAME>\n` (with a `camera_id` constant you set
  per device before flashing) to match the Front/Left/Right identification protocol.
