"""Entry point: the Pi-side manager for the ArUco localization rig.

Wires together the camera link layer (Front/Left/Right ESP32-CAMs over TCP +
the built-in Pi camera), ArUco detection, the marker map, the localization
fusion engine, and the API client that reports results to the Flutter app's
Flask server. See README.md for the wire protocol and setup notes.
"""
import logging
import time
from concurrent.futures import ThreadPoolExecutor

import config
from camera_link import CameraManager
from aruco_localizer import ArucoDetector
from marker_map import MarkerMap
from localization import LocalizationEngine
from api_client import ApiClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("pipeline")


def run():
    camera_manager = CameraManager(config)
    camera_manager.start()

    marker_map = MarkerMap(config.MARKERS_FILE)
    detector = ArucoDetector(config)
    engine = LocalizationEngine(config)
    api = ApiClient(config.API_BASE_URL)

    logger.info("Pipeline running. Waiting for cameras to connect...")

    with ThreadPoolExecutor(max_workers=4) as pool:
        try:
            while True:
                available = set(camera_manager.available_cameras())
                names = [n for n in config.CAMERA_SAMPLE_ORDER if n in available]
                if not names:
                    time.sleep(0.5)
                    continue

                marker_map.reload()

                # SNAP round trips are independent I/O waits, so sample every
                # reachable camera concurrently instead of paying N x latency.
                frames = dict(zip(names, pool.map(camera_manager.sample, names)))

                detections = []
                for name, frame in frames.items():
                    if frame is None:
                        continue
                    detections.extend(detector.detect(name, frame))

                result = engine.estimate(detections, marker_map)
                if result is not None:
                    api.post_localization(result)
                    logger.info(
                        "pos=(%.2f, %.2f, %.2f) yaw=%.1f deg markers=%d %s conf=%.2f",
                        result.position[0], result.position[1], result.position[2],
                        (result.orientation[2] * 180.0 / 3.14159265),
                        result.markers_detected, result.marker_ids, result.confidence,
                    )

                time.sleep(config.CYCLE_SLEEP_S)
        except KeyboardInterrupt:
            logger.info("Shutting down pipeline...")
        finally:
            camera_manager.stop()


if __name__ == "__main__":
    run()
