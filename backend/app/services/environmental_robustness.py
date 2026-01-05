"""
Environmental Robustness Service
Handles noise reduction and temporal smoothing for keypoint trajectories
"""
import numpy as np
from typing import List, Dict, Optional
from loguru import logger
from filterpy.kalman import KalmanFilter


class KalmanDenoiser:
    """
    Kalman filter-based denoiser for keypoint trajectories
    """
    
    def __init__(self, num_joints: int = 17, process_noise: float = 0.01):
        self.num_joints = num_joints
        self.process_noise = process_noise  # ✅ FIX: Set before creating filters
        self.filters = [self._create_filter() for _ in range(num_joints)]
    
    def _create_filter(self):
        """Create a Kalman filter for a single joint"""
        kf = KalmanFilter(dim_x=6, dim_z=3)  # 3D position, 3D velocity
        kf.x = np.zeros(6)  # Initial state: [x, y, z, vx, vy, vz]
        kf.F = np.eye(6)  # State transition matrix
        kf.H = np.hstack([np.eye(3), np.zeros((3, 3))])  # Measurement matrix
        kf.P *= 1000.  # Initial uncertainty
        kf.R = np.eye(3) * 1.0  # Measurement noise
        kf.Q = np.eye(6) * self.process_noise  # Process noise - ✅ Now process_noise is available
        return kf
    
    def denoise(self, keypoints: np.ndarray) -> np.ndarray:
        """
        Apply Kalman filtering to keypoint sequence
        
        Args:
            keypoints: (num_frames, num_joints, 3) array of 3D keypoints
            
        Returns:
            Denoised keypoint sequence
        """
        num_frames, num_joints, _ = keypoints.shape
        denoised = np.zeros_like(keypoints)
        
        for frame_idx in range(num_frames):
            for joint_idx in range(num_joints):
                kf = self.filters[joint_idx]
                measurement = keypoints[frame_idx, joint_idx, :]
                
                kf.predict()
                kf.update(measurement)
                
                denoised[frame_idx, joint_idx, :] = kf.x[:3]
        
        return denoised


class EnvironmentalRobustnessService:
    """
    Main service for environmental robustness processing
    Handles noise reduction and temporal smoothing
    """
    
    def __init__(self):
        self.denoiser = KalmanDenoiser()
        logger.info("Environmental robustness service initialized")
    
    def apply_robustness(
        self,
        keypoints_3d: np.ndarray,
        confidence: Optional[np.ndarray] = None,
        first_frame: Optional[np.ndarray] = None
    ) -> Dict[str, np.ndarray]:
        """
        Apply environmental robustness processing to keypoints
        
        Args:
            keypoints_3d: (num_frames, num_joints, 3) array of 3D keypoints
            confidence: (num_frames, num_joints) optional confidence scores
            first_frame: Optional first frame for reference detection
            
        Returns:
            Dictionary with denoised keypoints and metadata
        """
        try:
            # Apply Kalman filtering for temporal smoothing
            denoised_keypoints = self.denoiser.denoise(keypoints_3d)
            
            return {
                'keypoints_3d': denoised_keypoints,
                'confidence': confidence if confidence is not None else np.ones((keypoints_3d.shape[0], keypoints_3d.shape[1])),
                'processing_applied': ['kalman_filtering']
            }
        except Exception as e:
            logger.error(f"Error applying environmental robustness: {e}")
            # Return original keypoints on error
            return {
                'keypoints_3d': keypoints_3d,
                'confidence': confidence if confidence is not None else np.ones((keypoints_3d.shape[0], keypoints_3d.shape[1])),
                'processing_applied': [],
                'error': str(e)
            }
