import cv2
import numpy as np
import argparse

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

        for i in range(len(ids)):
            # Calculate the marker's pose
            success, rvec, tvec = cv2.solvePnP(obj_points, corners[i][0], camera_matrix, dist_coeffs)
            if success:
                distance = np.linalg.norm(tvec)
                x, y, z = tvec.flatten()
                rx, ry, rz = rvec.flatten()
                
                print(f"Marker ID: {ids[i][0]} | Calculated distance: {distance:.3f} meters")
                print(f"  -> Camera XYZ (tvec): [{x:.3f}, {y:.3f}, {z:.3f}]")
                print(f"  -> Camera Orientation (rvec): [{rx:.3f}, {ry:.3f}, {rz:.3f}]")
    else:
        print("No ArUco markers found in the image.")

if __name__ == "__main__":
    main()