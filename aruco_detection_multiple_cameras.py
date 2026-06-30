import cv2
import numpy as np
import argparse
import server # Import your existing server module
import json

def main():
    parser = argparse.ArgumentParser(description="ArUco Marker Pose Estimator")
    parser.add_argument("image", help="Path to the image file")
    parser.add_argument("marker_size", type=float, help="Size of the marker in meters (e.g., 0.05 for 5cm)")
    args = parser.parse_args()

    # Load the image
    img = cv2.imread(args.image)
    if img is None:
        print("Error: Could not load the image.")
        return

    # Approximate camera parameters
    focal_length = img.shape[1]
    center = (img.shape[1]/2, img.shape[0]/2)
    camera_matrix = np.array([
        [focal_length, 0, center[0]],
        [0, focal_length, center[1]],
        [0, 0, 1]
    ], dtype="double")
    dist_coeffs = np.zeros((4,1))

    # Define ArUco dictionary and detector
    dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
    parameters = cv2.aruco.DetectorParameters()
    detector = cv2.aruco.ArucoDetector(dictionary, parameters)

    # Detect the markers
    corners, ids, rejected = detector.detectMarkers(img)

    if ids is not None:
        print(f"Found {len(ids)} markers:")
        half_size = args.marker_size / 2.0
        obj_points = np.array([
            [-half_size, half_size, 0],
            [half_size, half_size, 0],
            [half_size, -half_size, 0],
            [-half_size, -half_size, 0]
        ], dtype=np.float32)

        # (Load your markers.json somewhere at the top of your script)
        # with open("markers.json", "r") as f:
        #     known_markers = {m["id"]: m for m in json.load(f)}

        global_positions = []

        for i in range(len(ids)):
            success, rvec, tvec = cv2.solvePnP(obj_points, corners[i][0], camera_matrix, dist_coeffs)
            if success:
                marker_id = ids[i][0]
                
                # 1. Convert rotation vector (rvec) to a 3x3 rotation matrix
                R, _ = cv2.Rodrigues(rvec)
                
                # 2. Build the 4x4 transformation matrix (Marker -> Camera)
                T_marker_to_cam = np.eye(4)
                T_marker_to_cam[:3, :3] = R
                T_marker_to_cam[:3, 3] = tvec.flatten()
                
                # 3. Invert the matrix to get Camera -> Marker
                T_cam_to_marker = np.linalg.inv(T_marker_to_cam)
                
                # 4. Extract the Pi's local X, Y, Z relative to this specific marker
                cam_local_x, cam_local_y, cam_local_z = T_cam_to_marker[:3, 3]
                
                # 5. Convert to Global Room Coordinates
                # (Requires adding the marker's known global position from markers.json)
                # if marker_id in known_markers:
                #     global_x = cam_local_x + known_markers[marker_id]["x"]
                #     global_y = cam_local_y + known_markers[marker_id]["y"]
                #     global_z = cam_local_z + known_markers[marker_id]["z"]
                #     global_positions.append([global_x, global_y, global_z])

        if global_positions:
        # Average the coordinates (Pose Fusion)
        avg_pos = np.mean(global_positions, axis=0)
        
        print(f"Fused Global Location: X={avg_pos[0]:.3f}, Y={avg_pos[1]:.3f}, Z={avg_pos[2]:.3f}")
        
        # Push to your Flask server
        server.update_localization(
            x=avg_pos[0],
            y=avg_pos[1],
            z=avg_pos[2],
            markers_detected=len(global_positions)
        )
    else:
        print("No ArUco markers found in the image.")

if __name__ == "__main__":
    main()