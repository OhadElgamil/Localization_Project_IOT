import socket
import subprocess
import threading
import sys
import select
import termios
import tty
import time

HOST = '0.0.0.0'
PORT = 5000
WIDTH = "800"
HEIGHT = "600"
QUALITY = "75"

# Thread-safe dictionary to track multiple connected cameras: { "ID": (conn, rfile) }
cameras = {}
cameras_lock = threading.Lock()

running = True

# Separate photo counters for each camera type
pi_photo_count = 0
esp_photo_count = 0

def safe_print(message):
    """Prints messages safely in raw mode by ensuring carriage return."""
    sys.stdout.write(message.replace('\n', '\r\n') + '\r\n')
    sys.stdout.flush()

def capture_pi_camera(count, on_complete_cb=None):
    """Captures an image using the local Pi camera without opening a preview window."""
    filename = f"pi_photo_{count}.jpg"
    try:
        try:
            subprocess.run(["rpicam-still", "-o", filename, "-t", "100", "--immediate", "--nopreview", 
                            "--width", WIDTH, "--height", HEIGHT],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        except FileNotFoundError:
            subprocess.run(["libcamera-still", "-o", filename, "-t", "100", "--immediate", "--nopreview",
                            "--width", WIDTH, "--height", HEIGHT],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

        safe_print(f"[Pi Camera] Success! Saved as {filename}")
    except Exception as e:
        safe_print(f"[Pi Camera] Capture failed: {e}")
    finally:
        if on_complete_cb:
            on_complete_cb()

def capture_esp_camera(cam_id, conn, rfile, count, on_complete_cb=None):
    """Triggers and receives an image from a specific connected ESP32-CAM."""
    try:
        # 1. Send SNAP command
        conn.sendall(b"SNAP\n")

        # 2. Read image size
        size_line = rfile.readline().decode('utf-8').strip()
        if not size_line:
            safe_print(f"[ESP32-CAM - {cam_id}] Connection closed by device.")
            close_esp_connection(cam_id)
            return

        image_len = int(size_line)
        
        # 3. Read image data
        safe_print(f"Reading image from {cam_id}...")
        image_data = rfile.read(image_len)
        
        # 4. Save image if complete
        if len(image_data) == image_len:
            filename = f"./{cam_id}_{count}.jpg"
            with open(filename, "wb") as f:
                f.write(image_data)
            safe_print(f"[ESP32-CAM - {cam_id}] Success! Saved as {filename}")
        else:
            safe_print(f"[ESP32-CAM - {cam_id}] Error: Incomplete image received.")
            close_esp_connection(cam_id)

    except (socket.error, ValueError) as e:
        safe_print(f"[ESP32-CAM - {cam_id}] Connection error during capture: {e}")
        close_esp_connection(cam_id)
    finally:
        if on_complete_cb:
            on_complete_cb()

def close_esp_connection(cam_id):
    """Safely closes and removes a specific ESP32 connection."""
    with cameras_lock:
        if cam_id in cameras:
            conn, rfile = cameras[cam_id]
            try:
                conn.close()
            except:
                pass
            del cameras[cam_id]
            safe_print(f"[ESP32-CAM - {cam_id}] Camera disconnected.")

def handle_esp_connection(s):
    """Background thread to manage incoming ESP32-CAM connections."""
    global running
    while running:
        try:
            conn, addr = s.accept()
            conn.settimeout(5.0)
            rfile = conn.makefile('rb')
            
            # Read the ID line, then the READY line
            id_line = rfile.readline().decode('utf-8').strip()
            ready_line = rfile.readline().decode('utf-8').strip()

            if id_line.startswith("ID:") and "READY" in ready_line:
                conn.settimeout(None)
                cam_id = id_line.split(":")[1] # "RIGHT", "LEFT", "FRONT"
                
                with cameras_lock:
                    # Clean up old connection if same camera ID reconnects
                    if cam_id in cameras:
                        try:
                            cameras[cam_id][0].close()
                        except:
                            pass
                    cameras[cam_id] = (conn, rfile)
                
                safe_print(f"\n[ESP32-CAM] Camera {cam_id} connected successfully from {addr[0]}.")
                safe_print("[System] Ready for next command...")
            else:
                conn.close()
        except Exception:
            pass

def run_server():
    global running, pi_photo_count, esp_photo_count

    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((HOST, PORT))
        s.listen()

        safe_print(f"Server listening on port {PORT}...")
        safe_print("Controls: [Space] Both, [p] Pi Only, [e] ESPs Only, [r] Reset. Press Ctrl+C to exit.\n")
        safe_print("[System] Ready for next command...")

        conn_thread = threading.Thread(target=handle_esp_connection, args=(s,), daemon=True)
        conn_thread.start()

        try:
            tty.setraw(fd)

            while running:
                ready_to_read, _, _ = select.select([sys.stdin], [], [], 0.5)

                if ready_to_read:
                    char = sys.stdin.read(1)

                    if char == '\x03':  # Ctrl+C
                        raise KeyboardInterrupt

                    if char == ' ':
                        safe_print("\n[System] Capturing photo with BOTH Pi and all connected ESP cameras...")
                        pi_photo_count += 1
                        
                        with cameras_lock:
                            connected_cams = list(cameras.items())
                        
                        if connected_cams:
                            esp_photo_count += 1
                            total_operations = 1 + len(connected_cams)
                            completed_ops = 0
                            
                            def make_callback():
                                def callback():
                                    nonlocal completed_ops
                                    completed_ops += 1
                                    if completed_ops == total_operations:
                                        safe_print("[System] Ready for next command...")
                                return callback

                            cb = make_callback()
                            threading.Thread(target=capture_pi_camera, args=(pi_photo_count, cb)).start()
                            for cam_id, (conn, rfile) in connected_cams:
                                threading.Thread(target=capture_esp_camera, args=(cam_id, conn, rfile, esp_photo_count, cb)).start()
                        else:
                            threading.Thread(target=capture_pi_camera, args=(pi_photo_count, lambda: safe_print("[System] Ready for next command..."))).start()
                            safe_print("[ESP32-CAM] Cannot capture ESP, no cameras connected.")

                    elif char in ('p', 'P'):
                        safe_print("\n[System] Capturing photo with Pi Camera...")
                        pi_photo_count += 1
                        threading.Thread(target=capture_pi_camera, args=(pi_photo_count, lambda: safe_print("[System] Ready for next command..."))).start()

                    elif char in ('e', 'E'):
                        with cameras_lock:
                            connected_cams = list(cameras.items())
                            
                        if connected_cams:
                            safe_print("\n[System] Capturing photo with all connected ESP32-CAMs...")
                            esp_photo_count += 1
                            total_operations = len(connected_cams)
                            completed_ops = 0
                            
                            def make_callback():
                                def callback():
                                    nonlocal completed_ops
                                    completed_ops += 1
                                    if completed_ops == total_operations:
                                        safe_print("[System] Ready for next command...")
                                return callback
                                
                            cb = make_callback()
                            for cam_id, (conn, rfile) in connected_cams:
                                threading.Thread(target=capture_esp_camera, args=(cam_id, conn, rfile, esp_photo_count, cb)).start()
                        else:
                            safe_print("[ESP32-CAM] Cannot capture, no cameras connected.")
                            safe_print("[System] Ready for next command...")

                    elif char in ('r', 'R'):
                        safe_print("\n[System] Resetting counters and disconnecting all ESP32s...")
                        pi_photo_count = 0
                        esp_photo_count = 0
                        
                        with cameras_lock:
                            active_cam_ids = list(cameras.keys())
                            
                        for cam_id in active_cam_ids:
                            with cameras_lock:
                                conn = cameras.get(cam_id, (None, None))[0]
                            if conn:
                                try:
                                    conn.sendall(b"DISCONNECT\n")
                                    time.sleep(0.05)
                                except:
                                    pass
                            close_esp_connection(cam_id)
                            
                        safe_print("[System] Reset complete. Ready for next command...")

        except KeyboardInterrupt:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
            print("\nShutting down server...")
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
            running = False

if __name__ == "__main__":
    run_server()