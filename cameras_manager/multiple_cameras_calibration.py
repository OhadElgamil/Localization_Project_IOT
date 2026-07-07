import socket
import subprocess
import threading
import sys
import select
import termios
import tty
import time
import os

HOST = '0.0.0.0'
PORT = 5000
WIDTH = "640"
HEIGHT = "480"
QUALITY = "75"

# Global shared variables for the network thread and inputs
running = True

# Thread-safe dictionary to hold N cameras
# Format: {'esp_192_168_1_10': {'conn': socket, 'rfile': rfile, 'count': 0}}
esp_clients = {}
clients_lock = threading.Lock()

# Pi camera counter
pi_photo_count = 0

# Ensure the root and pi camera directories exist
os.makedirs("./calib_images/pi_camera", exist_ok=True)

def safe_print(message):
    """Prints messages safely in raw mode by ensuring carriage return."""
    sys.stdout.write(message.replace('\n', '\r\n') + '\r\n')
    sys.stdout.flush()

def capture_pi_camera(count, on_complete_cb=None):
    """Captures an image using the local Pi camera."""
    filename = f"./calib_images/pi_camera/pi_photo_{count}.jpg"
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

def capture_esp_camera(cam_id, on_complete_cb=None):
    """Triggers and receives an image from a specific connected ESP32-CAM."""
    with clients_lock:
        if cam_id not in esp_clients:
            safe_print(f"[{cam_id}] Cannot capture, camera not in active list.")
            if on_complete_cb: on_complete_cb()
            return
        
        client = esp_clients[cam_id]
        conn = client['conn']
        rfile = client['rfile']
        
        # Increment and grab the target photo count
        client['count'] += 1
        count = client['count']

    try:
        # 1. Send SNAP command
        conn.sendall(b"SNAP\n")

        # 2. Read image size
        size_line = rfile.readline().decode('utf-8').strip()
        if not size_line:
            safe_print(f"[{cam_id}] Connection closed by device.")
            close_esp_connection(cam_id)
            if on_complete_cb: on_complete_cb()
            return

        image_len = int(size_line)
        
        # 3. Read image data
        image_data = rfile.read(image_len)
        
        # 4. Save image if complete
        if len(image_data) == image_len:
            filename = f"./calib_images/{cam_id}/{count}.jpg"
            with open(filename, "wb") as f:
                f.write(image_data)
            safe_print(f"[{cam_id}] Success! Saved as {filename}")
        else:
            safe_print(f"[{cam_id}] Error: Incomplete image received.")
            close_esp_connection(cam_id)

    except (socket.error, ValueError) as e:
        safe_print(f"[{cam_id}] Connection error during capture: {e}")
        close_esp_connection(cam_id)
    finally:
        if on_complete_cb:
            on_complete_cb()

def close_esp_connection(cam_id):
    """Safely closes an active ESP32 connection by its ID."""
    with clients_lock:
        if cam_id in esp_clients:
            try:
                esp_clients[cam_id]['conn'].close()
            except:
                pass
            del esp_clients[cam_id]
            safe_print(f"[{cam_id}] Camera disconnected.")

def handle_esp_connection(s):
    """Background thread to manage incoming ESP32-CAM connections."""
    global running
    while running:
        try:
            # Short timeout allows the loop to check 'running' state regularly
            s.settimeout(1.0) 
            conn, addr = s.accept()
            
            cam_id = f"esp_{addr[0].replace('.', '_')}" # e.g., esp_192_168_1_10

            conn.settimeout(5.0)
            rfile = conn.makefile('rb')
            ready_line = rfile.readline().decode('utf-8').strip()

            if "READY" in ready_line:
                conn.settimeout(None)
                
                # Create dedicated directory for this camera
                os.makedirs(f"./calib_images/{cam_id}", exist_ok=True)
                
                with clients_lock:
                    esp_clients[cam_id] = {
                        'conn': conn,
                        'rfile': rfile,
                        'count': 0
                    }
                    
                safe_print(f"\n[{cam_id}] Camera connected successfully (Ready).")
                safe_print("[System] Ready for next command...")
            else:
                conn.close()
        except socket.timeout:
            continue
        except Exception:
            pass

def run_server():
    global running, pi_photo_count

    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((HOST, PORT))
        s.listen()

        safe_print(f"Server listening on port {PORT}...")
        safe_print("Controls: [Space] All Cams, [p] Pi Only, [e] ESPs Only, [r] Reset. Press Ctrl+C to exit.\n")
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
                        safe_print("\n[System] Capturing photo with ALL cameras...")
                        pi_photo_count += 1
                        
                        with clients_lock:
                            active_cam_ids = list(esp_clients.keys())

                        total_tasks = 1 + len(active_cam_ids) # 1 Pi + N ESPs
                        completed_cameras = 0
                        
                        def wait_for_all_cb():
                            nonlocal completed_cameras
                            completed_cameras += 1
                            if completed_cameras == total_tasks:
                                safe_print("[System] Ready for next command...")

                        # Trigger Pi
                        threading.Thread(target=capture_pi_camera, args=(pi_photo_count, wait_for_all_cb)).start()
                        
                        # Trigger all ESPs
                        for cid in active_cam_ids:
                            threading.Thread(target=capture_esp_camera, args=(cid, wait_for_all_cb)).start()

                    elif char == 'p' or char == 'P':
                        safe_print("\n[System] Capturing photo with Pi Camera...")
                        pi_photo_count += 1
                        threading.Thread(target=capture_pi_camera, args=(pi_photo_count, lambda: safe_print("[System] Ready for next command..."))).start()

                    elif char == 'e' or char == 'E':
                        safe_print("\n[System] Capturing photo with ALL ESP32-CAMs...")
                        
                        with clients_lock:
                            active_cam_ids = list(esp_clients.keys())

                        if not active_cam_ids:
                            safe_print("[System] Cannot capture, no ESP cameras are connected.")
                            safe_print("[System] Ready for next command...")
                        else:
                            total_tasks = len(active_cam_ids)
                            completed_cameras = 0
                            
                            def wait_for_esps_cb():
                                nonlocal completed_cameras
                                completed_cameras += 1
                                if completed_cameras == total_tasks:
                                    safe_print("[System] Ready for next command...")
                            
                            for cid in active_cam_ids:
                                threading.Thread(target=capture_esp_camera, args=(cid, wait_for_esps_cb)).start()

                    elif char == 'r' or char == 'R':
                        safe_print("\n[System] Resetting counters and sending DISCONNECT to all ESP32s...")
                        pi_photo_count = 0
                        
                        with clients_lock:
                            active_cam_ids = list(esp_clients.keys())
                        
                        for cid in active_cam_ids:
                            try:
                                esp_clients[cid]['conn'].sendall(b"DISCONNECT\n")
                                time.sleep(0.1) 
                            except:
                                pass
                            close_esp_connection(cid)
                            
                        safe_print("[System] Counters reset and ESPs disconnected.")
                        safe_print("[System] Ready for next command...")

        except KeyboardInterrupt:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
            print("\nShutting down server...")
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
            running = False

if __name__ == "__main__":
    run_server()
