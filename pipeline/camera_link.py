"""Manages connections to the ESP32-CAM/ESP-EYE cameras plus the built-in Pi camera.

Wire protocol (must match ESP_EYE/send_pictures_on_command/send_pictures_on_command.ino,
and the compatible subset spoken by ESP32/send_pictures_on_managers_command.ino):
  1. Camera opens a TCP connection to the Pi on CAMERA_TCP_PORT and keeps it open.
  2. Camera sends a handshake line: "ID:FRONT\\n" / "ID:LEFT\\n" / "ID:RIGHT\\n",
     immediately followed by a "READY\\n" line (drained here with a short
     timeout; older firmware that only sends "ID:" also works fine).
  3. Pi sends "SNAP\\n" whenever it wants a frame from that camera.
  4. Camera replies with a decimal length line ("12345\\n") followed by exactly
     that many bytes of JPEG data.
  5. If the camera drops the connection, it reconnects on its own (firmware
     retries every 2s), so the manager just needs to keep accepting.

This is a pull/request-response design: each named camera slot holds at most
one live connection, and `sample()` blocks for one SNAP round trip.
"""
import logging
import os
import shutil
import socket
import subprocess
import tempfile
import threading
import time

import cv2
import numpy as np

logger = logging.getLogger("pipeline.camera_link")

KNOWN_NAMES = {"FRONT", "LEFT", "RIGHT"}


class EspCameraLink:
    def __init__(self, name, conn, addr):
        self.name = name
        self.addr = addr
        self._conn = conn
        self._rfile = conn.makefile("rb")
        self._lock = threading.Lock()
        self.connected = True

    def snap(self, timeout=3.0):
        """Request one fresh frame. Returns a BGR np.ndarray, or None on failure."""
        with self._lock:
            if not self.connected:
                return None
            try:
                self._conn.settimeout(timeout)
                self._conn.sendall(b"SNAP\n")

                size_line = self._rfile.readline()
                if not size_line:
                    raise ConnectionError("camera closed the connection")
                image_len = int(size_line.decode("ascii", errors="ignore").strip())

                data = self._rfile.read(image_len)
                if data is None or len(data) != image_len:
                    raise ConnectionError("incomplete image payload")

                arr = np.frombuffer(data, dtype=np.uint8)
                frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
                if frame is None:
                    raise ConnectionError("JPEG decode failed")
                return frame
            except (socket.timeout, socket.error, ValueError, ConnectionError) as e:
                logger.warning("[%s] snap failed, dropping connection: %s", self.name, e)
                self._close_locked()
                return None

    def close(self):
        with self._lock:
            self._close_locked()

    def _close_locked(self):
        self.connected = False
        try:
            self._conn.close()
        except Exception:
            pass


