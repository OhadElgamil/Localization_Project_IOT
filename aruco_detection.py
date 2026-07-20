import cv2
import numpy as np
import argparse

import os

def main():
    parser = argparse.ArgumentParser(description="ArUco Marker Pose Estimator")
    parser.add_argument("image", help="Path to the image file")
    parser.add_argument("marker_size", type=float, help="Size of the marker in meters (e.g., 0.05 for 5cm)")
    parser.add_argument("--calib", type=str, default="calibration_data.npz", help="Path to calibration data file")
    parser.add_argument("--uncalib", action="store_true", help="Force using the default camera matrix guess instead of calibration data")
    args = parser.parse_args()

    img = cv2.imread(args.image)
    if img is None:
        print("Error: Could not load the image.")
        return
        
    # Load actual calibration data if available and not forced to bypass
    if not args.uncalib and os.path.exists(args.calib):
        print(f"Loading calibration from {args.calib}")
        data = np.load(args.calib)
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
            print(f"Warning: Calibration file {args.calib} not found. Using default camera matrix.")
        focal_length = img.shape[1]
        center = (img.shape[1]/2, img.shape[0]/2)
        camera_matrix = np.array([
            [focal_length, 0, center[0]],
            [0, focal_length, center[1]],
            [0, 0, 1]
        ], dtype="double")
        dist_coeffs = np.zeros((5,1))

    # Undistort the image first if distortion is non-zero
    if np.any(dist_coeffs):
        print("Undistorting image before ArUco detection...")
        img = cv2.undistort(img, camera_matrix, dist_coeffs)
        # Since we undistorted the image, we tell solvePnP that distortion is now 0
        dist_coeffs_pnp = np.zeros(5)
    else:
        dist_coeffs_pnp = dist_coeffs

    dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
    parameters = cv2.aruco.DetectorParameters()
    detector = cv2.aruco.ArucoDetector(dictionary, parameters)

    corners, ids, rejected = detector.detectMarkers(img)
    vis = img.copy()

    if ids is not None:
        # Draw detected marker borders and IDs
        cv2.aruco.drawDetectedMarkers(vis, corners, ids)

        print(f"Found {len(ids)} markers:")
        half_size = args.marker_size / 2.0
        obj_points = np.array([
            [-half_size,  half_size, 0],
            [ half_size,  half_size, 0],
            [ half_size, -half_size, 0],
            [-half_size, -half_size, 0]
        ], dtype=np.float32)

        for i in range(len(ids)):
            success, rvec, tvec = cv2.solvePnP(
                obj_points, corners[i][0], camera_matrix, dist_coeffs_pnp, flags=cv2.SOLVEPNP_IPPE_SQUARE
            )
            if success:
                distance = np.linalg.norm(tvec)
                x, y, z = tvec.flatten()
                rx, ry, rz = rvec.flatten()

                # Draw XYZ axes on the marker (length = half the marker size)
                cv2.drawFrameAxes(vis, camera_matrix, dist_coeffs, rvec, tvec, args.marker_size * 0.5)

                # Label each marker with its ID and distance
                corner = corners[i][0][0].astype(int)  # top-left corner
                label = f"ID:{ids[i][0]}  {distance:.2f}m"
                cv2.putText(vis, label, (corner[0], corner[1] - 10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

                print(f"Marker ID: {ids[i][0]} | Distance: {distance:.3f}m")
                print(f"  -> tvec: [{x:.3f}, {y:.3f}, {z:.3f}]")
                print(f"  -> rvec: [{rx:.3f}, {ry:.3f}, {rz:.3f}]")
    else:
        print("No ArUco markers found in the image.")
        cv2.putText(vis, "No markers found", (20, 40),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 255), 2)

    cv2.imwrite("output.jpg", vis)
    print("Saved visualization to output.jpg")

if __name__ == "__main__":
    main()
