import cv2
import numpy as np
import glob
import argparse
import os

# Map friendly names to cv2.aruco dictionary constants
DICT_MAP = {
    "4X4_50": cv2.aruco.DICT_4X4_50,
    "4X4_100": cv2.aruco.DICT_4X4_100,
    "4X4_250": cv2.aruco.DICT_4X4_250,
    "4X4_1000": cv2.aruco.DICT_4X4_1000,
    "5X5_50": cv2.aruco.DICT_5X5_50,
    "5X5_100": cv2.aruco.DICT_5X5_100,
    "5X5_250": cv2.aruco.DICT_5X5_250,
    "5X5_1000": cv2.aruco.DICT_5X5_1000,
    "6X6_50": cv2.aruco.DICT_6X6_50,
    "6X6_100": cv2.aruco.DICT_6X6_100,
    "6X6_250": cv2.aruco.DICT_6X6_250,
    "6X6_1000": cv2.aruco.DICT_6X6_1000,
    "7X7_50": cv2.aruco.DICT_7X7_50,
    "7X7_100": cv2.aruco.DICT_7X7_100,
    "7X7_250": cv2.aruco.DICT_7X7_250,
    "7X7_1000": cv2.aruco.DICT_7X7_1000,
    "ORIGINAL": cv2.aruco.DICT_ARUCO_ORIGINAL,
}


def build_board(squares_x, squares_y, square_len_m, marker_len_m, dict_name):
    if marker_len_m >= square_len_m:
        raise ValueError(
            f"marker_size ({marker_len_m*1000:.2f}mm) must be smaller than "
            f"square_size ({square_len_m*1000:.2f}mm). The marker sits inside "
            f"the square with a border margin — check your measurements."
        )
    aruco_dict = cv2.aruco.getPredefinedDictionary(DICT_MAP[dict_name])
    board = cv2.aruco.CharucoBoard(
        (squares_x, squares_y), square_len_m, marker_len_m, aruco_dict
    )
    return board, aruco_dict


