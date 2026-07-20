import cv2
import numpy as np
import argparse

def main():
    parser = argparse.ArgumentParser(description="ArUco Marker Pose Estimator")
    parser.add_argument("image", help="Path to the image file")
    parser.add_argument("marker_size", type=float, help="Size of the marker in meters (e.g., 0.05 for 5cm)")
    args = parser.parse_args()

    img = cv2.imread(args.image)
    if img is None:
        print("Error: Could not load the image.")
        return
        
    #Load actual calibration data instead of guessing
    #try:
    #	with np.load("calibration_data.npz") as X:
    #        camera_matrix, dist_coeffs = [X[i] for i in ('camera_matrix', 'dist_coeffs')]
    #        print(camera_matrix)
    #       print(dist_coeffs)
    #except FileNotFoundError:
    # 	print("Error: calibration_data.npz not found. Please run the calibration script first.")
    #	return
        
    focal_length = img.shape[1]
    center = (img.shape[1]/2, img.shape[0]/2)
    camera_matrix = np.array([
        [focal_length, 0, center[0]],
        [0, focal_length, center[1]],
    [0, 0, 1]
    ], dtype="double")
    dist_coeffs = np.zeros((5,1))

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
            success, rvec, tvec = cv2.solvePnP(obj_points, corners[i][0], camera_matrix, dist_coeffs)
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

    cv2.imshow("ArUco Pose Estimation", vis)
    cv2.imwrite("output.jpg", vis)
    print("Saved visualization to output.jpg")
    cv2.waitKey(0)
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
