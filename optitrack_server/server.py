import math
import time
from datetime import datetime, timezone
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# Delay between retries when the OptiTrack call fails. The OptiTrack
# interface is a third-party system we don't control and known to be flaky,
# so a small pause avoids hammering it while it recovers.
RETRY_DELAY_S = 0.5

_stats = {
    "requests_served": 0,
    "total_failed_attempts": 0,
    "last_failed_attempts": 0,
}


def query_optitrack() -> dict:
    """
    PLACEHOLDER -- replace the body of this function with the real call into
    the OptiTrack/Motive system (e.g. a NatNet client request for a rigid
    body's current position).

    Contract this function must follow:
    - Return a dict {"x": float, "y": float, "z": float} in meters, in the
      same world frame as the app's own localization estimate.
    - Raise any exception on failure (timeout, bad frame, disconnected,
      etc.) -- the caller (query_optitrack_with_retry) already retries on
      any exception, so this function does not need its own retry logic.

    Everything else in this file (the Flask routes, the retry loop, the
    failed-attempt counter) is meant to stay as-is; only this function
    should need to change to plug in the real system.
    """
    raise NotImplementedError(
        "query_optitrack() is a placeholder -- wire it up to the real "
        "OptiTrack/NatNet client."
    )


def query_optitrack_with_retry() -> tuple[dict, int]:
    """
    Calls query_optitrack() in a loop until it succeeds, since the OptiTrack
    interface is known to be buggy/flaky and we can't fix it ourselves.
    Returns (ground_truth_position, failed_attempts) once it finally gets an
    answer. Does not give up -- a caller waiting on this may block for a
    while if OptiTrack is having a bad moment.
    """
    failed_attempts = 0
    while True:
        try:
            position = query_optitrack()
            return position, failed_attempts
        except Exception as e:
            failed_attempts += 1
            print(f"[optitrack] attempt {failed_attempts} failed: {e}")
            time.sleep(RETRY_DELAY_S)


@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({
        "status": "ok",
        "version": "1.0.0",
        "requests_served": _stats["requests_served"],
        "total_failed_attempts": _stats["total_failed_attempts"],
    })


@app.route("/api/compare", methods=["POST"])
def compare():
    data = request.get_json(force=True)
    position = data.get("position") or data
    try:
        est_x = float(position["x"])
        est_y = float(position["y"])
        est_z = float(position["z"])
    except (KeyError, TypeError, ValueError) as e:
        return jsonify({"success": False, "error": f"invalid position: {e}"}), 400

    ground_truth, failed_attempts = query_optitrack_with_retry()

    error_m = math.sqrt(
        (ground_truth["x"] - est_x) ** 2
        + (ground_truth["y"] - est_y) ** 2
        + (ground_truth["z"] - est_z) ** 2
    )

    _stats["requests_served"] += 1
    _stats["total_failed_attempts"] += failed_attempts
    _stats["last_failed_attempts"] = failed_attempts

    return jsonify({
        "success": True,
        "estimate": {"x": est_x, "y": est_y, "z": est_z},
        "ground_truth": ground_truth,
        "error_m": error_m,
        "failed_attempts": failed_attempts,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }), 200


if __name__ == "__main__":
    # Runs on the machine connected to the OptiTrack system, not the Pi.
    # Port 5002: 5000 is the ESP32-CAM TCP protocol, 5001 is pi_server's
    # Flask REST API -- see flutter_app/pi_server/server.py.
    print("OptiTrack comparison server starting on http://0.0.0.0:5002")
    # threaded=True so a slow/retrying /api/compare request doesn't block
    # other requests (e.g. /api/health) on the same server.
    app.run(host="0.0.0.0", port=5002, debug=False, threaded=True)
