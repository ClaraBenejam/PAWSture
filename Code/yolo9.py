"""
Posture analysis using YOLO pose estimation with pressure map simulation.
Detects body keypoints and calculates posture scores.
"""

import cv2
import numpy as np
from ultralytics import YOLO
import math
import datetime
from supabase import create_client, Client
import time
import sys
import os

# Import pressure map simulator
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
try:
    from pressure_map_simulator import PressureMapSimulator
    PRESSURE_MAP_AVAILABLE = True
except ImportError:
    PRESSURE_MAP_AVAILABLE = False


def calcular_direccion_inclinacion(keypoints):
    """
    Calculate tilt direction from keypoint height differences.
    
    Parameters:
        keypoints: Array of keypoints with [x, y, confidence] format
        
    Returns:
        Tuple: (lateral_tilt, frontal_tilt, confidence, (shoulder_diff, head_diff))
    """
    try:
        # COCO keypoint indices: 0:nose, 5:left_shoulder, 6:right_shoulder
        nose = tuple(keypoints[0][:2]) if len(keypoints) > 0 else None
        left_shoulder = tuple(keypoints[5][:2]) if len(keypoints) > 5 else None
        right_shoulder = tuple(keypoints[6][:2]) if len(keypoints) > 6 else None
        
        # Get confidences
        confidences = [float(keypoints[i][2]) if len(keypoints) > i else 0 for i in [0, 5, 6]]
        
        # Check valid keypoints
        valid_count = sum(c > 0 for c in confidences)
        if valid_count < 2 or not all([nose, left_shoulder, right_shoulder]):
            return 'center', 'center', 0.0, (0, 0)
        
        # Calculate lateral tilt (shoulder height difference)
        left_height = left_shoulder[1]
        right_height = right_shoulder[1]
        shoulder_diff = left_height - right_height
        
        # Determine lateral direction
        lateral_threshold = 15
        if shoulder_diff < -lateral_threshold:
            lateral_tilt = 'left'
        elif shoulder_diff > lateral_threshold:
            lateral_tilt = 'right'
        else:
            lateral_tilt = 'center'
        
        # Calculate frontal tilt (head relative to shoulders)
        head_height = nose[1]
        avg_shoulder_height = (left_height + right_height) / 2.0
        head_diff = head_height - avg_shoulder_height
        
        # Determine frontal direction
        frontal_threshold = 20
        if head_diff > frontal_threshold:
            frontal_tilt = 'forward'
        elif head_diff < -frontal_threshold:
            frontal_tilt = 'back'
        else:
            frontal_tilt = 'center'
        
        # Calculate average confidence
        valid_confs = [c for c in confidences if c > 0]
        confidence = sum(valid_confs) / len(valid_confs) if valid_confs else 0.0
        
        return lateral_tilt, frontal_tilt, confidence, (shoulder_diff, head_diff)
    
    except Exception as e:
        print(f"Error calculating tilt: {e}")
        return 'center', 'center', 0.0, (0, 0)


