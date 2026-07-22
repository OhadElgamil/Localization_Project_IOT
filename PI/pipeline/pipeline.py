"""Entry point: the Pi-side manager for the ArUco localization rig.

Wires together the camera link layer (named ESP32-CAM/ESP-EYE cameras over
TCP + the built-in Pi camera), ArUco detection, the marker map, the
3-marker triangulation, and the API client that reports results (or an
insufficient-markers error) to the Flutter app's Flask server. See
README.md for the wire protocol and setup notes.
"""
import logging
import time
import concurrent.futures

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
    last_detections = {}  # name -> (timestamp, detections)
    try:
        while True:
            available = set(camera_manager.available_cameras())
            names = [n for n in config.CAMERA_SAMPLE_ORDER if n in available]

            cycle += 1
            marker_map.reload()

            # Concurrent sampling to minimize network latency
            detections = []
            if names:
                with concurrent.futures.ThreadPoolExecutor(max_workers=len(names)) as executor:
                    # Fire all SNAP requests simultaneously
                    future_to_name = {executor.submit(camera_manager.sample, name): name for name in names}
                    
                    # As each camera responds, run the ArUco detection
                    for future in concurrent.futures.as_completed(future_to_name):
                        name = future_to_name[future]
                        frame = future.result()
                        current_time = time.monotonic()
                        if frame is not None:
                            cam_detections = detector.detect(name, frame)
                            last_detections[name] = (current_time, cam_detections)
                            detections.extend(cam_detections)
                        else:
                            if name in last_detections:
                                cache_time, cam_detections = last_detections[name]
                                if (current_time - cache_time) <= config.FRAME_CACHE_TTL_S:
                                    logger.debug("[%s] frame dropped, reusing cached detections from %.2fs ago", name, current_time - cache_time)
                                    detections.extend(cam_detections)

            camera_times = camera_manager.response_times()
            logger.debug("cycle %d: cameras=%s detections=%d times=%s", cycle, names, len(detections), camera_times)

            result = localization.estimate_least_squares(detections, marker_map, config.T_CAM_ROBOT,
                                            max_markers=config.MAX_TRIANGULATION_MARKERS)
            api.post_localization(result, camera_response_times=camera_times)  # unconditional: success or error, every cycle

            time.sleep(config.CYCLE_SLEEP_S)
    except KeyboardInterrupt:
        logger.info("Shutting down pipeline...")
    finally:
        camera_manager.stop()


if __name__ == "__main__":
    run()
