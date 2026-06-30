import json
import os
from datetime import datetime, timezone
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

MARKERS_FILE = os.path.join(os.path.dirname(__file__), "markers.json")

_localization_result: dict = {
    "position": {"x": 0.0, "y": 0.0, "z": 0.0},
    "orientation": {"yaw": 0.0, "pitch": 0.0, "roll": 0.0},
    "confidence": 0.0,
    "markers_detected": 0,
    "timestamp": datetime.now(timezone.utc).isoformat(),
}

def update_localization(x: float, y: float, z: float, yaw: float = 0.0, confidence: float = 1.0, markers_detected: int = 0) -> None:
    _localization_result.update({
        "position": {"x": x, "y": y, "z": z},
        "orientation": {"yaw": yaw, "pitch": 0.0, "roll": 0.0},
        "confidence": confidence,
        "markers_detected": markers_detected,
        "timestamp": datetime.now(timezone.utc).isoformat(),
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
    return jsonify(_localization_result)

@app.route("/api/localization", methods=["GET"])
def get_localization():
    try:
        # Check how much time has passed since the last valid camera update
        last_time = datetime.fromisoformat(_localization_result["timestamp"])
        time_since_update = (datetime.now(timezone.utc) - last_time).total_seconds()
        
        # If no camera has seen a barcode in over 1 second, set count to 0
        if time_since_update > 1.0:
            _localization_result["markers_detected"] = 0
            
    except ValueError:
        pass # Failsafe just in case the timestamp format is slightly off

    return jsonify(_localization_result)

if __name__ == "__main__":
    print("ArUco Localization Server starting on http://0.0.0.0:5000")
    app.run(host="0.0.0.0", port=5000, debug=False)