def generar_heatmap_direccional(rows=10, cols=10, direccion_lateral='center', 
                                direccion_frontal='center', angulos=(0, 0), 
                                noise_level=0.08, overall_risk=0):
    """
    Generate directional pressure heatmap based on tilt and risk level.
    
    Parameters:
        rows: Number of rows in heatmap
        cols: Number of columns in heatmap
        direccion_lateral: Lateral tilt direction
        direccion_frontal: Frontal tilt direction
        angulos: Tilt angles
        noise_level: Noise intensity
        overall_risk: Overall risk level (0-4)
        
    Returns:
        10x10 heatmap matrix with pressure values (0-1)
    """
    heatmap = np.zeros((rows, cols))
    
    # Risk-based parameters
    risk_params = {
        0: {'center_pressure': 0.8, 'displacement': 0.0, 'lateral_strength': 0.0, 'sigma': 3.0},
        1: {'center_pressure': 0.8, 'displacement': 0.1, 'lateral_strength': 0.1, 'sigma': 3.2},
        2: {'center_pressure': 0.8, 'displacement': 0.2, 'lateral_strength': 0.15, 'sigma': 3.4},
        3: {'center_pressure': 0.8, 'displacement': 0.4, 'lateral_strength': 0.3, 'sigma': 3.6},
        4: {'center_pressure': 0.8, 'displacement': 0.6, 'lateral_strength': 0.45, 'sigma': 3.8}
    }
    
    params = risk_params.get(overall_risk, risk_params[0])
    center_pressure = params['center_pressure']
    base_displacement = params['displacement']
    lateral_strength = params['lateral_strength']
    sigma_base = params['sigma']
    
    # Base center position
    base_center_col = 5.0
    sigma_row = sigma_col = sigma_base
    
    # Apply lateral displacement based on risk
    if overall_risk >= 2:
        if direccion_lateral == 'left':
            base_center_col -= base_displacement
        elif direccion_lateral == 'right':
            base_center_col += base_displacement
    
    # Generate gaussian distribution
    for r in range(rows):
        for c in range(cols):
            # Separate backrest (rows 0-4) and seat (rows 5-9)
            if r < 5:
                center_row, center_col = 2.5, base_center_col
            else:
                center_row, center_col = 7.5, base_center_col
            
            distance_sq = ((r - center_row)**2 / (2 * sigma_row**2) + 
                          (c - center_col)**2 / (2 * sigma_col**2))
            gaussian = np.exp(-distance_sq)
            
            # Apply center pressure (more on seat)
            if r >= 5:
                heatmap[r, c] = center_pressure * gaussian * 1.3
            else:
                heatmap[r, c] = center_pressure * gaussian
    
    # Apply lateral limits for higher risk levels
    if overall_risk >= 2:
        for r in range(rows):
            for c in range(cols):
                if c <= 3:  # Left side
                    left_factor = max(0, 1.0 - (c / 3.0))
                    heatmap[r, c] = max(heatmap[r, c], lateral_strength * left_factor * 0.8)
                if c >= 6:  # Right side
                    right_factor = max(0, 1.0 - ((9 - c) / 3.0))
                    heatmap[r, c] = max(heatmap[r, c], lateral_strength * right_factor * 0.8)
    
    # Apply lateral tilt patterns
    if direccion_lateral == 'left':
        for r in range(rows):
            # Increase pressure on left side
            for c in range(0, 5):
                left_factor = max(0, 1.0 - (c / 4.0))
                heatmap[r, c] = min(heatmap[r, c] + left_factor * 0.6, 1.0)
            # Decrease pressure on right side
            for c in range(5, 10):
                reduction = 0.8 - 0.3 * ((c - 5) / 4.0)
                heatmap[r, c] = heatmap[r, c] * reduction
    
    elif direccion_lateral == 'right':
        for r in range(rows):
            # Decrease pressure on left side
            for c in range(0, 5):
                reduction = 0.8 - 0.3 * ((4 - c) / 4.0)
                heatmap[r, c] = heatmap[r, c] * reduction
            # Increase pressure on right side
            for c in range(5, 10):
                right_factor = max(0, 1.0 - ((9 - c) / 4.0))
                heatmap[r, c] = min(heatmap[r, c] + right_factor * 0.6, 1.0)
    
    # Apply frontal tilt patterns
    if direccion_frontal == 'forward':
        for r in range(0, 5):  # Backrest
            reduction = 0.5 + 0.3 * (r / 4.0)
            heatmap[r, :] = heatmap[r, :] * reduction
        for r in range(5, 10):  # Seat
            increase = 1.2 + 0.2 * ((r - 5) / 4.0)
            heatmap[r, :] = np.minimum(heatmap[r, :] * increase, 1.0)
    
    elif direccion_frontal == 'back':
        for r in range(0, 5):  # Backrest
            increase = 1.2 + 0.2 * (r / 4.0)
            heatmap[r, :] = np.minimum(heatmap[r, :] * increase, 1.0)
        for r in range(5, 10):  # Seat
            reduction = 0.95 - 0.1 * ((r - 5) / 4.0)
            heatmap[r, :] = heatmap[r, :] * reduction
    
    else:  # center
        for r in range(0, 5):  # Backrest
            heatmap[r, :] = heatmap[r, :] * 0.7
        for r in range(5, 10):  # Seat
            heatmap[r, :] = np.minimum(heatmap[r, :] * 1.2, 1.0)
    
    # Add controlled noise
    if noise_level > 0:
        adjusted_noise = noise_level * max(0.3, 1.0 - (overall_risk * 0.1))
        noise = np.random.normal(0, adjusted_noise * 0.1, (rows, cols))
        heatmap = np.clip(heatmap + noise, 0, 1)
    
    # Normalize if needed
    heatmap = np.clip(heatmap, 0, 1)
    if heatmap.max() > 0:
        current_max = heatmap.max()
        if current_max < 0.5:
            heatmap = heatmap * (0.8 / current_max)
        elif current_max > 0.95:
            heatmap = heatmap * 0.95
    
    return heatmap


