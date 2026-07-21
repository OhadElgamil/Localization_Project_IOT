import numpy as np
import time
import logging

try:
    import matplotlib.pyplot as plt
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False

from config import T_CAM_ROBOT
import localization
import geometry
from contracts import LocalizationResult

# Suppress debug logs for clean output
logging.getLogger("pipeline.localization").setLevel(logging.WARNING)

# ==========================================
# Simulation Configuration Constants
# ==========================================
NUM_MARKERS = 7
NUM_TRIALS = 750
NOISE_STD = 0.02
OUTLIER_PROB = 0.0005
OUTLIER_MAGNITUDE = 0.5  # meters
HUBER_DELTA = 0.25  # Huber loss threshold
MIN_MARKER_SEPARATION = 0.25  # meters
# ==========================================

class MockMarkerMap:
    def __init__(self, markers):
        self.markers = markers
        
    def get(self, marker_id):
        return self.markers.get(marker_id)
        
    def get_transform(self, marker_id):
        T = np.eye(4)
        T[:3, 3] = self.markers.get(marker_id)
        return T
        
    def known_ids(self):
        return list(self.markers.keys())

class MockDetection:
    def __init__(self, camera_name, marker_id, distance_m, T_marker_cam):
        self.camera_name = camera_name
        self.marker_id = marker_id
        self.distance_m = distance_m
        self.T_marker_cam = T_marker_cam

def generate_random_scene(num_markers):
    # 1. Random true robot location (y=0, yaw is multiple of 90)
    x = np.random.uniform(-3.0, 3.0)
    z = np.random.uniform(-3.0, 3.0)
    yaw_deg = np.random.choice([0.0, 90.0, 180.0, 270.0])
    
    T_global_robot_true = geometry.extrinsic_transform((x, 0.0, z), (0.0, 0.0, yaw_deg))
    true_pos = T_global_robot_true[:3, 3]
    
    # 2. Random markers on walls (randomized distance between 0.5 and 5 meters)
    markers = {}
    for i in range(num_markers):
        for attempt in range(100):
            wall = np.random.choice(['n', 's', 'e', 'w'])
            wall_dist = np.random.uniform(0.5, 5.0)
            wall_pos = np.random.uniform(-5.0, 5.0)
            
            mx = wall_dist if wall == 'e' else -wall_dist if wall == 'w' else wall_pos
            mz = wall_dist if wall == 'n' else -wall_dist if wall == 's' else wall_pos
            my = np.random.uniform(0.5, 2.0)
            candidate_pos = np.array([mx, my, mz])
            
            if not markers:
                markers[i+1] = candidate_pos
                break
                
            distances = [np.linalg.norm(candidate_pos - existing_pos) for existing_pos in markers.values()]
            if min(distances) >= MIN_MARKER_SEPARATION:
                markers[i+1] = candidate_pos
                break
        else:
            # Fallback if we couldn't find a spot
            markers[i+1] = candidate_pos
    
    marker_map = MockMarkerMap(markers)
    return T_global_robot_true, true_pos, marker_map

def create_noisy_detections(T_global_robot_true, marker_map, noise_std, outlier_prob, outlier_magnitude):
    detections = []
    outliers_injected = 0
    
    # We will just assign a random camera from our 4 available cameras to each marker detection
    cameras = list(T_CAM_ROBOT.keys())
    
    for marker_id in marker_map.markers:
        cam_name = np.random.choice(cameras)
        
        # Calculate true T_marker_cam
        T_global_marker = marker_map.get_transform(marker_id)
        T_marker_global = geometry.invert_homogeneous(T_global_marker)
        T_cam_robot_inv = geometry.invert_homogeneous(T_CAM_ROBOT[cam_name])
        
        # T_global_cam = T_global_robot @ T_robot_cam
        T_global_cam = T_global_robot_true @ T_cam_robot_inv
        T_marker_cam_true = T_marker_global @ T_global_cam
        
        # Inject normal camera noise
        noise_vec = np.random.normal(0, noise_std, 3)
        
        # Inject occasional severe outlier
        if np.random.random() < outlier_prob:
            noise_vec += np.random.normal(0, outlier_magnitude, 3)
            outliers_injected += 1
            
        T_marker_cam_noisy = np.copy(T_marker_cam_true)
        T_marker_cam_noisy[:3, 3] += noise_vec
        
        noisy_dist = np.linalg.norm(T_marker_cam_noisy[:3, 3])
        
        det = MockDetection(
            camera_name=cam_name,
            marker_id=marker_id,
            distance_m=noisy_dist,
            T_marker_cam=T_marker_cam_noisy
        )
        detections.append(det)
        
    return detections, outliers_injected

