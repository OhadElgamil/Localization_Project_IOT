import json
import os
from datetime import datetime, timezone
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

MARKERS_FILE = os.path.join(os.path.dirname(__file__), "markers.json")

_localization_result: dict = {
    "position": None,
    "orientation": None,
    "confidence": 0.0,
    "markers_detected": 0,
    "timestamp": datetime.now(timezone.utc).isoformat(),
    "error": "not enough barcodes detected",
}

def update_localization(x: float = None, y: float = None, z: float = None, yaw: float = 0.0, pitch: float = 0.0, roll: float = 0.0, confidence: float = 1.0, markers_detected: int = 0, error: str = None) -> None:
    if error is not None:
        position = None
        orientation = None
        confidence = 0.0
    else:
        position = {"x": x, "y": y, "z": z}
        orientation = {"yaw": yaw, "pitch": pitch, "roll": roll}
    _localization_result.update({
        "position": position,
        "orientation": orientation,
        "confidence": confidence,
        "markers_detected": markers_detected,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "error": error,
    })

def _load_markers() -> list:
    if os.path.exists(MARKERS_FILE):
        with open(MARKERS_FILE, "r") as f:
            return json.load(f)
    return []

def _save_markers(markers: list) -> None:
    with open(MARKERS_FILE, "w") as f:
        json.dump(markers, f, indent=2)

@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({
        "status": "ok",
        "markers_loaded": len(_load_markers()),
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
    return jsonify({"success": True, "count": len(markers)}), 201

@app.route("/api/markers", methods=["DELETE"])
def clear_markers():
    _save_markers([])
    return jsonify({"success": True}), 200

@app.route("/api/localization", methods=["GET"])
def get_localization():
    result = dict(_localization_result)
    try:
        # If the pipeline itself hasn't reported anything in over a second
        # (crashed, disconnected, never started), that's distinct from a
        # normal "not enough barcodes this cycle" error the pipeline sends
        # explicitly and immediately.
        last_time = datetime.fromisoformat(result["timestamp"])
        time_since_update = (datetime.now(timezone.utc) - last_time).total_seconds()
        if time_since_update > 1.0:
            result["markers_detected"] = 0
            result["position"] = None
            result["orientation"] = None
            result["confidence"] = 0.0
            result["error"] = "Connection to pipeline lost"
    except ValueError:
        pass # Failsafe just in case the timestamp format is slightly off

    return jsonify(result)

@app.route("/api/localization", methods=["POST"])
def post_localization():
    data = request.get_json(force=True)

    if data.get("error"):
        update_localization(
            error=str(data["error"]),
            markers_detected=int(data.get("markers_detected", 0)),
        )
        return jsonify({"success": True}), 201

    position = data.get("position") or data
    orientation = data.get("orientation") or data
    try:
        update_localization(
            x=float(position["x"]),
            y=float(position["y"]),
            z=float(position["z"]),
            yaw=float(orientation.get("yaw", 0.0)) if isinstance(orientation, dict) else float(data.get("yaw", 0.0)),
            pitch=float(orientation.get("pitch", 0.0)) if isinstance(orientation, dict) else float(data.get("pitch", 0.0)),
            roll=float(orientation.get("roll", 0.0)) if isinstance(orientation, dict) else float(data.get("roll", 0.0)),
            confidence=float(data.get("confidence", 1.0)),
            markers_detected=int(data.get("markers_detected", 0)),
            error=None,
        )
    except (KeyError, TypeError, ValueError) as e:
        return jsonify({"success": False, "error": str(e)}), 400
    return jsonify({"success": True}), 201

if __name__ == "__main__":
    # Port 5001, not 5000: the ESP32-CAM firmware has port 5000 hardcoded for
    # its own TCP camera protocol (pipeline/camera_link.py listens there), so
    # this REST API had to move to avoid the collision. Update the Flutter
    # app's connection settings if it's still pointing at 5000.
    print("ArUco Localization Server starting on http://0.0.0.0:5001")
    app.run(host="0.0.0.0", port=5001, debug=False)