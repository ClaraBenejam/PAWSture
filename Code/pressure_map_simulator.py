"""
Pressure map simulator for posture analysis.
Generates deterministic pressure heatmaps based on posture angles and risk zones.
Based on research papers about smart sitting posture monitoring.
"""

import numpy as np
import cv2
import time
import math


class PressureMapSimulator:
    """
    Deterministic pressure heatmap simulator (10x10 grid).
    Based on vision system detected angles and risk zones.
    """
    
    def __init__(self, update_rate_hz: float = 4.0, noise_level: float = 0.1):
        """
        Initialize pressure map simulator.
        
        Parameters:
            update_rate_hz: Update frequency in Hz
            noise_level: Gaussian noise intensity (0-1)
        """
        self.map_size = (10, 10)  # 10x10 cells
        self.pressure_map = np.zeros(self.map_size, dtype=np.float32)
        self.last_update_time = time.time()
        self.update_interval = 1.0 / update_rate_hz
        self.noise_level = noise_level
        
        # Simulation parameters
        self.base_pressure = 0.3
        self.max_pressure = 1.0
        
        # Posture parameter influence weights
        self.posture_factors = {
            'neck_lateral_bend': {'weight': 0.3, 'center_shift': (0, 0.2)},
            'neck_flexion': {'weight': 0.4, 'center_shift': (0.3, 0)},
            'shoulder_alignment': {'weight': 0.5, 'center_shift': (0, 0.25)},
            'arm_abduction': {'weight': 0.35, 'center_shift': (0.15, 0.15)},
            'overall': {'weight': 0.6, 'center_shift': (0.1, 0.1)}
        }
        
        # Anatomical regions (backrest: rows 0-4, seat: rows 5-9)
        self.regions = {
            'backrest': {'rows': (0, 4), 'cols': (0, 9), 'base_center': (2, 5), 'sensitivity': 1.2},
            'seat': {'rows': (5, 9), 'cols': (0, 9), 'base_center': (7, 5), 'sensitivity': 1.0}
        }
        
        # History for temporal smoothing
        self.pressure_history = []
        self.history_length = 5
    
    def _create_base_distribution(self, center: tuple, sigma: float = 2.0) -> np.ndarray:
        """
        Create 2D Gaussian distribution centered at given position.
        
        Parameters:
            center: (row, col) center position
            sigma: Standard deviation
            
        Returns:
            2D normalized Gaussian distribution
        """
        rows, cols = self.map_size
        x = np.arange(cols)
        y = np.arange(rows)
        xx, yy = np.meshgrid(x, y)
        
        # 2D Gaussian
        gaussian = np.exp(-((xx - center[1])**2 + (yy - center[0])**2) / (2 * sigma**2))
        
        # Normalize
        if np.max(gaussian) > 0:
            gaussian = gaussian / np.max(gaussian)
        
        return gaussian
    
    def _apply_posture_influence(self, scores: dict) -> np.ndarray:
        """
        Apply posture parameter influences to base pressure map.
        
        Parameters:
            scores: Dictionary of posture scores from vision system
            
        Returns:
            Pressure map influenced by posture
        """
        # Start with uniform base pressure
        base_map = np.ones(self.map_size) * self.base_pressure
        total_influence = np.zeros(self.map_size)
        
        # Apply each posture parameter's influence
        for param_name, score_data in scores.items():
            if param_name not in self.posture_factors:
                continue
                
            factor_config = self.posture_factors[param_name]
            angle = score_data.get('angle', 0)
            zone = score_data.get('zone', 0)
            
            # Calculate shift based on angle
            angle_rad = math.radians(angle)
            shift_row = factor_config['center_shift'][0] * angle * math.cos(angle_rad)
            shift_col = factor_config['center_shift'][1] * angle * math.sin(angle_rad)
            
            # Apply influence to each region
            for region_name, region_config in self.regions.items():
                base_center = region_config['base_center']
                adjusted_center = (
                    max(min(base_center[0] + shift_row, self.map_size[0]-1), 0),
                    max(min(base_center[1] + shift_col, self.map_size[1]-1), 0)
                )
                
                # Create region distribution
                region_dist = self._create_base_distribution(adjusted_center)
                
                # Apply region mask
                mask = np.zeros(self.map_size)
                rows_start, rows_end = region_config['rows']
                cols_start, cols_end = region_config['cols']
                mask[rows_start:rows_end+1, cols_start:cols_end+1] = 1
                region_dist = region_dist * mask
                
                # Weight by parameter importance and zone
                weight = factor_config['weight'] * (zone + 1) * region_config['sensitivity']
                total_influence += region_dist * weight
        
        # Combine base with influence
        influenced_map = base_map + total_influence
        return np.clip(influenced_map, 0, self.max_pressure)
    
    def _add_controlled_noise(self, pressure_map: np.ndarray) -> np.ndarray:
        """
        Add controlled Gaussian noise for natural variations.
        
        Parameters:
            pressure_map: Base pressure map
            
        Returns:
            Pressure map with added noise
        """
        noise = np.random.normal(0, self.noise_level, self.map_size)
        noise = cv2.GaussianBlur(noise, (3, 3), 0.5)  # Smooth noise
        noisy_map = pressure_map + noise
        return np.clip(noisy_map, 0, self.max_pressure)
    
    def _apply_temporal_smoothing(self, pressure_map: np.ndarray) -> np.ndarray:
        """
        Apply temporal smoothing using history buffer.
        
        Parameters:
            pressure_map: Current pressure map
            
        Returns:
            Temporally smoothed pressure map
        """
        self.pressure_history.append(pressure_map.copy())
        if len(self.pressure_history) > self.history_length:
            self.pressure_history.pop(0)
        
        if len(self.pressure_history) >= 2:
            return np.mean(self.pressure_history, axis=0)
        return pressure_map
    
    def update(self, posture_scores: dict) -> np.ndarray:
        """
        Update pressure map based on posture scores.
        
        Parameters:
            posture_scores: Dictionary of posture scores
            
        Returns:
            Updated pressure map or None if not time to update
        """
        current_time = time.time()
        
        # Check update interval
        if current_time - self.last_update_time < self.update_interval:
            return None
        
        self.last_update_time = current_time
        
        # Create base distribution if no scores
        if not posture_scores:
            self.pressure_map = np.ones(self.map_size) * self.base_pressure
        else:
            # Apply posture influence
            influenced_map = self._apply_posture_influence(posture_scores)
            
            # Add noise and smoothing
            noisy_map = self._add_controlled_noise(influenced_map)
            smoothed_map = self._apply_temporal_smoothing(noisy_map)
            
            self.pressure_map = smoothed_map
        
        return self.pressure_map.copy()
    
    def get_visualization(self, size: int = 200) -> np.ndarray:
        """
        Generate visualization of pressure map.
        
        Parameters:
            size: Visualization size in pixels
            
        Returns:
            BGR image of pressure heatmap
        """
        if self.pressure_map is None:
            return np.zeros((size, size, 3), dtype=np.uint8)
        
        # Resize and normalize
        resized = cv2.resize(self.pressure_map, (size, size), interpolation=cv2.INTER_LINEAR)
        normalized = (resized / self.max_pressure * 255).astype(np.uint8)
        
        # Apply colormap
        heatmap = cv2.applyColorMap(normalized, cv2.COLORMAP_JET)
        
        # Add grid lines
        cell_size = size // 10
        for i in range(11):
            cv2.line(heatmap, (i * cell_size, 0), (i * cell_size, size), (50, 50, 50), 1)
            cv2.line(heatmap, (0, i * cell_size), (size, i * cell_size), (50, 50, 50), 1)
        
        return heatmap
    
    def get_statistics(self) -> dict:
        """
        Calculate pressure map statistics.
        
        Returns:
            Dictionary of statistical measures
        """
        if self.pressure_map is None:
            return {}
        
        stats = {
            'mean_pressure': float(np.mean(self.pressure_map)),
            'max_pressure': float(np.max(self.pressure_map)),
            'min_pressure': float(np.min(self.pressure_map)),
            'pressure_std': float(np.std(self.pressure_map)),
        }
        
        # Calculate asymmetry index
        left_half = self.pressure_map[:, :5]
        right_half = self.pressure_map[:, 5:]
        total_mean = np.mean(left_half) + np.mean(right_half)
        
        if total_mean > 0:
            stats['asymmetry_index'] = abs(np.mean(left_half) - np.mean(right_half)) / total_mean
        
        # Regional statistics
        stats['backrest_mean'] = float(np.mean(self.pressure_map[:5, :]))
        stats['seat_mean'] = float(np.mean(self.pressure_map[5:, :]))
        
        return stats
    
    def reset(self):
        """Reset simulator to initial state."""
        self.pressure_map = np.ones(self.map_size) * self.base_pressure
        self.pressure_history = []
        self.last_update_time = time.time()


if __name__ == "__main__":
    # Example usage
    simulator = PressureMapSimulator(update_rate_hz=4.0, noise_level=0.08)
    
    # Sample posture scores
    example_scores = {
        'neck_lateral_bend': {'angle': 15.5, 'zone': 1, 'risk': 'Low'},
        'neck_flexion': {'angle': 25.2, 'zone': 2, 'risk': 'Medium'},
        'shoulder_alignment': {'angle': 8.7, 'zone': 1, 'risk': 'Low'},
        'arm_abduction': {'angle': 40.3, 'zone': 2, 'risk': 'Medium'},
        'overall': {'zone': 2, 'risk': 'Medium'}
    }
    
    # Test update
    pressure_map = simulator.update(example_scores)
    
    if pressure_map is not None:
        print("Pressure map generated successfully")
        print(f"Shape: {pressure_map.shape}")
        
        # Show visualization
        heatmap_viz = simulator.get_visualization(300)
        cv2.imshow("Pressure Map Example", heatmap_viz)
        cv2.waitKey(0)
        cv2.destroyAllWindows()