def run_comparison():
    print("==================================================")
    print("   Localization Strategy Comparison Simulator")
    print("==================================================\n")
    
    triplet_errors_clean = []
    triplet_errors_outlier = []
    triplet_times = []
    triplet_confs_clean = []
    triplet_confs_outlier = []
    
    ls_errors_clean = []
    ls_errors_outlier = []
    ls_times = []
    ls_confs_clean = []
    ls_confs_outlier = []
    
    for i in range(NUM_TRIALS):
        T_global_robot_true, true_pos, marker_map = generate_random_scene(NUM_MARKERS)
        detections, num_outliers = create_noisy_detections(T_global_robot_true, marker_map, NOISE_STD, OUTLIER_PROB, OUTLIER_MAGNITUDE)
        
        # 1. Test Triplets Method
        start_t = time.perf_counter()
        res_trip = localization.estimate_triplets(detections, marker_map, T_CAM_ROBOT, max_markers=NUM_MARKERS)
        t_trip = time.perf_counter() - start_t
        
        if res_trip.position is not None:
            err_trip = np.linalg.norm(res_trip.position - true_pos)
            triplet_times.append(t_trip)
            if num_outliers > 0:
                triplet_errors_outlier.append(err_trip)
                triplet_confs_outlier.append(res_trip.confidence)
            else:
                triplet_errors_clean.append(err_trip)
                triplet_confs_clean.append(res_trip.confidence)
            
        # 2. Test Least Squares Method
        start_t = time.perf_counter()
        res_ls = localization.estimate_least_squares(detections, marker_map, T_CAM_ROBOT, max_markers=NUM_MARKERS, use_huber=True, huber_delta=HUBER_DELTA)
        t_ls = time.perf_counter() - start_t
        
        if res_ls.position is not None:
            err_ls = np.linalg.norm(res_ls.position - true_pos)
            ls_times.append(t_ls)
            if num_outliers > 0:
                ls_errors_outlier.append(err_ls)
                ls_confs_outlier.append(res_ls.confidence)
            else:
                ls_errors_clean.append(err_ls)
                ls_confs_clean.append(res_ls.confidence)
            
    print(f"Results over {NUM_TRIALS} trials ({NUM_MARKERS} markers per trial, {OUTLIER_PROB*100}% chance of {OUTLIER_MAGNITUDE}m outlier):")
    total_outlier_trials = len(triplet_errors_outlier)
    print(f"Trials with 1+ Outliers: {total_outlier_trials}")
    print(f"Trials with 0 Outliers:  {len(triplet_errors_clean)}")
    
    def print_stats(name, times, clean, outlier, clean_conf, outlier_conf):
        print(f"\n--- {name} ---")
        print(f"Average CPU Time : {np.mean(times)*1000:.2f} ms")
        if clean:
            print(f"Clean Trials     : Avg Error = {np.mean(clean):.3f}m, Max Error = {np.max(clean):.3f}m, Avg Conf = {np.mean(clean_conf):.2f}")
        if outlier:
            print(f"Outlier Trials   : Avg Error = {np.mean(outlier):.3f}m, Max Error = {np.max(outlier):.3f}m, Avg Conf = {np.mean(outlier_conf):.2f}")
        else:
            print(f"Outlier Trials   : N/A")
            
    print_stats("Triplets Method (Old)", triplet_times, triplet_errors_clean, triplet_errors_outlier, triplet_confs_clean, triplet_confs_outlier)
    print_stats("Single Least-Squares Method (New w/ Huber Loss)", ls_times, ls_errors_clean, ls_errors_outlier, ls_confs_clean, ls_confs_outlier)
    print("\n==================================================")
    
    if MATPLOTLIB_AVAILABLE:
        print("\nGenerating plots...")
        triplet_all_errors = triplet_errors_clean + triplet_errors_outlier
        ls_all_errors = ls_errors_clean + ls_errors_outlier
        
        # 1. Histogram
        plt.figure(figsize=(10, 6))
        plt.hist(triplet_all_errors, bins=50, alpha=0.5, label='Triplets (Old)', color='red', range=(0, max(ls_all_errors + triplet_all_errors)))
        plt.hist(ls_all_errors, bins=50, alpha=0.5, label='Single LS (New)', color='blue', range=(0, max(ls_all_errors + triplet_all_errors)))
        plt.title(f'Localization Error Distribution ({NUM_TRIALS} Trials)')
        plt.xlabel('Error (meters)')
        plt.ylabel('Number of Trials')
        plt.legend()
        plt.grid(True, alpha=0.3)
        plt.savefig('error_histogram.png')
        print(" -> Saved error_histogram.png")
        
        # 2. Cumulative Distribution Function (CDF)
        plt.figure(figsize=(10, 6))
        plt.plot(np.sort(triplet_all_errors), np.linspace(0, 1, len(triplet_all_errors)), label='Triplets (Old)', color='red', lw=2)
        plt.plot(np.sort(ls_all_errors), np.linspace(0, 1, len(ls_all_errors)), label='Single LS (New)', color='blue', lw=2)
        plt.title(f'Cumulative Distribution of Errors ({NUM_TRIALS} Trials)')
        plt.xlabel('Error (meters)')
        plt.ylabel('Cumulative Probability (e.g. 0.8 = 80% of trials)')
        plt.yticks(np.arange(0, 1.05, 0.05))
        plt.legend()
        plt.grid(True, alpha=0.3)
        plt.savefig('error_cdf.png')
        print(" -> Saved error_cdf.png")
    else:
        print("\nmatplotlib is not installed. To see error graphs, run: pip install matplotlib")

if __name__ == '__main__':
    run_comparison()
