import multiprocessing as mp
import asyncio
import cv2
import numpy as np
import socket
import time
import json
import struct
import requests

# Load markers globally for the workers
try:
    with open("markers.json", "r") as f:
        KNOWN_MARKERS = {m["id"]: m for m in json.load(f)}
except FileNotFoundError:
    print("Warning: markers.json not found. Global localization will fail.")
    KNOWN_MARKERS = {}

# Pre-define ArUco parameters
ARUCO_DICT = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
ARUCO_PARAMS = cv2.aruco.DetectorParameters()
DETECTOR = cv2.aruco.ArucoDetector(ARUCO_DICT, ARUCO_PARAMS)

# Dummy camera matrix (Calibrate later for better Z-axis accuracy)
FOCAL_LENGTH = 800
CENTER = (320, 240)
CAMERA_MATRIX = np.array([
    [FOCAL_LENGTH, 0, CENTER[0]],
    [0, FOCAL_LENGTH, CENTER[1]],
    [0, 0, 1]
], dtype="double")
DIST_COEFFS = np.zeros((4,1))

MARKER_SIZE = 0.05 
HALF_SIZE = MARKER_SIZE / 2.0
OBJ_POINTS = np.array([
    [-HALF_SIZE, HALF_SIZE, 0],
    [HALF_SIZE, HALF_SIZE, 0],
    [HALF_SIZE, -HALF_SIZE, 0],
    [-HALF_SIZE, -HALF_SIZE, 0]
], dtype=np.float32)

# ---------------------------------------------------------
# CONSUMER: The Vision Workers
# ---------------------------------------------------------
def vision_worker(frame_queue):
    while True:
        cam_id, frame = frame_queue.get()
        if frame is None: break 
        
        corners, ids, rejected = DETECTOR.detectMarkers(frame)
        global_positions = []

        if ids is not None:
            for i in range(len(ids)):
                success, rvec, tvec = cv2.solvePnP(OBJ_POINTS, corners[i][0], CAMERA_MATRIX, DIST_COEFFS)
                if success:
                    marker_id = ids[i][0]
                    if marker_id in KNOWN_MARKERS:
                        R, _ = cv2.Rodrigues(rvec)
                        T_marker_to_cam = np.eye(4)
                        T_marker_to_cam[:3, :3] = R
                        T_marker_to_cam[:3, 3] = tvec.flatten()
                        
                        T_cam_to_marker = np.linalg.inv(T_marker_to_cam)
                        cam_local_x, cam_local_y, cam_local_z = T_cam_to_marker[:3, 3]
                        
                        global_x = cam_local_x + KNOWN_MARKERS[marker_id]["x"]
                        global_y = cam_local_y + KNOWN_MARKERS[marker_id]["y"]
                        global_z = cam_local_z + KNOWN_MARKERS[marker_id]["z"]
                        
                        global_positions.append([global_x, global_y, global_z])

        if global_positions:
            avg_pos = np.mean(global_positions, axis=0)
            try:
                requests.post("http://127.0.0.1:5000/api/localization", json={
                    "x": float(avg_pos[0]), 
                    "y": float(avg_pos[1]), 
                    "z": float(avg_pos[2]),
                    "markers_detected": len(global_positions)
                }, timeout=0.5)
            except requests.exceptions.RequestException:
                pass 

# ---------------------------------------------------------
# PRODUCER: Local Pi Camera
# ---------------------------------------------------------
def local_camera_producer(frame_queue):
    cap = cv2.VideoCapture(0)
    while True:
        ret, frame = cap.read()
        if ret and not frame_queue.full():
            frame_queue.put(("PI_CAM", frame))
        time.sleep(0.05) 

# ---------------------------------------------------------
# PRODUCER: ESP Camera Server (TCP) & Connection Tracker
# ---------------------------------------------------------
active_cameras = set()

async def handle_esp_client(reader, writer, frame_queue):
    global active_cameras
    client_ip = writer.get_extra_info('peername')[0]
    
    if client_ip not in active_cameras:
        active_cameras.add(client_ip)
        print(f"[NETWORK] New camera connected from IP: {client_ip}")

    try:
        length_bytes = await reader.readexactly(4)
        length = struct.unpack('<I', length_bytes)[0]
        img_data = await reader.readexactly(length)
        
        img_array = np.frombuffer(img_data, dtype=np.uint8)
        frame = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
        
        if frame is not None and not frame_queue.full():
            frame_queue.put((f"ESP_{client_ip}", frame))
            
    except Exception:
        pass 
    finally:
        writer.close()
        await writer.wait_closed()

async def run_tcp_server(frame_queue):
    tcp_server = await asyncio.start_server(
        lambda r, w: handle_esp_client(r, w, frame_queue), '0.0.0.0', 8888)
    print("[NETWORK] TCP Server listening on port 8888")
    async with tcp_server:
        await tcp_server.serve_forever()

def esp_server_process(frame_queue):
    asyncio.run(run_tcp_server(frame_queue))

# ---------------------------------------------------------
# ORCHESTRATOR: UDP Sync Broadcast
# ---------------------------------------------------------
def udp_trigger_loop(fps):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    
    delay = 1.0 / fps
    print(f"[NETWORK] Broadcasting UDP triggers on port 9999 at {fps} FPS")
    while True:
        sock.sendto(b"CAPTURE", ('<broadcast>', 9999))
        time.sleep(delay)

# ---------------------------------------------------------
# MAIN
# ---------------------------------------------------------
if __name__ == '__main__':
    TARGET_FPS = 10
    frame_queue = mp.Queue(maxsize=15)

    workers = [mp.Process(target=vision_worker, args=(frame_queue,)) for _ in range(3)]
    for w in workers: w.start()

    p_local_cam = mp.Process(target=local_camera_producer, args=(frame_queue,))
    p_local_cam.start()

    p_esp_server = mp.Process(target=esp_server_process, args=(frame_queue,))
    p_esp_server.start()

    p_udp = mp.Process(target=udp_trigger_loop, args=(TARGET_FPS,))
    p_udp.start()

    try:
        while True: time.sleep(1) 
    except KeyboardInterrupt:
        print("\nShutting down pipeline...")
        for w in workers: frame_queue.put(("QUIT", None))