class PostureScorer:
    """Main class for posture analysis and scoring."""
    
    def __init__(self, enable_supabase_logging=True, user_id=1, enable_pressure_map=True):
        """
        Initialize PostureScorer.
        
        Parameters:
            enable_supabase_logging: Enable database logging
            user_id: User ID for database records
            enable_pressure_map: Enable pressure map visualization
        """
        self.model = YOLO('yolo11m-pose.pt')
        self.user_id = user_id
        
        # Zone thresholds for 5-level scoring
        self.zones = {
            'neck_lateral_bend': [5, 10, 20, 35],
            'neck_flexion': [9, 18, 30, 50],
            'shoulder_alignment': [5, 10, 20, 35],
            'arm_abduction': [13, 25, 45, 70],
        }
        
        # Risk level definitions
        self.zone_risk = {
            0: "Very Low",
            1: "Low", 
            2: "Medium",
            3: "High",
            4: "Very High"
        }
        
        # Color mapping for zones
        self.zone_colors = {
            0: (0, 255, 0),    # Green
            1: (0, 255, 255),  # Yellow
            2: (0, 165, 255),  # Orange
            3: (0, 0, 255),    # Red
            4: (128, 0, 128)   # Purple
        }
        
        # Keypoint skeleton connections
        self.skeleton = [
            (5, 6), (5, 7), (6, 8), (7, 9), (8, 10),  # Arms
            (5, 11), (6, 12), (11, 12),  # Torso
            (11, 13), (12, 14), (13, 15), (14, 16)  # Legs
        ]
        
        # Supabase configuration
        self.enable_supabase_logging = enable_supabase_logging
        self.SUPABASE_URL = "https://sunsfqthmwotlbfcgmay.supabase.co"
        self.SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InN1bnNmcXRobXdvdGxiZmNnbWF5Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjM0MDQwNjcsImV4cCI6MjA3ODk4MDA2N30.dLSgRjiiK4dDrYcwenp2RHBkMdQxYglficyyRripRN8"
        self.supabase = None
        self.last_supabase_time = 0
        self.supabase_interval = 0.2  # 5 Hz
        self.supabase_insert_count = 0
        
        # Pressure map configuration
        self.enable_pressure_map = enable_pressure_map and PRESSURE_MAP_AVAILABLE
        self.pressure_simulator = None
        self.pressure_map = None
        self.pressure_stats = {}
        self.show_pressure_map = True
        self.pressure_map_size = 180
        
        # Tilt detection variables
        self.tilt_direction_lateral = 'center'
        self.tilt_direction_frontal = 'center'
        self.tilt_confidence = 0.0
        self.tilt_angles = (0, 0)
        
        # Initialize components
        if enable_supabase_logging:
            self.init_supabase()
        if self.enable_pressure_map:
            self.init_pressure_simulator()
    
    def init_supabase(self):
        """Initialize Supabase client connection."""
        try:
            self.supabase = create_client(self.SUPABASE_URL, self.SUPABASE_KEY)
        except Exception as e:
            print(f"Supabase init error: {e}")
            self.supabase = None
    
    def init_pressure_simulator(self):
        """Initialize pressure map simulator."""
        try:
            self.pressure_simulator = PressureMapSimulator(update_rate_hz=4.0, noise_level=0.08)
        except Exception as e:
            print(f"Pressure simulator error: {e}")
            self.enable_pressure_map = False
    
    def update_pressure_map(self, posture_scores, keypoints_raw=None):
        """
        Update pressure map based on posture scores and tilt detection.
        
        Parameters:
            posture_scores: Dictionary of posture scores
            keypoints_raw: Raw keypoints array for tilt detection
        """
        if not self.enable_pressure_map or self.pressure_simulator is None:
            return
        
        # Update simulator with posture scores
        pressure_map = self.pressure_simulator.update(posture_scores)
        
        # Get overall risk level
        overall_zone = posture_scores.get('overall', {}).get('zone', 0)
        overall_risk = int(overall_zone) if overall_zone is not None else 0
        
        # Detect tilt direction if keypoints available
        if keypoints_raw is not None:
            lateral, frontal, conf, angles = calcular_direccion_inclinacion(keypoints_raw)
            self.tilt_direction_lateral = lateral
            self.tilt_direction_frontal = frontal
            self.tilt_confidence = conf
            self.tilt_angles = angles
            
            # Skip if low confidence
            if conf < 0.3:
                self.pressure_map = np.zeros((10, 10))
                self.pressure_stats = self.pressure_simulator.get_statistics()
                return
            
            # Generate directional heatmap
            directional_heatmap = generar_heatmap_direccional(
                direccion_lateral=lateral,
                direccion_frontal=frontal,
                angulos=angles,
                overall_risk=overall_risk
            )
            
            # Combine with simulator heatmap
            if pressure_map is not None:
                pressure_map = (pressure_map * 0.3) + (directional_heatmap * 0.7)
        
        if pressure_map is not None:
            self.pressure_map = pressure_map
            self.pressure_stats = self.pressure_simulator.get_statistics()
            self.last_pressure_update = time.time()
    
    def draw_pressure_map_on_frame(self, frame):
        """
        Draw pressure map visualization on frame (bottom-left corner).
        
        Parameters:
            frame: Input video frame
            
        Returns:
            Frame with pressure map overlay
        """
        if not self.enable_pressure_map or not self.show_pressure_map or self.pressure_map is None:
            return frame
        
        # Use calculated pressure map
        pressure_heatmap = self.pressure_map.copy()
        
        # Resize for visualization
        visualization_size = 150
        pressure_heatmap_scaled = cv2.resize(pressure_heatmap, 
                                            (visualization_size, visualization_size), 
                                            interpolation=cv2.INTER_LINEAR)
        
        # Apply colormap
        pressure_color = cv2.applyColorMap((pressure_heatmap_scaled * 255).astype(np.uint8), 
                                          cv2.COLORMAP_JET)
        
        # Calculate bottom-left position
        h, w = visualization_size, visualization_size
        frame_h, frame_w = frame.shape[:2]
        x = 10
        y = frame_h - h - 10
        
        # Ensure within frame bounds
        y = max(0, y)
        x = min(x, frame_w - w - 10)
        
        # Blend with frame
        alpha = 0.6
        roi = frame[y:y+h, x:x+w]
        blended = cv2.addWeighted(pressure_color, alpha, roi, 1 - alpha, 0)
        frame[y:y+h, x:x+w] = blended
        
        # Add grid lines
        cell_h, cell_w = h // 10, w // 10
        for i in range(11):
            cv2.line(frame, (x, y + i*cell_h), (x + w, y + i*cell_h), (255, 255, 255), 1)
            cv2.line(frame, (x + i*cell_w, y), (x + i*cell_w, y + h), (255, 255, 255), 1)
        
        # Add border and title
        cv2.rectangle(frame, (x, y), (x + w, y + h), (255, 255, 255), 2)
        cv2.putText(frame, "Pressure Map (10x10)", (x, y - 10),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1)
        
        # Add tilt information
        info_y = y - 30
        if self.tilt_confidence > 0.05:
            lateral_text = f"Lateral: {self.tilt_direction_lateral}"
            frontal_text = f"Frontal: {self.tilt_direction_frontal}"
            
            cv2.putText(frame, lateral_text, (x, info_y),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 255), 1)
            cv2.putText(frame, frontal_text, (x, info_y - 20),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 255), 1)
        
        return frame
    
    def insert_posture_measurement(self, scores):
        """
        Insert posture measurement into Supabase database.
        
        Parameters:
            scores: Dictionary of posture scores
            
        Returns:
            True if insertion successful, False otherwise
        """
        if not self.enable_supabase_logging or self.supabase is None:
            return False
        
        try:
            # Prepare data
            data = {
                "id_usuario": self.user_id,
                "timestamp": datetime.datetime.now().isoformat(sep=" ", timespec="seconds"),
                "overall_risk": scores.get('overall', {}).get('risk', 'Unknown'),
                "overall_zone": scores.get('overall', {}).get('zone', 0),
            }
            
            # Add individual parameters
            for param in self.zones.keys():
                if param in scores:
                    data[f"{param}_angle"] = float(scores[param]['angle'])
                    data[f"{param}_zone"] = scores[param]['zone']
                    data[f"{param}_risk"] = scores[param]['risk']
                else:
                    data[f"{param}_angle"] = -1.0
                    data[f"{param}_zone"] = -1
                    data[f"{param}_risk"] = 'Not Detected'
            
            # Insert into database
            response = self.supabase.table("posture").insert(data).execute()
            
            if not hasattr(response, 'error') or not response.error:
                self.supabase_insert_count += 1
                return True
            return False
                
        except Exception as e:
            return False
    
    def calculate_neck_lateral_bend(self, left_ear, right_ear, left_shoulder, right_shoulder):
        """Calculate neck lateral bend angle from ear height differences."""
        shoulder_mid_y = (left_shoulder[1] + right_shoulder[1]) / 2
        left_ear_height = left_ear[1] - shoulder_mid_y
        right_ear_height = right_ear[1] - shoulder_mid_y
        ear_height_diff = abs(left_ear_height - right_ear_height)
        return min(ear_height_diff * 0.5, 50)
    
    def calculate_shoulder_alignment(self, left_shoulder, right_shoulder):
        """Calculate shoulder alignment tilt angle."""
        dx = right_shoulder[0] - left_shoulder[0]
        dy = right_shoulder[1] - left_shoulder[1]
        return math.degrees(math.atan2(abs(dy), abs(dx)))
    
    def calculate_vertical_angle(self, point1, point2):
        """Calculate angle relative to vertical axis."""
        dx = point2[0] - point1[0]
        dy = point2[1] - point1[1]
        return math.degrees(math.atan2(abs(dx), abs(dy)))
    
    def calculate_neck_flexion(self, nose, left_shoulder, right_shoulder):
        """Calculate forward head posture angle."""
        shoulder_mid = (
            (left_shoulder[0] + right_shoulder[0]) / 2,
            (left_shoulder[1] + right_shoulder[1]) / 2
        )
        horizontal_distance = abs(nose[0] - shoulder_mid[0])
        vertical_distance = abs(nose[1] - shoulder_mid[1])
        
        if vertical_distance > 0:
            forward_ratio = horizontal_distance / vertical_distance
            return min(forward_ratio * 30, 60)
        return 0
    
    def get_zone(self, angle, parameter_name):
        """Determine zone (0-4) based on angle thresholds."""
        thresholds = self.zones[parameter_name]
        
        if angle <= thresholds[0]:
            return 0
        elif angle <= thresholds[1]:
            return 1
        elif angle <= thresholds[2]:
            return 2
        elif angle <= thresholds[3]:
            return 3
        else:
            return 4
    
    def calculate_posture_scores(self, keypoints):
        """Calculate all posture scores from keypoints."""
        if keypoints is None or len(keypoints) == 0:
            return {}, None
        
        kps = keypoints[0]
        scores = {}
        keypoints_data = {}
        
        try:
            # Extract valid keypoints
            for idx, kp in enumerate(kps):
                if kp[2] > 0.3:
                    keypoints_data[idx] = (float(kp[0]), float(kp[1]))
            
            # Keypoint indices
            NOSE, LEFT_EAR, RIGHT_EAR = 0, 3, 4
            LEFT_SHOULDER, RIGHT_SHOULDER = 5, 6
            LEFT_ELBOW, RIGHT_ELBOW = 7, 8
            
            # Calculate neck lateral bend
            if all(k in keypoints_data for k in [LEFT_EAR, RIGHT_EAR, LEFT_SHOULDER, RIGHT_SHOULDER]):
                neck_angle = self.calculate_neck_lateral_bend(
                    keypoints_data[LEFT_EAR], keypoints_data[RIGHT_EAR],
                    keypoints_data[LEFT_SHOULDER], keypoints_data[RIGHT_SHOULDER]
                )
                scores['neck_lateral_bend'] = self.create_score(neck_angle, 'neck_lateral_bend')
            
            # Calculate neck flexion
            if all(k in keypoints_data for k in [NOSE, LEFT_SHOULDER, RIGHT_SHOULDER]):
                neck_flexion_angle = self.calculate_neck_flexion(
                    keypoints_data[NOSE], keypoints_data[LEFT_SHOULDER], keypoints_data[RIGHT_SHOULDER]
                )
                scores['neck_flexion'] = self.create_score(neck_flexion_angle, 'neck_flexion')
            
            # Calculate shoulder alignment
            if all(k in keypoints_data for k in [LEFT_SHOULDER, RIGHT_SHOULDER]):
                shoulder_angle = self.calculate_shoulder_alignment(
                    keypoints_data[LEFT_SHOULDER], keypoints_data[RIGHT_SHOULDER]
                )
                scores['shoulder_alignment'] = self.create_score(shoulder_angle, 'shoulder_alignment')
            
            # Calculate arm abduction
            arm_angles = []
            if all(k in keypoints_data for k in [LEFT_SHOULDER, LEFT_ELBOW]):
                left_arm_angle = self.calculate_vertical_angle(
                    keypoints_data[LEFT_SHOULDER], keypoints_data[LEFT_ELBOW]
                )
                arm_angles.append(left_arm_angle)
            
            if all(k in keypoints_data for k in [RIGHT_SHOULDER, RIGHT_ELBOW]):
                right_arm_angle = self.calculate_vertical_angle(
                    keypoints_data[RIGHT_SHOULDER], keypoints_data[RIGHT_ELBOW]
                )
                arm_angles.append(right_arm_angle)
            
            if arm_angles:
                max_arm_angle = max(arm_angles)
                scores['arm_abduction'] = self.create_score(max_arm_angle, 'arm_abduction')
            
            # Calculate overall score
            if scores:
                zones = [score['zone'] for score in scores.values() if score.get('zone') is not None]
                if zones:
                    max_zone = max(zones)
                    scores['overall'] = {
                        'zone': max_zone,
                        'risk': self.zone_risk[max_zone]
                    }
            
            return scores, keypoints_data
            
        except Exception as e:
            print(f"Score calculation error: {e}")
            return {}, None
    
    def create_score(self, angle, parameter_name):
        """Create standardized score dictionary."""
        zone = self.get_zone(angle, parameter_name)
        return {
            'angle': angle,
            'zone': zone,
            'risk': self.zone_risk[zone]
        }
    
    def draw_keypoints_with_confidence(self, image, results, confidence_threshold=0.3):
        """Draw keypoints and skeleton on image with confidence coloring."""
        img_with_keypoints = image.copy()
        
        for result in results:
            if result.keypoints is not None:
                for person_keypoints in result.keypoints.data:
                    keypoints = person_keypoints.cpu().numpy()
                    
                    # Draw skeleton
                    for start_idx, end_idx in self.skeleton:
                        if (start_idx < len(keypoints) and end_idx < len(keypoints) and
                            keypoints[start_idx][2] > confidence_threshold and 
                            keypoints[end_idx][2] > confidence_threshold):
                            
                            start_point = (int(keypoints[start_idx][0]), int(keypoints[start_idx][1]))
                            end_point = (int(keypoints[end_idx][0]), int(keypoints[end_idx][1]))
                            cv2.line(img_with_keypoints, start_point, end_point, (0, 255, 255), 2)
                    
                    # Draw keypoints
                    for idx, kp in enumerate(keypoints):
                        x, y, conf = kp
                        if conf > confidence_threshold:
                            color_intensity = int(255 * conf)
                            color = (0, color_intensity, 255 - color_intensity)
                            cv2.circle(img_with_keypoints, (int(x), int(y)), 5, color, -1)
        
        return img_with_keypoints
    
    def export_measurements(self, scores):
        """Export measurements to database at controlled rate."""
        current_time = time.time()
        
        if self.enable_supabase_logging and current_time - self.last_supabase_time >= self.supabase_interval:
            self.last_supabase_time = current_time
            self.insert_posture_measurement(scores)
    
    def process_frame(self, frame):
        """
        Main frame processing pipeline.
        
        Parameters:
            frame: Input video frame
            
        Returns:
            Tuple: (annotated_frame, posture_scores)
        """
        # Run YOLO inference
        results = self.model(frame)
        annotated_frame = frame.copy()
        
        # Draw keypoints
        annotated_frame = self.draw_keypoints_with_confidence(annotated_frame, results)
        
        # Calculate posture scores
        posture_scores = {}
        keypoints_raw = None
        
        for result in results:
            if result.keypoints is not None:
                for keypoints in result.keypoints.data:
                    posture_scores, _ = self.calculate_posture_scores([keypoints])
                    keypoints_raw = keypoints.cpu().numpy()
                    break
                break
        
        # Update pressure map
        if self.enable_pressure_map and posture_scores:
            self.update_pressure_map(posture_scores, keypoints_raw)
            annotated_frame = self.draw_pressure_map_on_frame(annotated_frame)
        
        # Export to database
        if posture_scores:
            self.export_measurements(posture_scores)
        
        return annotated_frame, posture_scores


