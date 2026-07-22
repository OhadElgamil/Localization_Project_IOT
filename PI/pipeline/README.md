# Pipeline

The Pi-side manager for the ArUco localization rig. Run with:

```
python3 pipeline.py
```

Run the tests with:

```
python -m unittest test_localization -v
```

## Architecture

```
camera_link.py      CameraManager: TCP server for the ESP32-CAM/ESP-EYE cameras + built-in PiCam
aruco_localizer.py   ArucoDetector: marker detection + per-marker PnP pose (world-convention output)
marker_map.py        MarkerMap: reads flutter_app/pi_server/markers.json (live reload)
localization.py      Pure fusion logic: 3-closest-markers trilateration, or an explicit error
contracts.py         MarkerDetection / LocalizationResult dataclasses shared across modules
api_client.py         ApiClient: POSTs results (or errors) to the Flask server for the Flutter app
geometry.py           Shared rotation/transform/trilateration math + the two axis-correction matrices
config.py             All ports, paths, and calibration/extrinsics settings
pipeline.py            Orchestrator / entry point
test_localization.py   Unit tests (fabricated inputs, no cameras/images/sockets)
```

## Coordinate convention

World axes are **X, Y (up), Z**, right-handed. No axis is labeled "forward" -- instead, **an
object at identity orientation (roll=pitch=yaw=0) faces world -Z**, for both markers and cameras.
Yaw rotates about Y (up). See `geometry.py`'s module docstring for the full derivation, including
the two fixed correction matrices (`CAM_CV_TO_WORLD`, `MARKER_RAW_TO_WORLD`) that convert OpenCV's
raw solvePnP output and the raw ArUco marker-corner frame into this convention before anything
else uses them. If you ever add a new coordinate producer (a different mocap system, a different
app), it must use this same convention or positions/orientations will silently be wrong.

## Camera wire protocol

Matches `ESP_EYE/send_pictures_on_command/send_pictures_on_command.ino` (the confirmed hardware in
use). The older `ESP32/send_pictures_on_managers_command/send_pictures_on_managers_command.ino`
speaks a compatible subset and also works.

1. Each camera opens a TCP connection to the Pi on port 5000 and keeps it open.
2. It sends a handshake identifying itself: `ID:FRONT\n` / `ID:LEFT\n` / `ID:RIGHT\n`, usually
   followed by a `READY\n` line (drained if present; also works with firmware that omits it).
3. The Pi sends `SNAP\n` whenever it wants a frame from that camera.
4. The camera replies with a decimal length line, then exactly that many bytes of JPEG.
5. If a camera drops, the firmware reconnects on its own every 2s; the manager just keeps accepting.

This is a pull/request-response design -- each named camera slot holds one live connection, and
`CameraManager.sample(name)` blocks for a single SNAP round trip. `pipeline.py` samples every
currently-connected camera **sequentially** each cycle (concurrency was deliberately dropped for
this rewrite -- correctness first, latency optimization is a later pass).

The built-in Pi camera is captured separately (`picamera2`, falling back to
`rpicam-still`/`libcamera-still`, falling back to `cv2.VideoCapture(0)` for dev machines) and
exposed under the name `PICAM`.

## Camera intrinsics

Cameras are assumed perfect by default: if no calibration file exists, intrinsics are derived
directly from each captured frame's actual shape (`focal_length = frame width in pixels`,
principal point = frame center, zero distortion) -- matching this repo's `aruco_detection.py`. A
real calibration always takes priority: drop the `.npz` produced by `calibration/calibration.py`
(containing `camera_matrix` + `dist_coeffs`) into `pipeline/calibration_data/<NAME>.npz`.

## Things you must configure before trusting the output

- **`config.MARKER_SIZE_M`** — must match the physical size of the printed markers (currently 0.175m).
- **`config.CAMERA_EXTRINSICS_RAW`** — where each camera is physically mounted relative to the
  robot's own origin (translation in meters + roll/pitch/yaw in degrees, world convention above).
  All placeholders right now (zero offset, zero rotation) -- measure your actual rig.
- **Per-marker orientation** — each marker in the app has roll/pitch/yaw fields (degrees) in
  addition to x/y/z, defaulting to 0 (facing world -Z). If two markers face different directions
  and their orientation isn't set correctly, fusing detections from both will be wrong.

## Marker map

Markers are defined by the Android app and stored at `flutter_app/pi_server/markers.json` (the
Flask server writes this file when the app calibrates). Each entry is
`{id, x, y, z, roll_deg, pitch_deg, yaw_deg}` — the `*_deg` fields are optional and default to 0.
The pipeline reads the file directly and reloads it whenever it changes — no HTTP dependency, so
it keeps working even if the Flask server is down.

## Localization strategy

Exactly 3 markers -- the 3 closest, by raw measured camera-to-marker distance -- are used for a
least-squares trilateration (position) + confidence-weighted circular mean (orientation). If fewer
than 3 known markers are visible this cycle, the pipeline doesn't guess: it reports an explicit
error (`contracts.INSUFFICIENT_MARKERS_ERROR`, `"not enough barcodes detected"`), which the app
displays in place of a position. See "How the position math actually works" below for what each
marker's contribution is built from.

### How the position math actually works

`cv2.solvePnP` does 100% of the "find the camera relative to this marker" work. On top of that:

1. `solvePnP` returns the marker's position **as seen from the camera, in the camera's own (raw
   OpenCV) axes** -- backwards from what's wanted, and not yet in axes that can be rotated into
   world coordinates (the camera's world orientation is the whole unknown).
2. Invert once (`R.T`, `-R.T @ tvec`): now it's "the camera's position, as seen from the marker,
   in the marker's own axes" -- the same physical offset, re-expressed from a viewpoint whose
   orientation in the room **is** known (the marker's fixed, measured mounting).
3. Apply the one-time `CAM_CV_TO_WORLD` correction and rotate by the marker's own known world
   orientation (`MARKER_RAW_TO_WORLD` then the marker's roll/pitch/yaw -- identity if unrotated).
4. **Add** that rotated offset to the marker's known global position. For an unrotated marker,
   step 3's rotation is the identity and this is exactly `marker_position + offset`.

The 4x4 homogeneous-transform code (`T_global_marker @ T_marker_cam @ T_cam_robot`) is just steps
2-4 in one matrix multiply -- bookkeeping, not additional math.

## Error contract

`GET`/`POST /api/localization` now carries a nullable `error` field. On success it's `null` and
`position`/`orientation` are populated as before. When fewer than 3 markers are seen, `position`
and `orientation` are `null` and `error` is `"not enough barcodes detected"` (`markers_detected`
still carries the actual count). The pipeline POSTs every cycle regardless of outcome, so the app
reflects the current state within one cycle rather than waiting on a staleness timeout.

## Debug logging

`config.LOG_LEVEL = "DEBUG"` (the default) logs, every cycle: raw marker IDs seen per camera, each
marker's distance/tvec, the marker-map lookup used, each per-marker candidate robot pose, the
final fused result or the insufficient-markers error, and the exact JSON POSTed to Flask. Drop it
to `"INFO"` for quieter day-to-day running once things check out.
