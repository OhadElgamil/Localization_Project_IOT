"""
Raspberry Pi REST server for ArUco Localization.

Endpoints consumed by the Flutter app:
  GET  /api/health         - connectivity check + status
  GET  /api/markers        - return stored marker calibration
  POST /api/markers        - receive and save marker calibration
  DELETE /api/markers      - clear all stored markers
  GET  /api/localization   - return latest localization result

Run:
  pip install flask flask-cors
  python server.py

The localization logic (ArUco detection + position calculation) belongs
in your existing Python code. Populate `_localization_result` from there
and this server will serve it to the app.
"""

import json
import os
from datetime import datetime, timezone
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

MARKERS_FILE = os.path.join(os.path.dirname(__file__), "markers.json")

# -------------------------------------------------------------------
# Replace this with your actual localization output.
# Your ArUco processing code should write to this dict continuously.
# -------------------------------------------------------------------
_localization_result: dict = {
    "position": {"x": 0.0, "y": 0.0, "z": 0.0},
    "orientation": {"yaw": 0.0, "pitch": 0.0, "roll": 0.0},
    "confidence": 0.0,
    "markers_detected": 0,
    "timestamp": datetime.now(timezone.utc).isoformat(),
}


def update_localization(x: float, y: float, z: float,
                        yaw: float = 0.0, confidence: float = 1.0,
                        markers_detected: int = 0) -> None:
    """Call this from your ArUco processing code to push a new result."""
    _localization_result.update({
        "position": {"x": x, "y": y, "z": z},
        "orientation": {"yaw": yaw, "pitch": 0.0, "roll": 0.0},
        "confidence": confidence,
        "markers_detected": markers_detected,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })


# -------------------------------------------------------------------
# Marker persistence helpers
# -------------------------------------------------------------------
def _load_markers() -> list:
    if os.path.exists(MARKERS_FILE):
        with open(MARKERS_FILE, "r") as f:
            return json.load(f)
    return []


def _save_markers(markers: list) -> None:
    with open(MARKERS_FILE, "w") as f:
        json.dump(markers, f, indent=2)


# -------------------------------------------------------------------
# Routes
# -------------------------------------------------------------------
@app.route("/api/health", methods=["GET"])
def health():
    markers = _load_markers()
    return jsonify({
        "status": "ok",
        "connected_cameras": _count_cameras(),
        "markers_loaded": len(markers),
        "version": "1.0.0",
    })


@app.route("/api/markers", methods=["GET"])
def get_markers():
    return jsonify({"markers": _load_markers()})


@app.route("/api/markers", methods=["POST"])
def set_markers():
    data = request.get_json(force=True)
    markers = data.get("markers", [])
    _save_markers(markers)
    print(f"[server] Received {len(markers)} markers from app.")
    for m in markers:
        print(f"  Marker {m['id']:>4}: X={m['x']:.3f}  Y={m['y']:.3f}  Z={m['z']:.3f}")
    return jsonify({"success": True, "count": len(markers)}), 201


@app.route("/api/markers", methods=["DELETE"])
def clear_markers():
    _save_markers([])
    return jsonify({"success": True}), 200


@app.route("/api/localization", methods=["GET"])
def get_localization():
    return jsonify(_localization_result)


# -------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------
def _count_cameras() -> int:
    """Try to detect how many video devices are present."""
    count = 0
    for i in range(10):
        if os.path.exists(f"/dev/video{i}"):
            count += 1
    return count


if __name__ == "__main__":
    print("ArUco Localization Server starting on http://0.0.0.0:5000")
    app.run(host="0.0.0.0", port=5000, debug=False)