def main():
    """Main execution function for standalone posture analysis."""
    scorer = PostureScorer(enable_supabase_logging=True, user_id=1, enable_pressure_map=True)
    
    # Initialize camera
    cap = cv2.VideoCapture(0)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    
    print("\n" + "="*70)
    print("POSTURE ANALYSIS WITH PRESSURE MAP")
    print("="*70)
    
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        
        # Mirror effect
        frame = cv2.flip(frame, 1)
        
        # Process frame
        annotated_frame, scores = scorer.process_frame(frame)
        
        # Display information
        y_offset = 30
        if scores:
            overall = scores.get('overall', {})
            overall_zone = overall.get('zone', 0)
            overall_color = scorer.zone_colors[overall_zone]
            
            cv2.putText(annotated_frame, f"Posture: {overall.get('risk', 'Unknown')} (Zone {overall_zone})", 
                       (10, y_offset), cv2.FONT_HERSHEY_SIMPLEX, 0.6, overall_color, 2)
            y_offset += 30
        
        # Show frame
        cv2.imshow('Posture Analysis', annotated_frame)
        
        # Handle key presses
        key = cv2.waitKey(1) & 0xFF
        if key == ord('q'):
            break
    
    # Cleanup
    cap.release()
    cv2.destroyAllWindows()
    print(f"Records sent: {scorer.supabase_insert_count}")


if __name__ == "__main__":
    main()
