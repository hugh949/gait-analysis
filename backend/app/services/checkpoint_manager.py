"""
Checkpoint Manager for Gait Analysis
Saves intermediate results after each processing step to allow resuming from stable checkpoints
"""
import os
import json
import pickle
import numpy as np
from typing import Dict, Optional, List, Any
from pathlib import Path
from loguru import logger

# File locking (optional - may not be available on all systems)
try:
    import fcntl
    HAS_FCNTL = True
except ImportError:
    HAS_FCNTL = False


class CheckpointManager:
    """Manages checkpoints for gait analysis processing steps"""
    
    def __init__(self, analysis_id: str, checkpoint_dir: Optional[str] = None):
        """
        Initialize checkpoint manager
        
        Args:
            analysis_id: Unique analysis identifier
            checkpoint_dir: Directory to store checkpoints (default: /home/site/checkpoints)
        """
        self.analysis_id = analysis_id
        self.checkpoint_dir = checkpoint_dir or os.getenv(
            "CHECKPOINT_DIR",
            "/home/site/checkpoints"
        )
        self.checkpoint_dir = Path(self.checkpoint_dir)
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"CheckpointManager initialized for analysis {analysis_id}, checkpoint_dir={self.checkpoint_dir}")
    
    def _get_checkpoint_path(self, step_name: str) -> Path:
        """Get path for a specific step checkpoint"""
        return self.checkpoint_dir / f"{self.analysis_id}_{step_name}.checkpoint"
    
    def _get_metadata_path(self) -> Path:
        """Get path for checkpoint metadata"""
        return self.checkpoint_dir / f"{self.analysis_id}_metadata.json"
    
    def save_step_1(self, frames_2d_keypoints: List[List], frame_timestamps: List[float], 
                    total_frames: int, video_fps: float, processing_stats: Dict) -> bool:
        """
        Save Step 1 (Pose Estimation) checkpoint
        
        Args:
            frames_2d_keypoints: List of 2D keypoint frames
            frame_timestamps: List of frame timestamps
            total_frames: Total frames in video
            video_fps: Video FPS
            processing_stats: Processing statistics
            
        Returns:
            True if saved successfully, False otherwise
        """
        try:
            checkpoint_path = self._get_checkpoint_path("step1_2d_keypoints")
            metadata_path = self._get_metadata_path()
            
            logger.info(f"💾 Saving Step 1 checkpoint: {len(frames_2d_keypoints)} 2D keypoint frames")
            
            # Save 2D keypoints (convert numpy arrays to lists for JSON serialization)
            checkpoint_data = {
                'frames_2d_keypoints': [
                    [[float(kp[0]), float(kp[1]), float(kp[2])] if len(kp) >= 3 else [float(kp[0]), float(kp[1]), 0.0]
                     for kp in frame] if frame else []
                    for frame in frames_2d_keypoints
                ],
                'frame_timestamps': [float(ts) for ts in frame_timestamps],
                'total_frames': total_frames,
                'video_fps': float(video_fps),
                'processing_stats': processing_stats,
                'step': 'step_1_pose_estimation',
                'completed': True
            }
            
            # Save checkpoint with file locking
            temp_path = checkpoint_path.with_suffix('.tmp')
            with open(temp_path, 'wb') as f:
                if HAS_FCNTL:
                    fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                pickle.dump(checkpoint_data, f)
                if HAS_FCNTL:
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)
            
            # Atomic rename
            temp_path.replace(checkpoint_path)
            
            # Update metadata
            metadata = self._load_metadata()
            metadata['step_1_pose_estimation'] = {
                'completed': True,
                'checkpoint_file': str(checkpoint_path),
                'frames_count': len(frames_2d_keypoints),
                'timestamp': time.time()
            }
            self._save_metadata(metadata)
            
            logger.info(f"✅ Step 1 checkpoint saved: {checkpoint_path} ({len(frames_2d_keypoints)} frames)")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to save Step 1 checkpoint: {e}", exc_info=True)
            return False
    
    def load_step_1(self) -> Optional[Dict]:
        """
        Load Step 1 (Pose Estimation) checkpoint
        
        Returns:
            Dictionary with checkpoint data or None if not found
        """
        try:
            checkpoint_path = self._get_checkpoint_path("step1_2d_keypoints")
            
            if not checkpoint_path.exists():
                logger.debug(f"Step 1 checkpoint not found: {checkpoint_path}")
                return None
            
            logger.info(f"📂 Loading Step 1 checkpoint: {checkpoint_path}")
            
            with open(checkpoint_path, 'rb') as f:
                if HAS_FCNTL:
                    fcntl.flock(f.fileno(), fcntl.LOCK_SH)
                checkpoint_data = pickle.load(f)
                if HAS_FCNTL:
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)
            
            logger.info(f"✅ Step 1 checkpoint loaded: {len(checkpoint_data.get('frames_2d_keypoints', []))} frames")
            return checkpoint_data
            
        except Exception as e:
            logger.error(f"❌ Failed to load Step 1 checkpoint: {e}", exc_info=True)
            return None
    
    def save_step_2(self, frames_3d_keypoints: List[List], frames_2d_keypoints: List[List]) -> bool:
        """
        Save Step 2 (3D Lifting) checkpoint
        
        Args:
            frames_3d_keypoints: List of 3D keypoint frames
            frames_2d_keypoints: List of 2D keypoint frames (for reference)
            
        Returns:
            True if saved successfully, False otherwise
        """
        try:
            checkpoint_path = self._get_checkpoint_path("step2_3d_keypoints")
            metadata_path = self._get_metadata_path()
            
            logger.info(f"💾 Saving Step 2 checkpoint: {len(frames_3d_keypoints)} 3D keypoint frames")
            
            checkpoint_data = {
                'frames_3d_keypoints': [
                    [[float(kp[0]), float(kp[1]), float(kp[2])] if len(kp) >= 3 else [float(kp[0]), float(kp[1]), 0.0]
                     for kp in frame] if frame else []
                    for frame in frames_3d_keypoints
                ],
                'frames_2d_keypoints': [
                    [[float(kp[0]), float(kp[1]), float(kp[2])] if len(kp) >= 3 else [float(kp[0]), float(kp[1]), 0.0]
                     for kp in frame] if frame else []
                    for frame in frames_2d_keypoints
                ],
                'step': 'step_2_3d_lifting',
                'completed': True
            }
            
            temp_path = checkpoint_path.with_suffix('.tmp')
            with open(temp_path, 'wb') as f:
                if HAS_FCNTL:
                    fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                pickle.dump(checkpoint_data, f)
                if HAS_FCNTL:
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)
            
            temp_path.replace(checkpoint_path)
            
            metadata = self._load_metadata()
            metadata['step_2_3d_lifting'] = {
                'completed': True,
                'checkpoint_file': str(checkpoint_path),
                'frames_count': len(frames_3d_keypoints),
                'timestamp': time.time()
            }
            self._save_metadata(metadata)
            
            logger.info(f"✅ Step 2 checkpoint saved: {checkpoint_path} ({len(frames_3d_keypoints)} frames)")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to save Step 2 checkpoint: {e}", exc_info=True)
            return False
    
    def load_step_2(self) -> Optional[Dict]:
        """Load Step 2 (3D Lifting) checkpoint"""
        try:
            checkpoint_path = self._get_checkpoint_path("step2_3d_keypoints")
            
            if not checkpoint_path.exists():
                return None
            
            logger.info(f"📂 Loading Step 2 checkpoint: {checkpoint_path}")
            
            with open(checkpoint_path, 'rb') as f:
                if HAS_FCNTL:
                    fcntl.flock(f.fileno(), fcntl.LOCK_SH)
                checkpoint_data = pickle.load(f)
                if HAS_FCNTL:
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)
            
            logger.info(f"✅ Step 2 checkpoint loaded: {len(checkpoint_data.get('frames_3d_keypoints', []))} frames")
            return checkpoint_data
            
        except Exception as e:
            logger.error(f"❌ Failed to load Step 2 checkpoint: {e}", exc_info=True)
            return None
    
    def save_step_3(self, metrics: Dict, frames_3d_keypoints: List[List]) -> bool:
        """
        Save Step 3 (Gait Metrics) checkpoint
        
        Args:
            metrics: Calculated gait metrics
            frames_3d_keypoints: List of 3D keypoint frames (for reference)
            
        Returns:
            True if saved successfully, False otherwise
        """
        try:
            checkpoint_path = self._get_checkpoint_path("step3_metrics")
            
            logger.info(f"💾 Saving Step 3 checkpoint: {len(metrics)} metrics")
            
            checkpoint_data = {
                'metrics': {k: float(v) if isinstance(v, (int, float, np.number)) else v 
                           for k, v in metrics.items()},
                'frames_3d_keypoints': [
                    [[float(kp[0]), float(kp[1]), float(kp[2])] if len(kp) >= 3 else [float(kp[0]), float(kp[1]), 0.0]
                     for kp in frame] if frame else []
                    for frame in frames_3d_keypoints
                ],
                'step': 'step_3_metrics_calculation',
                'completed': True
            }
            
            temp_path = checkpoint_path.with_suffix('.tmp')
            with open(temp_path, 'wb') as f:
                if HAS_FCNTL:
                    fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                pickle.dump(checkpoint_data, f)
                if HAS_FCNTL:
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)
            
            temp_path.replace(checkpoint_path)
            
            metadata = self._load_metadata()
            metadata['step_3_metrics_calculation'] = {
                'completed': True,
                'checkpoint_file': str(checkpoint_path),
                'metrics_count': len(metrics),
                'timestamp': time.time()
            }
            self._save_metadata(metadata)
            
            logger.info(f"✅ Step 3 checkpoint saved: {checkpoint_path}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to save Step 3 checkpoint: {e}", exc_info=True)
            return False
    
    def load_step_3(self) -> Optional[Dict]:
        """Load Step 3 (Gait Metrics) checkpoint"""
        try:
            checkpoint_path = self._get_checkpoint_path("step3_metrics")
            
            if not checkpoint_path.exists():
                return None
            
            logger.info(f"📂 Loading Step 3 checkpoint: {checkpoint_path}")
            
            with open(checkpoint_path, 'rb') as f:
                if HAS_FCNTL:
                    fcntl.flock(f.fileno(), fcntl.LOCK_SH)
                checkpoint_data = pickle.load(f)
                if HAS_FCNTL:
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)
            
            logger.info(f"✅ Step 3 checkpoint loaded: {len(checkpoint_data.get('metrics', {}))} metrics")
            return checkpoint_data
            
        except Exception as e:
            logger.error(f"❌ Failed to load Step 3 checkpoint: {e}", exc_info=True)
            return None
    
    def _load_metadata(self) -> Dict:
        """Load checkpoint metadata"""
        metadata_path = self._get_metadata_path()
        if metadata_path.exists():
            try:
                with open(metadata_path, 'r') as f:
                    if HAS_FCNTL:
                        fcntl.flock(f.fileno(), fcntl.LOCK_SH)
                    metadata = json.load(f)
                    if HAS_FCNTL:
                        fcntl.flock(f.fileno(), fcntl.LOCK_UN)
                return metadata
            except Exception as e:
                logger.warning(f"Failed to load metadata: {e}")
        return {}
    
    def _save_metadata(self, metadata: Dict) -> None:
        """Save checkpoint metadata"""
        metadata_path = self._get_metadata_path()
        temp_path = metadata_path.with_suffix('.tmp')
        try:
            with open(temp_path, 'w') as f:
                if HAS_FCNTL:
                    fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                json.dump(metadata, f, indent=2)
                if HAS_FCNTL:
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)
            temp_path.replace(metadata_path)
        except Exception as e:
            logger.error(f"Failed to save metadata: {e}", exc_info=True)
    
    def get_completed_steps(self) -> Dict[str, bool]:
        """Get which steps have been completed (have checkpoints)"""
        metadata = self._load_metadata()
        return {
            'step_1_pose_estimation': metadata.get('step_1_pose_estimation', {}).get('completed', False),
            'step_2_3d_lifting': metadata.get('step_2_3d_lifting', {}).get('completed', False),
            'step_3_metrics_calculation': metadata.get('step_3_metrics_calculation', {}).get('completed', False)
        }
    
    def cleanup(self) -> None:
        """Clean up checkpoints for this analysis"""
        try:
            for step_file in ['step1_2d_keypoints', 'step2_3d_keypoints', 'step3_metrics']:
                checkpoint_path = self._get_checkpoint_path(step_file)
                if checkpoint_path.exists():
                    checkpoint_path.unlink()
            
            metadata_path = self._get_metadata_path()
            if metadata_path.exists():
                metadata_path.unlink()
            
            logger.info(f"🧹 Cleaned up checkpoints for analysis {self.analysis_id}")
        except Exception as e:
            logger.warning(f"Failed to cleanup checkpoints: {e}")


# Import time for timestamps
import time