def main():
    parser = argparse.ArgumentParser(
        description="Single Camera Intrinsic Calibration using a ChArUco board"
    )
    parser.add_argument("--img_dir", type=str, default="./calib_images",
                        help="Directory containing calibration images")
    parser.add_argument("--ext", type=str, default="jpg",
                        help="File extension of the images (e.g., jpg, png)")
    parser.add_argument("--squares_x", type=int, required=True,
                        help="Number of squares horizontally on the board (tiles width)")
    parser.add_argument("--squares_y", type=int, required=True,
                        help="Number of squares vertically on the board (tiles height)")
    parser.add_argument("--square_size", type=float, required=True,
                        help="Full square size in meters (e.g. 0.015 for 15mm). "
                             "Measure the black square edge-to-edge, NOT the marker.")
    parser.add_argument("--marker_size", type=float, required=True,
                        help="ArUco marker size in meters (e.g. 0.011 for 11mm)")
    parser.add_argument("--dict", type=str, required=True, choices=list(DICT_MAP.keys()),
                        help="ArUco dictionary used to generate the board")
    parser.add_argument("--min_corners", type=int, default=6,
                        help="Minimum number of ChArUco corners required to accept a view")
    parser.add_argument("--max_reproj_error", type=float, default=1.0,
                        help="Per-view reprojection error (px) above which a view is "
                             "flagged as an outlier after the initial solve")
    parser.add_argument("--save_path", type=str, default="calibration_data.npz")
    args = parser.parse_args()

    board, aruco_dict = build_board(
        args.squares_x, args.squares_y, args.square_size, args.marker_size, args.dict
    )

    detector_params = cv2.aruco.DetectorParameters()
    charuco_params = cv2.aruco.CharucoParameters()
    charuco_detector = cv2.aruco.CharucoDetector(board, charuco_params, detector_params)

    search_path = os.path.join(args.img_dir, f"*.{args.ext}")
    images = sorted(glob.glob(search_path))

    if not images:
        print(f"Error: No images found in {search_path}")
        return

    print(f"Found {len(images)} images. Detecting ChArUco board "
          f"({args.squares_x}x{args.squares_y} squares, dict={args.dict})...")

    all_charuco_corners = []
    all_charuco_ids = []
    used_filenames = []
    img_shape = None  # (width, height)

    for fname in images:
        img = cv2.imread(fname)
        if img is None:
            print(f"[SKIP] Could not read: {fname}")
            continue

        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        if img_shape is None:
            img_shape = gray.shape[::-1]  # (width, height)
        elif gray.shape[::-1] != img_shape:
            print(f"[SKIP] {fname}: image size {gray.shape[::-1]} does not match "
                  f"first image size {img_shape}. All images must be the same resolution.")
            continue

        charuco_corners, charuco_ids, marker_corners, marker_ids = \
            charuco_detector.detectBoard(gray)

        if charuco_ids is None or len(charuco_ids) < args.min_corners:
            n_found = 0 if charuco_ids is None else len(charuco_ids)
            print(f"[FAILED] {fname}: only {n_found} ChArUco corners found "
                  f"(need {args.min_corners})")
            continue

        all_charuco_corners.append(charuco_corners)
        all_charuco_ids.append(charuco_ids)
        used_filenames.append(fname)
        print(f"[OK] {fname}: {len(charuco_ids)} corners found")

    if len(all_charuco_corners) == 0:
        print("Error: No usable ChArUco detections in any image. Check --dict, "
              "--squares_x/--squares_y, and image focus/lighting.")
        return

    print(f"\n{len(all_charuco_corners)}/{len(images)} images usable. "
          f"Calculating camera parameters...")

    ret, camera_matrix, dist_coeffs, rvecs, tvecs = cv2.aruco.calibrateCameraCharuco(
        all_charuco_corners, all_charuco_ids, board, img_shape, None, None
    )

    if not ret:
        print("Calibration failed.")
        return

    # Per-view reprojection error, using the board's own object points
    # for the specific corner IDs detected in each view.
    obj_points_all = board.getChessboardCorners()  # indexed by corner id
    per_view_errors = []
    for i in range(len(all_charuco_corners)):
        ids = all_charuco_ids[i].flatten()
        obj_pts = obj_points_all[ids]
        img_pts = all_charuco_corners[i]

        projected, _ = cv2.projectPoints(
            obj_pts, rvecs[i], tvecs[i], camera_matrix, dist_coeffs
        )
        error = cv2.norm(img_pts, projected, cv2.NORM_L2) / len(projected)
        per_view_errors.append(error)

    mean_error = float(np.mean(per_view_errors))

    print("\n--- Initial Calibration ---")
    print(f"Views used: {len(all_charuco_corners)}")
    print(f"Mean reprojection error: {mean_error:.4f} px")
    print("\nPer-view reprojection error:")
    for fname, err in zip(used_filenames, per_view_errors):
        flag = "  <-- OUTLIER" if err > args.max_reproj_error else ""
        print(f"  {err:.4f} px  {fname}{flag}")

    # Drop outlier views and re-solve for a cleaner result
    outlier_idx = [i for i, e in enumerate(per_view_errors) if e > args.max_reproj_error]
    if outlier_idx and len(outlier_idx) < len(all_charuco_corners):
        print(f"\n{len(outlier_idx)} view(s) exceed {args.max_reproj_error}px, "
              f"re-solving without them...")

        clean_corners = [c for i, c in enumerate(all_charuco_corners) if i not in outlier_idx]
        clean_ids = [c for i, c in enumerate(all_charuco_ids) if i not in outlier_idx]
        clean_filenames = [f for i, f in enumerate(used_filenames) if i not in outlier_idx]

        ret2, camera_matrix2, dist_coeffs2, rvecs2, tvecs2 = cv2.aruco.calibrateCameraCharuco(
            clean_corners, clean_ids, board, img_shape, None, None
        )

        if ret2:
            per_view_errors2 = []
            for i in range(len(clean_corners)):
                ids = clean_ids[i].flatten()
                obj_pts = obj_points_all[ids]
                img_pts = clean_corners[i]
                projected, _ = cv2.projectPoints(
                    obj_pts, rvecs2[i], tvecs2[i], camera_matrix2, dist_coeffs2
                )
                error = cv2.norm(img_pts, projected, cv2.NORM_L2) / len(projected)
                per_view_errors2.append(error)

            mean_error2 = float(np.mean(per_view_errors2))
            print(f"Re-solved mean reprojection error: {mean_error2:.4f} px "
                  f"(was {mean_error:.4f} px with all views)")

            camera_matrix, dist_coeffs = camera_matrix2, dist_coeffs2
            mean_error = mean_error2
            used_filenames = clean_filenames
    elif outlier_idx:
        print("\nWarning: all views flagged as outliers relative to --max_reproj_error. "
              "Keeping the original solve — check your board measurements and detection quality.")

    print("\n--- Final Calibration ---")
    print("Camera Matrix (Intrinsic Parameters):")
    print(camera_matrix)
    print("\nDistortion Coefficients:")
    print(dist_coeffs)
    print(f"\nFinal mean reprojection error: {mean_error:.4f} px "
          f"(views used: {len(used_filenames)})")

    if mean_error > 1.0:
        print("\nWARNING: reprojection error is above 1px. Do not trust these "
              "parameters for localization. Check board flatness, square/marker "
              "size accuracy, and image sharpness before re-shooting.")

    np.savez(args.save_path, camera_matrix=camera_matrix, dist_coeffs=dist_coeffs)
    print(f"\nSaved calibration data to {args.save_path}")


if __name__ == "__main__":
    main()
