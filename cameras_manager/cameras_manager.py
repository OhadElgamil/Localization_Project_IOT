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

# Global shared variables for the network thread and inputs
esp_conn = None
esp_rfile = None
running = True

# Separate photo counters for each camera
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
            subprocess.run(["rpicam-still", "-o", filename, "-t", "100", "--immediate", "--nopreview"], 
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        except FileNotFoundError:
            subprocess.run(["libcamera-still", "-o", filename, "-t", "100", "--immediate", "--nopreview"], 
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            
        safe_print(f"[Pi Camera] Success! Saved as {filename}")
    except Exception as e:
        safe_print(f"[Pi Camera] Capture failed: {e}")
    finally:
        if on_complete_cb:
            on_complete_cb()

def capture_esp_camera(count, on_complete_cb=None):
    """Triggers and receives an image from the connected ESP32-CAM."""
    global esp_conn, esp_rfile
    if not esp_conn:
        safe_print("[ESP32-CAM] Cannot capture, camera is not connected.")
        if on_complete_cb:
            on_complete_cb()
        return

    try:
        # 1. Send SNAP command
        esp_conn.sendall(b"SNAP\n")
        
        # 2. Read image size
        size_line = esp_rfile.readline().decode('utf-8').strip()
        if not size_line:
            safe_print("[ESP32-CAM] Connection closed by device.")
            close_esp_connection()
            return

        image_len = int(size_line)
        
        # 3. Read image data
        image_data = b""
        bytes_remaining = image_len

        while bytes_remaining > 0:
            chunk = esp_conn.recv(min(4096, bytes_remaining))
            if not chunk:
                break
            image_data += chunk
            bytes_remaining -= len(chunk)

        # 4. Save image if complete
        if len(image_data) == image_len:
            filename = f"esp_photo_{count}.jpg"
            with open(filename, "wb") as f:
                f.write(image_data)
            safe_print(f"[ESP32-CAM] Success! Saved as {filename}")
        else:
            safe_print("[ESP32-CAM] Error: Incomplete image received.")
            close_esp_connection()

    except (socket.error, ValueError) as e:
        safe_print(f"[ESP32-CAM] Connection error during capture: {e}")
        close_esp_connection()
    finally:
        if on_complete_cb:
            on_complete_cb()

def close_esp_connection():
    """Safely closes the active ESP32 connection."""
    global esp_conn, esp_rfile
    if esp_conn:
        try:
            esp_conn.close()
        except:
            pass
        esp_conn = None
        esp_rfile = None
        safe_print("[ESP32-CAM] Camera disconnected.")

def handle_esp_connection(s):
    """Background thread to manage incoming ESP32-CAM connections."""
    global esp_conn, esp_rfile, running
    while running:
        try:
            conn, addr = s.accept()
            
            conn.settimeout(5.0)
            rfile = conn.makefile('rb')
            ready_line = rfile.readline().decode('utf-8').strip()
            
            if "READY" in ready_line:
                conn.settimeout(None)
                esp_conn = conn
                esp_rfile = rfile
                safe_print(f"\n[ESP32-CAM] Camera connected successfully from {addr[0]} (Ready).")
                safe_print("[System] Ready for next command...")
            else:
                conn.close()
        except Exception:
            pass

def run_server():
    global running, pi_photo_count, esp_photo_count, esp_conn
    
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((HOST, PORT))
        s.listen()
        
        safe_print(f"Server listening on port {PORT}...")
        safe_print("Controls: [Space] Both, [p] Pi Only, [e] ESP Only, [r] Reset. Press Ctrl+C to exit.\n")
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
                        safe_print("\n[System] Capturing photo with BOTH cameras...")
                        pi_photo_count += 1
                        
                        if esp_conn:
                            esp_photo_count += 1
                            completed_cameras = 0
                            def wait_for_both_cb():
                                nonlocal completed_cameras
                                completed_cameras += 1
                                if completed_cameras == 2:
                                    safe_print("[System] Ready for next command...")

                            threading.Thread(target=capture_pi_camera, args=(pi_photo_count, wait_for_both_cb)).start()
                            threading.Thread(target=capture_esp_camera, args=(esp_photo_count, wait_for_both_cb)).start()
                        else:
                            threading.Thread(target=capture_pi_camera, args=(pi_photo_count, lambda: safe_print("[System] Ready for next command..."))).start()
                            safe_print("[ESP32-CAM] Cannot capture, camera is not connected.")
                            
                    elif char == 'p' or char == 'P':
                        safe_print("\n[System] Capturing photo with Pi Camera...")
                        pi_photo_count += 1
                        threading.Thread(target=capture_pi_camera, args=(pi_photo_count, lambda: safe_print("[System] Ready for next command..."))).start()
                        
                    elif char == 'e' or char == 'E':
                        safe_print("\n[System] Capturing photo with ESP32-CAM...")
                        if esp_conn:
                            esp_photo_count += 1
                            threading.Thread(target=capture_esp_camera, args=(esp_photo_count, lambda: safe_print("[System] Ready for next command..."))).start()
                        else:
                            safe_print("[ESP32-CAM] Cannot capture, camera is not connected.")
                            safe_print("[System] Ready for next command...")

                    elif char == 'r' or char == 'R':
                        safe_print("\n[System] Resetting counters and sending DISCONNECT to ESP32...")
                        pi_photo_count = 0
                        esp_photo_count = 0
                        
                        if esp_conn:
                            try:
                                # Send explicit disconnect command to the ESP32
                                esp_conn.sendall(b"DISCONNECT\n")
                                time.sleep(0.2)  # Give ESP32 a brief moment to process the line
                            except:
                                pass
                            close_esp_connection()
                        else:
                            safe_print("[System] Counters reset. No active ESP connection.")
                            safe_print("[System] Ready for next command...")

        except KeyboardInterrupt:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
            print("\nShutting down server...")
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
            running = False

if __name__ == "__main__":
    run_server()