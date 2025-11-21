import cv2
import numpy as np
from ultralytics import YOLO
import math
import csv
import datetime
import time
from supabase import create_client, Client

class PostureScorer:
    def __init__(self):
        self.model = YOLO('yolo11n-pose.pt')
        
        # Expanded to 5 zones while maintaining the very low zone size
        self.zones = {
            'neck_lateral_bend': [5, 10, 20, 35],
            'neck_flexion': [9, 18, 30, 50],
            'shoulder_alignment': [5, 10, 20, 35],
            'arm_abduction': [13, 25, 45, 70],
        }
        
        # 5-level risk scale
        self.zone_risk = {
            0: "Very Low",
            1: "Low", 
            2: "Medium",
            3: "High",
            4: "Very High"
        }
        
        # Colors for 5 zones
        self.zone_colors = {
            0: (0, 255, 0),    # Green
            1: (0, 255, 255),  # Yellow
            2: (0, 165, 255),  # Orange
            3: (0, 0, 255),    # Red
            4: (128, 0, 128)   # Purple
        }
        
        # CSV configuration
        self.csv_file = f"posture_scores_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        self.last_csv_time = 0
        self.csv_interval = 0.2
        self.csv_delimiter = ';'
        
        # Supabase configuration
        self.SUPABASE_URL = "https://sunsfqthmwotlbfcgmay.supabase.co"
        self.SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InN1bnNmcXRobXdvdGxiZmNnbWF5Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjM0MDQwNjcsImV4cCI6MjA3ODk4MDA2N30.dLSgRjiiK4dDrYcwenp2RHBkMdQxYglficyyRripRN8"
        self.supabase = None
        self.last_supabase_time = 0
        self.supabase_interval = 0.2
        
        self.init_supabase()
        self.init_csv()

    def init_supabase(self):
        """Initialize Supabase client"""
        try:
            self.supabase = create_client(self.SUPABASE_URL, self.SUPABASE_KEY)
            print("Supabase client initialized successfully")
        except Exception as e:
            print(f"Error initializing Supabase: {e}")
            self.supabase = None

    def init_csv(self):
        """Initialize CSV file with headers"""
        headers = ['timestamp', 'overall_risk', 'overall_zone']
        for param in self.zones.keys():
            headers.extend([f'{param}_angle', f'{param}_zone', f'{param}_risk'])
        
        with open(self.csv_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f, delimiter=self.csv_delimiter)
            writer.writerow(headers)
        print(f"CSV logging started: {self.csv_file}")

    def insert_posture_measurement(self, scores):
        """Insert posture measurement into Supabase"""
        if self.supabase is None:
            return False
        
        try:
            data = {
                "timestamp": datetime.datetime.now().isoformat(sep=" ", timespec="seconds"),
                "overall_risk": scores.get('overall', {}).get('risk', 'Unknown'),
                "overall_zone": scores.get('overall', {}).get('zone', 0),
            }
            
            for param in self.zones.keys():
                if param in scores:
                    data[f"{param}_angle"] = float(scores[param]['angle'])
                    data[f"{param}_zone"] = scores[param]['zone']
                    data[f"{param}_risk"] = scores[param]['risk']
                else:
                    data[f"{param}_angle"] = -1.0
                    data[f"{param}_zone"] = -1
                    data[f"{param}_risk"] = 'Not Detected'
            
            response = self.supabase.table("posture").insert(data).execute()
            
            if hasattr(response, 'error') and response.error:
                return False
            else:
                return True
                
        except Exception as e:
            return False

    def export_to_csv(self, scores):
        """Export current scores to CSV"""
        current_time = time.time()
        if current_time - self.last_csv_time < self.csv_interval:
            return
        
        self.last_csv_time = current_time
        timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
        
        row = [timestamp, scores.get('overall', {}).get('risk', 'Unknown'), scores.get('overall', {}).get('zone', 0)]
        
        for param in self.zones.keys():
            if param in scores:
                row.extend([
                    f"{scores[param]['angle']:.2f}",
                    scores[param]['zone'],
                    scores[param]['risk']
                ])
            else:
                row.extend(['-1', -1, 'Not Detected'])
        
        with open(self.csv_file, 'a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f, delimiter=self.csv_delimiter)
            writer.writerow(row)

    def export_measurements(self, scores):
        """Export measurements to both CSV and Supabase"""
        current_time = time.time()
        if current_time - self.last_csv_time < self.csv_interval:
            return
        
        self.last_csv_time = current_time
        self.export_to_csv(scores)
        
        if current_time - self.last_supabase_time >= self.supabase_interval:
            self.last_supabase_time = current_time
            self.insert_posture_measurement(scores)

    def calculate_neck_lateral_bend(self, left_ear, right_ear, left_shoulder, right_shoulder):
        """Calculate neck lateral bend using ear height difference"""
        shoulder_mid_y = (left_shoulder[1] + right_shoulder[1]) / 2
        left_ear_height = left_ear[1] - shoulder_mid_y
        right_ear_height = right_ear[1] - shoulder_mid_y
        ear_height_diff = abs(left_ear_height - right_ear_height)
        angle = min(ear_height_diff * 0.5, 50)
        return angle

    def calculate_shoulder_alignment(self, left_shoulder, right_shoulder):
        """Calculate shoulder alignment tilt"""
        dx = right_shoulder[0] - left_shoulder[0]
        dy = right_shoulder[1] - left_shoulder[1]
        angle_rad = math.atan2(abs(dy), abs(dx))
        angle_deg = math.degrees(angle_rad)
        return angle_deg

    def calculate_vertical_angle(self, point1, point2):
        """Calculate angle relative to vertical axis"""
        dx = point2[0] - point1[0]
        dy = point2[1] - point1[1]
        angle_rad = math.atan2(abs(dx), abs(dy))
        angle_deg = math.degrees(angle_rad)
        return angle_deg

    def calculate_neck_flexion(self, nose, left_shoulder, right_shoulder):
        """Calculate forward head posture"""
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
        """Determine zone (0-4) based on angle thresholds"""
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
        """Calculate all posture scores"""
        if keypoints is None or len(keypoints) == 0:
            return {}
        
        kps = keypoints[0]
        scores = {}
        
        try:
            NOSE, LEFT_EAR, RIGHT_EAR = 0, 3, 4
            LEFT_SHOULDER, RIGHT_SHOULDER = 5, 6
            LEFT_ELBOW, RIGHT_ELBOW = 7, 8
            
            keypoint_data = {}
            for idx, kp in enumerate(kps):
                if kp[2] > 0.3:
                    keypoint_data[idx] = (float(kp[0]), float(kp[1]))
            
            if all(k in keypoint_data for k in [LEFT_EAR, RIGHT_EAR, LEFT_SHOULDER, RIGHT_SHOULDER]):
                neck_angle = self.calculate_neck_lateral_bend(
                    keypoint_data[LEFT_EAR], keypoint_data[RIGHT_EAR],
                    keypoint_data[LEFT_SHOULDER], keypoint_data[RIGHT_SHOULDER]
                )
                scores['neck_lateral_bend'] = self.create_score(neck_angle, 'neck_lateral_bend')

            if all(k in keypoint_data for k in [NOSE, LEFT_SHOULDER, RIGHT_SHOULDER]):
                neck_flexion_angle = self.calculate_neck_flexion(
                    keypoint_data[NOSE], keypoint_data[LEFT_SHOULDER], keypoint_data[RIGHT_SHOULDER]
                )
                scores['neck_flexion'] = self.create_score(neck_flexion_angle, 'neck_flexion')

            if all(k in keypoint_data for k in [LEFT_SHOULDER, RIGHT_SHOULDER]):
                shoulder_angle = self.calculate_shoulder_alignment(
                    keypoint_data[LEFT_SHOULDER], keypoint_data[RIGHT_SHOULDER]
                )
                scores['shoulder_alignment'] = self.create_score(shoulder_angle, 'shoulder_alignment')

            arm_angles = []
            
            if all(k in keypoint_data for k in [LEFT_SHOULDER, LEFT_ELBOW]):
                left_arm_angle = self.calculate_vertical_angle(
                    keypoint_data[LEFT_SHOULDER], keypoint_data[LEFT_ELBOW]
                )
                arm_angles.append(left_arm_angle)
                scores['left_arm_abduction'] = self.create_score(left_arm_angle, 'arm_abduction')

            if all(k in keypoint_data for k in [RIGHT_SHOULDER, RIGHT_ELBOW]):
                right_arm_angle = self.calculate_vertical_angle(
                    keypoint_data[RIGHT_SHOULDER], keypoint_data[RIGHT_ELBOW]
                )
                arm_angles.append(right_arm_angle)
                scores['right_arm_abduction'] = self.create_score(right_arm_angle, 'arm_abduction')

            if arm_angles:
                max_arm_angle = max(arm_angles)
                scores['arm_abduction'] = self.create_score(max_arm_angle, 'arm_abduction')

            if scores:
                zones = [score['zone'] for score in scores.values() if score.get('zone') is not None]
                if zones:
                    max_zone = max(zones)
                    scores['overall'] = {
                        'zone': max_zone,
                        'risk': self.zone_risk[max_zone]
                    }

            return scores
            
        except Exception as e:
            return {}

    def create_score(self, angle, parameter_name):
        """Create standardized score entry"""
        zone = self.get_zone(angle, parameter_name)
        return {
            'angle': angle,
            'zone': zone,
            'risk': self.zone_risk[zone]
        }

    def process_frame(self, frame):
        """Process frame and return scores"""
        results = self.model(frame)
        annotated_frame = frame.copy()
        posture_scores = {}
        
        for result in results:
            if result.keypoints is not None:
                for keypoints in result.keypoints.data:
                    posture_scores = self.calculate_posture_scores([keypoints])
                    break
                break
        
        if posture_scores:
            self.export_measurements(posture_scores)
        
        return annotated_frame, posture_scores

def main():
    scorer = PostureScorer()
    cap = cv2.VideoCapture(0)
    
    print("Posture Scoring System - Zones & Risk Only")
    print("Press 'q' to quit")
    
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        
        annotated_frame, scores = scorer.process_frame(frame)
        
        # Display ONLY posture zones and risk information
        y_offset = 30
        
        if scores:
            overall = scores.get('overall', {})
            overall_zone = overall.get('zone', 0)
            overall_color = scorer.zone_colors[overall_zone]
            
            # Display overall posture
            cv2.putText(annotated_frame, f"Posture: {overall.get('risk', 'Unknown')} (Zone {overall_zone})", 
                       (10, y_offset), cv2.FONT_HERSHEY_SIMPLEX, 0.6, overall_color, 2)
            y_offset += 30
            
            # Display individual parameters
            for param, data in scores.items():
                if param != 'overall':
                    zone = data['zone']
                    color = scorer.zone_colors[zone]
                    
                    # Clean parameter names for display
                    display_name = param.replace('_', ' ').title()
                    text = f"{display_name}: {data['risk']} (Zone {zone})"
                    
                    cv2.putText(annotated_frame, text, (10, y_offset), 
                               cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)
                    y_offset += 20
        
        cv2.imshow('Posture Scoring', annotated_frame)
        
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break
    
    cap.release()
    cv2.destroyAllWindows()
    print(f"CSV file saved: {scorer.csv_file}")

if __name__ == "__main__":
    main()
