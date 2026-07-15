"""Entry point: the Pi-side manager for the ArUco localization rig.

Wires together the camera link layer (named ESP32-CAM/ESP-EYE cameras over
TCP + the built-in Pi camera), ArUco detection, the marker map, the
3-marker triangulation, and the API client that reports results (or an
insufficient-markers error) to the Flutter app's Flask server. See
README.md for the wire protocol and setup notes.
"""
import logging
import time

import config
from camera_link import CameraManager
from aruco_localizer import ArucoDetector
from marker_map import MarkerMap
import localization
from api_client import ApiClient

logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL),
    format="%(asctime)s.%(msecs)03d [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("pipeline")


def run():
    camera_manager = CameraManager(config)
    camera_manager.start()

    marker_map = MarkerMap(config.MARKERS_FILE)
    detector = ArucoDetector(config)
    api = ApiClient(config.API_BASE_URL)

    logger.info("Pipeline running (log level=%s). Waiting for cameras to connect...", config.LOG_LEVEL)

    cycle = 0
    try:
        while True:
            available = set(camera_manager.available_cameras())
            names = [n for n in config.CAMERA_SAMPLE_ORDER if n in available]

            cycle += 1
            marker_map.reload()

            # Sequential on purpose: correctness first, concurrency later.
            detections = []
            for name in names:
                frame = camera_manager.sample(name)
                if frame is None:
                    continue
                detections.extend(detector.detect(name, frame))

            logger.debug("cycle %d: cameras=%s detections=%d", cycle, names, len(detections))

            result = localization.estimate(detections, marker_map, config.T_CAM_ROBOT)
            api.post_localization(result)  # unconditional: success or error, every cycle

            time.sleep(config.CYCLE_SLEEP_S)
    except KeyboardInterrupt:
        logger.info("Shutting down pipeline...")
    finally:
        camera_manager.stop()


if __name__ == "__main__":
    run()
