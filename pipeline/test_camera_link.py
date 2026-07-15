"""Unit tests for EspCameraLink's timeout handling.

Uses a real loopback socket pair (socket.socketpair()) as a stand-in for the
ESP32-CAM's TCP connection, so these exercise the actual wire-protocol
parsing (readline + fixed-length read), not a mocked version of it.

Run with: python -m unittest test_camera_link -v
"""
import socket
import threading
import time
import unittest

import cv2
import numpy as np

from camera_link import EspCameraLink


def _make_jpeg_bytes():
    img = np.zeros((10, 10, 3), dtype=np.uint8)
    ok, buf = cv2.imencode(".jpg", img)
    assert ok
    return buf.tobytes()


class TestEspCameraLinkTimeout(unittest.TestCase):

    def test_timeout_does_not_disconnect_and_resumes_correctly(self):
        """A slow camera must be skipped for one cycle, not kicked -- and
        the late response that eventually arrives must be read correctly on
        the next call instead of desyncing the stream."""
        server_sock, client_sock = socket.socketpair()
        self.addCleanup(server_sock.close)
        link = EspCameraLink("FRONT", client_sock, ("127.0.0.1", 0))
        self.addCleanup(link.close)

        # First snap(): the fake camera never answers -- must time out
        # without dropping the connection.
        frame = link.snap(timeout=0.2)
        self.assertIsNone(frame)
        self.assertTrue(link.connected)

        # Exactly one SNAP command should have reached the "camera".
        server_sock.settimeout(1.0)
        cmd = b""
        while not cmd.endswith(b"\n"):
            cmd += server_sock.recv(1)
        self.assertEqual(cmd, b"SNAP\n")

        jpeg = _make_jpeg_bytes()

        def respond_late():
            time.sleep(0.1)
            server_sock.sendall(f"{len(jpeg)}\n".encode("ascii") + jpeg)

        threading.Thread(target=respond_late, daemon=True).start()

        # Second snap() must resume waiting on the SAME outstanding
        # response (no second SNAP sent) and parse it correctly once it
        # arrives.
        frame2 = link.snap(timeout=1.0)
        self.assertIsNotNone(frame2)
        self.assertEqual(frame2.shape[:2], (10, 10))
        self.assertTrue(link.connected)
        self.assertIsNotNone(link.last_response_time_s)

        # Confirm no second "SNAP\n" was ever sent to the camera side.
        server_sock.settimeout(0.1)
        with self.assertRaises(socket.timeout):
            server_sock.recv(1)

    def test_partial_data_preserved_across_timeout(self):
        """Bytes already received before a timeout fires must not be
        discarded -- only the remaining wait should repeat, not the whole
        response."""
        server_sock, client_sock = socket.socketpair()
        self.addCleanup(server_sock.close)
        link = EspCameraLink("FRONT", client_sock, ("127.0.0.1", 0))
        self.addCleanup(link.close)

        jpeg = _make_jpeg_bytes()
        header = f"{len(jpeg)}\n".encode("ascii")
        half = len(jpeg) // 2

        def respond_in_two_parts():
            cmd = b""
            while not cmd.endswith(b"\n"):
                cmd += server_sock.recv(1)
            server_sock.sendall(header + jpeg[:half])
            time.sleep(0.2)
            server_sock.sendall(jpeg[half:])

        threading.Thread(target=respond_in_two_parts, daemon=True).start()

        # First call: receives the header + first half, then times out
        # still short of the full payload.
        frame = link.snap(timeout=0.1)
        self.assertIsNone(frame)
        self.assertTrue(link.connected)

        # Second call: must not re-send SNAP or re-read the header, just
        # finish reading the remaining bytes.
        frame2 = link.snap(timeout=1.0)
        self.assertIsNotNone(frame2)
        self.assertEqual(frame2.shape[:2], (10, 10))

        server_sock.settimeout(0.1)
        with self.assertRaises(socket.timeout):
            server_sock.recv(1)

    def test_repeated_timeouts_still_never_disconnect(self):
        server_sock, client_sock = socket.socketpair()
        self.addCleanup(server_sock.close)
        link = EspCameraLink("FRONT", client_sock, ("127.0.0.1", 0))
        self.addCleanup(link.close)

        for _ in range(5):
            frame = link.snap(timeout=0.05)
            self.assertIsNone(frame)
            self.assertTrue(link.connected)

        # Still exactly one SNAP command sent across all 5 attempts.
        server_sock.settimeout(0.2)
        cmd = b""
        while not cmd.endswith(b"\n"):
            cmd += server_sock.recv(1)
        self.assertEqual(cmd, b"SNAP\n")
        server_sock.settimeout(0.1)
        with self.assertRaises(socket.timeout):
            server_sock.recv(1)

    def test_real_disconnect_still_drops_the_link(self):
        """A genuine closed connection (not a mere timeout) must still be
        treated as a real failure and drop the link."""
        server_sock, client_sock = socket.socketpair()
        link = EspCameraLink("FRONT", client_sock, ("127.0.0.1", 0))
        self.addCleanup(link.close)

        server_sock.close()  # camera vanished

        frame = link.snap(timeout=0.5)
        self.assertIsNone(frame)
        self.assertFalse(link.connected)


if __name__ == "__main__":
    unittest.main(verbosity=2)
