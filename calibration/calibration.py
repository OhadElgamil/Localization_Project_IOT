import cv2
import numpy as np
import glob
import argparse
import os

def main():
    parser = argparse.ArgumentParser(description="Single Camera Intrinsic Calibration using a Checkerboard")
    parser.add_argument("--img_dir", type=str, default="./calib_images", help="Directory containing calibration images")
    parser.add_argument("--ext", type=str, default="jpg", help="File extension of the images (e.g., jpg, png)")
    parser.add_argument("--width", type=int, default=9, help="Number of INNER corners horizontally on the checkerboard")
    parser.add_argument("--height", type=int, default=6, help="Number of INNER corners vertically on the checkerboard")
    parser.add_argument("--square_size", type=float, default=0.025, help="Size of a single square in meters (e.g., 0.025 for 25mm)")
    args = parser.parse_args()

    # Define the dimensions of the checkerboard (inner corners)
    CHECKERBOARD = (args.width, args.height)

    # Termination criteria for refining the corner coordinates
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.001)

    # Prepare object points based on the real-world dimensions of the checkerboard squares
    # e.g., (0,0,0), (1,0,0), (2,0,0) ... (8,5,0) scaled by square_size
    objp = np.zeros((CHECKERBOARD[0] * CHECKERBOARD[1], 3), np.float32)
    objp[:, :2] = np.mgrid[0:CHECKERBOARD[0], 0:CHECKERBOARD[1]].T.reshape(-1, 2)
    objp *= args.square_size

    # Arrays to store object points and image points from all the images
    objpoints = [] # 3d points in real world space
    imgpoints = [] # 2d points in image plane

    # Fetch all images
    search_path = os.path.join(args.img_dir, f"*.{args.ext}")
    images = glob.glob(search_path)

    if not images:
        print(f"Error: No images found in {search_path}")
        return

    print(f"Found {len(images)} images. Searching for checkerboard {CHECKERBOARD}...")

    img_shape = None

    for fname in images:
        img = cv2.imread(fname)
        if img is None:
            continue

        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        if img_shape is None:
            img_shape = gray.shape[::-1] # (width, height)

        # Find the chess board corners
        ret, corners = cv2.findChessboardCorners(gray, CHECKERBOARD,
                                                 cv2.CALIB_CB_ADAPTIVE_THRESH +
                                                 cv2.CALIB_CB_FAST_CHECK +
                                                 cv2.CALIB_CB_NORMALIZE_IMAGE)

        if ret:
            objpoints.append(objp)
            # Refine the corner locations to sub-pixel accuracy
            corners2 = cv2.cornerSubPix(gray, corners, (11, 11), (-1, -1), criteria)
            imgpoints.append(corners2)
            print(f"[OK] Found corners in: {fname}")
        else:
            print(f"[FAILED] Could not find corners in: {fname}")

    if len(objpoints) == 0:
        print("Error: Could not find checkerboard corners in any of the images. Check your grid dimensions and image clarity.")
        return

    print("\nCalculating camera parameters... This may take a moment.")
    ret, mtx, dist, rvecs, tvecs = cv2.calibrateCamera(objpoints, imgpoints, img_shape, None, None)

    if ret:
        print("\n--- Calibration Successful ---")
        print("Camera Matrix (Intrinsic Parameters):")
        print(mtx)
        print("\nDistortion Coefficients:")
        print(dist)

        # Calculate Re-projection Error to evaluate calibration quality
        mean_error = 0
        for i in range(len(objpoints)):
            imgpoints2, _ = cv2.projectPoints(objpoints[i], rvecs[i], tvecs[i], mtx, dist)
            error = cv2.norm(imgpoints[i], imgpoints2, cv2.NORM_L2) / len(imgpoints2)
            mean_error += error

        print(f"\nTotal Reprojection Error: {mean_error/len(objpoints):.4f} pixels (closer to 0 is better)")

        # Save the parameters for the ArUco script
        save_path = "calibration_data.npz"
        np.savez(save_path, camera_matrix=mtx, dist_coeffs=dist)
        print(f"\nSaved calibration data to {save_path}")
    else:
        print("Calibration failed.")

if __name__ == "__main__":
    main()
