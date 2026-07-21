import cv2
import numpy as np
import argparse
import server # Import your existing server module
import json

def main():
    parser = argparse.ArgumentParser(description="ArUco Marker Pose Estimator")
    parser.add_argument("image", help="Path to the image file")
    parser.add_argument("marker_size", type=float, help="Size of the marker in meters (e.g., 0.05 for 5cm)")
    parser.add_argument("--name", type=str, help="Name of the camera (e.g., FRONT, LEFT, RIGHT, PI)")
    parser.add_argument("--calib", type=str, default=None, help="Path to calibration data file (overrides --name)")
    parser.add_argument("--uncalib", action="store_true", help="Force using the default camera matrix guess instead of calibration data")
    args = parser.parse_args()

    # Determine calibration path
    calib_path = "calibration_data.npz"
    if args.calib:
        calib_path = args.calib
    elif args.name:
        cam_id = "PI" if args.name.upper() == "PICAM" else args.name.upper()
        import os
        calib_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pipeline", "calibration_data", f"calibration_data_{cam_id}.npz")

    # Load the image
    img = cv2.imread(args.image)
    if img is None:
        print("Error: Could not load the image.")
        return

    import os
    # Load actual calibration data if available and not forced to bypass
    if not args.uncalib and os.path.exists(calib_path):
        print(f"Loading calibration from {calib_path}")
        data = np.load(calib_path)
        camera_matrix = data["camera_matrix"]
        dist_coeffs = data["dist_coeffs"]
        
        # Check resolution if img_shape is saved
        if "img_shape" in data:
            calib_shape = data["img_shape"]  # (width, height)
            current_shape = (img.shape[1], img.shape[0])
            if calib_shape[0] != current_shape[0] or calib_shape[1] != current_shape[1]:
                print(f"Warning: Image resolution {current_shape} does not match calibration resolution {tuple(calib_shape)}.")
                print("Scaling camera matrix to match current resolution...")
                scale_x = current_shape[0] / calib_shape[0]
                scale_y = current_shape[1] / calib_shape[1]
                camera_matrix[0, 0] *= scale_x  # fx
                camera_matrix[0, 2] *= scale_x  # cx
                camera_matrix[1, 1] *= scale_y  # fy
                camera_matrix[1, 2] *= scale_y  # cy
    else:
        if args.uncalib:
            print("Using default camera matrix guess (forced by --uncalib).")
        else:
            print(f"Warning: Calibration file {calib_path} not found. Using default camera matrix.")
        # Approximate camera parameters
        focal_length = img.shape[1]
        center = (img.shape[1]/2, img.shape[0]/2)
        camera_matrix = np.array([
            [focal_length, 0, center[0]],
            [0, focal_length, center[1]],
            [0, 0, 1]
        ], dtype="double")
        dist_coeffs = np.zeros((4,1))

    # Undistort the image first if distortion is non-zero
    if np.any(dist_coeffs):
        print("Undistorting image before ArUco detection...")
        img = cv2.undistort(img, camera_matrix, dist_coeffs)
        dist_coeffs_pnp = np.zeros(4)
    else:
        dist_coeffs_pnp = dist_coeffs

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
            success, rvec, tvec = cv2.solvePnP(obj_points, corners[i][0], camera_matrix, dist_coeffs_pnp)
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