class CameraManager:
    def __init__(self, config):
        self.config = config
        self._links = {}
        self._links_lock = threading.Lock()
        self._sock = None
        self._running = False
        self._accept_thread = None

        self._picam = None
        self._picam_mode = None  # "picamera2" | "subprocess" | "cv2" | None
        self._init_local_camera()

    # -- ESP32-CAM TCP server -------------------------------------------------
    def start(self):
        self._running = True
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((self.config.CAMERA_TCP_HOST, self.config.CAMERA_TCP_PORT))
        sock.listen()
        sock.settimeout(1.0)
        self._sock = sock
        self._accept_thread = threading.Thread(target=self._accept_loop, daemon=True)
        self._accept_thread.start()
        logger.info("Camera TCP server listening on %s:%d",
                    self.config.CAMERA_TCP_HOST, self.config.CAMERA_TCP_PORT)

    def stop(self):
        self._running = False
        if self._sock is not None:
            try:
                self._sock.close()
            except Exception:
                pass
        with self._links_lock:
            for link in self._links.values():
                link.close()
        if self._picam_mode == "picamera2" and self._picam is not None:
            try:
                self._picam.stop()
            except Exception:
                pass
        elif self._picam_mode == "cv2" and self._picam is not None:
            try:
                self._picam.release()
            except Exception:
                pass

    def _accept_loop(self):
        while self._running:
            try:
                conn, addr = self._sock.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            threading.Thread(target=self._handshake, args=(conn, addr), daemon=True).start()

    def _handshake(self, conn, addr):
        try:
            conn.settimeout(5.0)
            rfile = conn.makefile("rb")
            line = rfile.readline().decode("ascii", errors="ignore").strip()
            name = line[3:].strip().upper() if line.startswith("ID:") else None
            if name not in KNOWN_NAMES:
                logger.warning("Rejecting connection from %s: unrecognized handshake %r", addr[0], line)
                conn.close()
                return

            # ESP_EYE firmware sends a second "READY\n" line right after the
            # ID line. Older firmware doesn't. Drain it if present so it
            # can't get mistaken for a SNAP response's length line later; a
            # short timeout tells "no second line coming" apart from "still
            # in flight" without blocking the handshake indefinitely.
            conn.settimeout(0.5)
            try:
                extra = rfile.readline().decode("ascii", errors="ignore").strip()
                if extra and extra.upper() != "READY":
                    logger.debug("[%s] unexpected line after handshake: %r", name, extra)
            except socket.timeout:
                pass

            conn.settimeout(None)
            link = EspCameraLink(name, conn, addr)
            with self._links_lock:
                old = self._links.get(name)
                self._links[name] = link
            if old is not None:
                old.close()
            logger.info("[%s] camera connected from %s", name, addr[0])
        except Exception as e:
            logger.warning("Handshake failed from %s: %s", addr[0], e)
            try:
                conn.close()
            except Exception:
                pass

    # -- Built-in Pi camera -----------------------------------------------------
    def _init_local_camera(self):
        try:
            from picamera2 import Picamera2  # type: ignore
            self._picam = Picamera2()
            still_config = self._picam.create_still_configuration()
            self._picam.configure(still_config)
            self._picam.start()
            time.sleep(1.0)  # let auto-exposure settle
            self._picam_mode = "picamera2"
            logger.info("PiCam: using picamera2")
            return
        except Exception as e:
            logger.info("PiCam: picamera2 unavailable (%s)", e)

        if shutil.which("rpicam-still") or shutil.which("libcamera-still"):
            self._picam_mode = "subprocess"
            logger.info("PiCam: using rpicam-still/libcamera-still subprocess fallback")
            return

        cap = cv2.VideoCapture(0)
        if cap.isOpened():
            self._picam = cap
            self._picam_mode = "cv2"
            logger.info("PiCam: no Pi camera stack found, using cv2.VideoCapture(0) (dev fallback)")
            return

        logger.warning("PiCam: no local camera available")

    def _capture_local(self):
        if self._picam_mode == "picamera2":
            arr = self._picam.capture_array()
            return cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)

        if self._picam_mode == "subprocess":
            tmp = os.path.join(tempfile.gettempdir(), "pipeline_picam_snap.jpg")
            for cmd_name in ("rpicam-still", "libcamera-still"):
                if not shutil.which(cmd_name):
                    continue
                cmd = [cmd_name, "-o", tmp, "-t", "100", "--immediate", "--nopreview",
                       "--width", str(self.config.PICAM_WIDTH), "--height", str(self.config.PICAM_HEIGHT)]
                try:
                    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                    check=True, timeout=5)
                    return cv2.imread(tmp)
                except Exception as e:
                    logger.warning("PiCam subprocess capture failed via %s: %s", cmd_name, e)
            return None

        if self._picam_mode == "cv2":
            ok, frame = self._picam.read()
            return frame if ok else None

        return None

    # -- Public sampling API -----------------------------------------------------
    def available_cameras(self):
        with self._links_lock:
            names = [n for n, link in self._links.items() if link.connected]
        if self._picam_mode is not None:
            names.append("PICAM")
        return names

    def sample(self, name, timeout=None):
        """Return one frame from the named camera, or None if unavailable/failed."""
        name = name.upper()
        if name == "PICAM":
            return self._capture_local()
        with self._links_lock:
            link = self._links.get(name)
        if link is None or not link.connected:
            return None
        return link.snap(timeout=timeout or self.config.SNAP_TIMEOUT_S)
