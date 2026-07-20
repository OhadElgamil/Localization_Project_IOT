"""Camera intrinsic calibration using a regular chessboard, driven live over
the same TCP link the ESP32-CAM firmware speaks.

Wire protocol (matches ESP_EYE/send_pictures_on_command/send_pictures_on_command.ino
and pipeline/camera_link.py):
  1. Camera connects to this script and sends "ID:<NAME>\n" then "READY\n".
  2. This script sends "SNAP\n" whenever it wants a frame.
  3. Camera replies with a decimal length line ("12345\n") followed by
     exactly that many bytes of JPEG data.

Controls (type into the terminal running this script):
  E - request and save a frame for calibration
  S - stop capturing and run calibration on the collected images
  Q - quit without calibrating
"""
import argparse
import os
import select
import socket
import sys
import termios
import tty

import cv2
import numpy as np

# Board is a regular (non-ArUco) chessboard, 6x15 squares, 16mm per square.
# cv2 counts *inner corners*, i.e. one less than the square count per side.
CHESSBOARD_CORNERS = (14, 5)  # (corners along the 15-square side, 6-square side)
SQUARE_SIZE_M = 0.016  # 16 mm


def recv_line(conn):
    line = bytearray()
    while True:
        b = conn.recv(1)
        if not b:
            raise ConnectionError("camera disconnected")
        if b == b"\n":
            break
        line += b
    return line.decode("ascii", errors="ignore").strip()


def recv_exact(conn, n):
    data = bytearray()
    while len(data) < n:
        chunk = conn.recv(n - len(data))
        if not chunk:
            raise ConnectionError("camera disconnected")
        data += chunk
    return bytes(data)


def wait_for_camera(port):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("0.0.0.0", port))
    sock.listen(1)
    print(f"Waiting for camera to connect on port {port}...")
    conn, addr = sock.accept()
    sock.close()

    line = recv_line(conn)
    name = line[3:].strip() if line.startswith("ID:") else "UNKNOWN"

    # ESP_EYE firmware sends a second "READY\n" line right after the ID
    # line; drain it if present so it isn't mistaken for a SNAP response later.
    conn.settimeout(0.5)
    try:
        extra = recv_line(conn)
        if extra.upper() != "READY":
            print(f"Unexpected line after handshake: {extra!r}")
    except socket.timeout:
        pass
    conn.settimeout(None)

    print(f"Camera '{name}' connected from {addr[0]}")
    return conn


def snap(conn):
    conn.sendall(b"SNAP\n")
    length = int(recv_line(conn))
    data = recv_exact(conn, length)
    arr = np.frombuffer(data, dtype=np.uint8)
    return cv2.imdecode(arr, cv2.IMREAD_COLOR)


def safe_print(message):
    # In raw terminal mode \n alone doesn't return the cursor to column 0.
    sys.stdout.write(message.replace("\n", "\r\n") + "\r\n")
    sys.stdout.flush()


def capture_loop(conn, img_dir):
    os.makedirs(img_dir, exist_ok=True)
    count = 0
    safe_print("\nPress 'e' to capture an image, 's' to stop and calibrate, 'q' to quit.")

    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        while True:
            ready, _, _ = select.select([sys.stdin], [], [], 0.5)
            if not ready:
                continue
            char = sys.stdin.read(1)

            if char in ("e", "E"):
                safe_print("'e' received - requesting image from camera, please wait...")
                frame = snap(conn)
                if frame is None:
                    safe_print("Failed to grab frame, try again.")
                    continue
                path = os.path.join(img_dir, f"calib_{count:03d}.jpg")
                cv2.imwrite(path, frame)
                count += 1
                safe_print(f"Saved {path} ({count} total)")
            elif char in ("s", "S"):
                safe_print(f"Stopping capture with {count} images.")
                break
            elif char in ("q", "Q", "\x03"):
                safe_print("Quitting without calibrating.")
                count = None
                break
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)

    return count


def calibrate(img_dir, save_path):
    objp = np.zeros((CHESSBOARD_CORNERS[0] * CHESSBOARD_CORNERS[1], 3), np.float32)
    objp[:, :2] = np.mgrid[0:CHESSBOARD_CORNERS[0], 0:CHESSBOARD_CORNERS[1]].T.reshape(-1, 2)
    objp *= SQUARE_SIZE_M

    obj_points = []
    img_points = []
    used_filenames = []
    img_shape = None

    images = sorted(f for f in os.listdir(img_dir) if f.lower().endswith(".jpg"))
    if not images:
        print("No images to calibrate with.")
        return

    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.001)

    for fname in images:
        path = os.path.join(img_dir, fname)
        img = cv2.imread(path)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        img_shape = gray.shape[::-1]

        found, corners = cv2.findChessboardCorners(gray, CHESSBOARD_CORNERS, None)
        if not found:
            print(f"[SKIP] {fname}: chessboard not found")
            continue

        corners = cv2.cornerSubPix(gray, corners, (11, 11), (-1, -1), criteria)
        obj_points.append(objp)
        img_points.append(corners)
        used_filenames.append(fname)
        print(f"[OK] {fname}")

    if len(obj_points) < 3:
        print(f"Only {len(obj_points)} usable images, need at least 3. Aborting.")
        return

    print(f"\n{len(obj_points)}/{len(images)} images usable. Calculating camera parameters...")

    ret, camera_matrix, dist_coeffs, rvecs, tvecs = cv2.calibrateCamera(
        obj_points, img_points, img_shape, None, None, flags=cv2.CALIB_FIX_K3
    )
        
    per_image = []
    for i in range(len(obj_points)):
        projected, _ = cv2.projectPoints(
            obj_points[i], rvecs[i], tvecs[i], camera_matrix, dist_coeffs
        )
        projected = projected.reshape(-1, 2)
        observed = img_points[i].reshape(-1, 2)
        # RMS error for this image
        err = np.sqrt(np.mean(np.sum((projected - observed) ** 2, axis=1)))
        per_image.append((used_filenames[i], err))

    # sort worst-first so the offenders are obvious
    for fname, err in sorted(per_image, key=lambda x: -x[1]):
        flag = "  <-- DROP" if err > 2 * ret else ""
        print(f"  image {fname}: {err:.4f} px{flag}")    
    

    print("\n--- Calibration Result ---")
    print("Camera Matrix (Intrinsic Parameters):")
    print(camera_matrix)
    print("\nDistortion Coefficients:")
    print(dist_coeffs)
    print(f"\nMean reprojection error: {ret:.4f} px")

    np.savez(save_path, camera_matrix=camera_matrix, dist_coeffs=dist_coeffs, img_shape=img_shape)
    print(f"\nSaved calibration data to {save_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Single camera intrinsic calibration using a regular chessboard, "
                     "captured live over the ESP32-CAM TCP link"
    )
    parser.add_argument("--port", type=int, default=5000,
                         help="TCP port to listen on (matches pi_port in the ESP32 firmware)")
    parser.add_argument("--img_dir", type=str, default="./calib_images",
                         help="Directory to save captured images")
    parser.add_argument("--save_path", type=str, default="calibration_data.npz",
                         help="Output file for calibration results")
    args = parser.parse_args()

    conn = wait_for_camera(args.port)
    try:
        count = capture_loop(conn, args.img_dir)
    finally:
        conn.close()

    calibrate(args.img_dir, args.save_path)


if __name__ == "__main__":
    main()
