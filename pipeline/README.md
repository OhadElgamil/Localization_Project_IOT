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

Matches `ESP32/send_pictures_on_managers_command/send_pictures_on_managers_command.ino`:

1. Each ESP32-CAM opens a TCP connection to the Pi on port 5000 and keeps it open.
2. It sends one handshake line identifying itself: `ID:FRONT\n`, `ID:LEFT\n`, or `ID:RIGHT\n`.
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

## Things you must configure before trusting the output

- **`config.MARKER_SIZE_M`** — must match the physical size of the printed markers.
- **`config.CAMERA_EXTRINSICS_RAW`** — where each camera is physically mounted relative to
  the robot's own origin (translation in meters + roll/pitch/yaw in degrees). Defaults
  assume all four cameras sit at the robot's center, with Left/Right rotated ±90°. Measure
  your actual rig and update these, or multi-camera fusion will be systematically biased.
- **Per-camera intrinsics** — run `calibration/calibration.py` for each camera and drop the
  resulting `.npz` (with `camera_matrix` + `dist_coeffs`) into `pipeline/calibration_data/`
  as `FRONT.npz`, `LEFT.npz`, `RIGHT.npz`, `PICAM.npz`. Any camera without a file falls back
  to an uncalibrated default (a logged warning) — usable for testing, not for real distances.

## Marker map

Markers are defined by the Android app and stored at `flutter_app/pi_server/markers.json`
(the Flask server writes this file when the app calibrates). The pipeline reads that same
file directly and reloads it whenever it changes — no HTTP dependency, so it keeps working
even if the Flask server is down.

## Localization strategy

- **1 known marker seen** → direct 6DOF pose from that marker's PnP solve (distance +
  full roll/pitch/yaw orientation).
- **2 known markers seen** → the two measured distances put the robot on a circle (the
  intersection of two spheres centered on the markers); the point on that circle closest
  to the orientation-informed pose estimate is picked ("half triangulation" + orientation
  disambiguation).
- **3+ known markers seen** → full least-squares multilateration on the measured distances,
  with orientation as the confidence-weighted circular mean of each marker's PnP orientation.

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
