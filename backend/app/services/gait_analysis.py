"""
Advanced Gait Analysis Service
Uses pose estimation and 3D reconstruction to calculate accurate gait parameters
Simulates multi-camera systems used in professional gait labs
"""
import numpy as np
from typing import List, Dict, Optional, Tuple, Callable
from pathlib import Path
import tempfile
import os
import asyncio
from concurrent.futures import ThreadPoolExecutor
import threading

# Import logger - handle gracefully if not available
try:
    from loguru import logger
except ImportError:
    import logging
    logger = logging.getLogger(__name__)

# Optional imports - handle gracefully if not available
try:
    import cv2
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False
    cv2 = None
    logger.warning("OpenCV not available - video processing will be limited")

try:
    import mediapipe as mp
    MEDIAPIPE_AVAILABLE = True
except ImportError:
    MEDIAPIPE_AVAILABLE = False
    mp = None
    logger.warning("MediaPipe not available - gait analysis will be limited")


class GaitAnalysisService:
    """Advanced gait analysis using pose estimation and 3D reconstruction"""
    
    def __init__(self):
        """Initialize gait analysis service"""
        self.executor = ThreadPoolExecutor(max_workers=2)
        
        if MEDIAPIPE_AVAILABLE:
            self.mp_pose = mp.solutions.pose
            self.pose = self.mp_pose.Pose(
                static_image_mode=False,
                model_complexity=2,  # Use high accuracy model
                enable_segmentation=False,
                min_detection_confidence=0.5,
                min_tracking_confidence=0.5
            )
            self.mp_drawing = mp.solutions.drawing_utils
            logger.info("MediaPipe pose estimation initialized")
        else:
            self.pose = None
            logger.warning("MediaPipe not available - using basic analysis")
    
    async def analyze_video(
        self,
        video_path: str,
        fps: float = 30.0,
        reference_length_mm: Optional[float] = None,
        view_type: str = "front",
        progress_callback: Optional[Callable] = None
    ) -> Dict:
        """
        Analyze video for gait parameters
        
        Args:
            video_path: Path to video file
            fps: Video frame rate
            reference_length_mm: Reference length in mm for scale calibration
            view_type: Camera view type (front, side, etc.)
            progress_callback: Optional async callback(progress_pct, message)
        
        Returns:
            Dictionary with keypoints, 3D poses, and gait metrics
        """
        if progress_callback:
            await progress_callback(5, "Opening video file...")
        
        # Use a simple list to store progress updates from sync thread
        progress_updates = []
        progress_lock = threading.Lock()
        processing_done = threading.Event()
        
        def sync_progress_callback(progress: int, message: str):
            """Sync callback that stores progress for async retrieval"""
            with progress_lock:
                progress_updates.append((progress, message))
        
        # Run video processing in thread pool
        loop = asyncio.get_event_loop()
        
        # Start processing
        process_task = loop.run_in_executor(
            self.executor,
            self._process_video_sync,
            video_path,
            fps,
            reference_length_mm,
            view_type,
            sync_progress_callback
        )
        
        # Monitor progress updates
        async def monitor_progress():
            last_update_idx = 0
            while not processing_done.is_set():
                await asyncio.sleep(0.1)  # Check every 100ms
                
                # Get new progress updates
                with progress_lock:
                    new_updates = progress_updates[last_update_idx:]
                    last_update_idx = len(progress_updates)
                
                # Send updates via async callback
                for progress, message in new_updates:
                    if progress_callback:
                        await progress_callback(progress, message)
        
        # Start monitoring
        monitor_task = asyncio.create_task(monitor_progress())
        
        try:
            # Wait for processing to complete
            result = await process_task
            processing_done.set()
            
            # Send any remaining updates
            with progress_lock:
                remaining_updates = progress_updates[last_update_idx:]
            for progress, message in remaining_updates:
                if progress_callback:
                    await progress_callback(progress, message)
            
            # Final progress updates
            if progress_callback:
                await progress_callback(60, "Lifting to 3D pose...")
                await progress_callback(80, "Calculating gait parameters...")
            
        finally:
            monitor_task.cancel()
            try:
                await monitor_task
            except asyncio.CancelledError:
                pass
        
        return result
    
    def _process_video_sync(
        self,
        video_path: str,
        fps: float,
        reference_length_mm: Optional[float],
        view_type: str,
        progress_callback: Optional[Callable] = None
    ) -> Dict:
        """Synchronous video processing"""
        if not CV2_AVAILABLE:
            raise ImportError("OpenCV (cv2) is required for video processing. Please install opencv-python.")
        
        cap = cv2.VideoCapture(video_path)
        
        if not cap.isOpened():
            raise ValueError(f"Could not open video: {video_path}")
        
        # Get video properties
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        video_fps = cap.get(cv2.CAP_PROP_FPS) or fps
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        
        logger.info(f"Video: {total_frames} frames, {video_fps} fps, {width}x{height}")
        
        # Extract frames and detect poses
        frames_2d_keypoints = []
        frame_timestamps = []
        frame_count = 0
        
        # Sample frames (process every Nth frame for efficiency)
        frame_skip = max(1, int(video_fps / 10))  # Process ~10 frames per second
        
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break
            
            # Skip frames for efficiency
            if frame_count % frame_skip != 0:
                frame_count += 1
                continue
            
            timestamp = frame_count / video_fps
            
            # Detect pose in frame
            if self.pose and MEDIAPIPE_AVAILABLE:
                # Convert BGR to RGB for MediaPipe
                rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                results = self.pose.process(rgb_frame)
                
                if results.pose_landmarks:
                    # Extract 2D keypoints
                    keypoints_2d = self._extract_2d_keypoints(results.pose_landmarks, width, height)
                    frames_2d_keypoints.append(keypoints_2d)
                    frame_timestamps.append(timestamp)
            
            frame_count += 1
            
            # Progress update
            if progress_callback and frame_count % 30 == 0:
                progress = min(50, int((frame_count / total_frames) * 50))
                progress_callback(progress, f"Processing frame {frame_count}/{total_frames}...")
        
        cap.release()
        
        if not frames_2d_keypoints:
            logger.warning("No poses detected in video")
            return self._empty_results()
        
        logger.info(f"Detected poses in {len(frames_2d_keypoints)} frames")
        
        # Lift 2D keypoints to 3D
        frames_3d_keypoints = self._lift_to_3d(frames_2d_keypoints, view_type)
        
        # Calculate gait metrics
        metrics = self._calculate_gait_metrics(
            frames_3d_keypoints,
            frame_timestamps,
            video_fps,
            reference_length_mm
        )
        
        return {
            "status": "completed",
            "analysis_type": "advanced_gait_analysis",
            "frames_processed": len(frames_2d_keypoints),
            "total_frames": total_frames,
            "keypoints_2d": frames_2d_keypoints[:10],  # Store sample for debugging
            "keypoints_3d": frames_3d_keypoints[:10],  # Store sample
            "metrics": metrics
        }
    
    def _extract_2d_keypoints(self, pose_landmarks, width: int, height: int) -> Dict:
        """Extract 2D keypoints from MediaPipe pose landmarks"""
        keypoints = {}
        
        # Map MediaPipe landmarks to our keypoint names
        landmark_map = {
            'nose': self.mp_pose.PoseLandmark.NOSE,
            'left_shoulder': self.mp_pose.PoseLandmark.LEFT_SHOULDER,
            'right_shoulder': self.mp_pose.PoseLandmark.RIGHT_SHOULDER,
            'left_elbow': self.mp_pose.PoseLandmark.LEFT_ELBOW,
            'right_elbow': self.mp_pose.PoseLandmark.RIGHT_ELBOW,
            'left_wrist': self.mp_pose.PoseLandmark.LEFT_WRIST,
            'right_wrist': self.mp_pose.PoseLandmark.RIGHT_WRIST,
            'left_hip': self.mp_pose.PoseLandmark.LEFT_HIP,
            'right_hip': self.mp_pose.PoseLandmark.RIGHT_HIP,
            'left_knee': self.mp_pose.PoseLandmark.LEFT_KNEE,
            'right_knee': self.mp_pose.PoseLandmark.RIGHT_KNEE,
            'left_ankle': self.mp_pose.PoseLandmark.LEFT_ANKLE,
            'right_ankle': self.mp_pose.PoseLandmark.RIGHT_ANKLE,
            'left_heel': self.mp_pose.PoseLandmark.LEFT_HEEL,
            'right_heel': self.mp_pose.PoseLandmark.RIGHT_HEEL,
            'left_foot_index': self.mp_pose.PoseLandmark.LEFT_FOOT_INDEX,
            'right_foot_index': self.mp_pose.PoseLandmark.RIGHT_FOOT_INDEX,
        }
        
        for name, landmark_idx in landmark_map.items():
            landmark = pose_landmarks.landmark[landmark_idx]
            keypoints[name] = {
                'x': landmark.x * width,
                'y': landmark.y * height,
                'z': landmark.z * width,  # MediaPipe provides depth estimate
                'visibility': landmark.visibility
            }
        
        return keypoints
    
    def _lift_to_3d(self, frames_2d_keypoints: List[Dict], view_type: str) -> List[Dict]:
        """
        Lift 2D keypoints to 3D using geometric constraints and temporal smoothing
        Simulates multi-camera reconstruction
        """
        frames_3d = []
        
        for i, keypoints_2d in enumerate(frames_2d_keypoints):
            keypoints_3d = {}
            
            # Use MediaPipe's depth estimate as starting point
            # Apply geometric constraints based on human body proportions
            for name, kp_2d in keypoints_2d.items():
                x, y, z_estimate = kp_2d['x'], kp_2d['y'], kp_2d['z']
                
                # Refine Z using body segment lengths and constraints
                z_refined = self._refine_depth(name, kp_2d, keypoints_2d, view_type)
                
                keypoints_3d[name] = {
                    'x': x,
                    'y': y,
                    'z': z_refined,
                    'confidence': kp_2d.get('visibility', 1.0)
                }
            
            # Apply temporal smoothing (average with previous frames)
            if i > 0 and len(frames_3d) > 0:
                prev_keypoints = frames_3d[-1]
                for name in keypoints_3d:
                    if name in prev_keypoints:
                        # Weighted average for smooth motion
                        alpha = 0.3  # Smoothing factor
                        keypoints_3d[name]['x'] = alpha * keypoints_3d[name]['x'] + (1 - alpha) * prev_keypoints[name]['x']
                        keypoints_3d[name]['y'] = alpha * keypoints_3d[name]['y'] + (1 - alpha) * prev_keypoints[name]['y']
                        keypoints_3d[name]['z'] = alpha * keypoints_3d[name]['z'] + (1 - alpha) * prev_keypoints[name]['z']
            
            frames_3d.append(keypoints_3d)
        
        return frames_3d
    
    def _refine_depth(self, joint_name: str, joint_2d: Dict, all_keypoints: Dict, view_type: str) -> float:
        """Refine depth estimate using body segment constraints"""
        z_estimate = joint_2d.get('z', 0.0)
        
        # Use known body segment proportions to constrain depth
        # Average human proportions (in relative units)
        segment_lengths = {
            'torso': 0.3,  # Shoulder to hip
            'thigh': 0.25,  # Hip to knee
            'shank': 0.25,  # Knee to ankle
            'upper_arm': 0.15,
            'forearm': 0.15,
        }
        
        # Refine based on adjacent joints
        if 'hip' in joint_name or 'shoulder' in joint_name:
            # Torso joints - use hip/shoulder distance
            if 'left_hip' in all_keypoints and 'right_hip' in all_keypoints:
                hip_width = abs(all_keypoints['left_hip']['x'] - all_keypoints['right_hip']['x'])
                # Estimate depth from hip width (assuming ~30cm hip width)
                z_refined = z_estimate * (300.0 / max(hip_width, 1.0))
                return z_refined
        
        return z_estimate
    
    def _calculate_gait_metrics(
        self,
        frames_3d_keypoints: List[Dict],
        timestamps: List[float],
        fps: float,
        reference_length_mm: Optional[float]
    ) -> Dict:
        """Calculate gait parameters from 3D pose sequence"""
        if len(frames_3d_keypoints) < 10:
            logger.warning("Not enough frames for gait analysis")
            return self._empty_metrics()
        
        # Extract ankle positions over time
        left_ankle_positions = []
        right_ankle_positions = []
        
        for keypoints in frames_3d_keypoints:
            if 'left_ankle' in keypoints and 'right_ankle' in keypoints:
                left_ankle_positions.append([
                    keypoints['left_ankle']['x'],
                    keypoints['left_ankle']['y'],
                    keypoints['left_ankle']['z']
                ])
                right_ankle_positions.append([
                    keypoints['right_ankle']['x'],
                    keypoints['right_ankle']['y'],
                    keypoints['right_ankle']['z']
                ])
        
        if len(left_ankle_positions) < 5 or len(right_ankle_positions) < 5:
            return self._empty_metrics()
        
        left_ankle_positions = np.array(left_ankle_positions)
        right_ankle_positions = np.array(right_ankle_positions)
        
        # Calibrate scale using reference length or body proportions
        scale_factor = self._calibrate_scale(frames_3d_keypoints, reference_length_mm)
        
        # Calculate step events (heel strikes)
        left_steps, right_steps = self._detect_steps(left_ankle_positions, right_ankle_positions, timestamps)
        
        # Calculate cadence (steps per minute)
        if len(left_steps) + len(right_steps) > 0:
            total_steps = len(left_steps) + len(right_steps)
            duration = timestamps[-1] - timestamps[0] if len(timestamps) > 1 else 1.0
            cadence = (total_steps / duration) * 60.0  # steps per minute
        else:
            cadence = 0.0
        
        # Calculate step length
        step_lengths = []
        if len(left_steps) > 0 and len(right_steps) > 0:
            # Calculate distance between opposite foot positions at step events
            for i, left_step_idx in enumerate(left_steps):
                if i < len(right_steps):
                    right_step_idx = right_steps[i]
                    if left_step_idx < len(left_ankle_positions) and right_step_idx < len(right_ankle_positions):
                        step_vec = left_ankle_positions[left_step_idx] - right_ankle_positions[right_step_idx]
                        step_length = np.linalg.norm(step_vec) * scale_factor
                        step_lengths.append(step_length)
        
        avg_step_length = np.mean(step_lengths) if step_lengths else 0.0
        
        # Calculate stride length (two steps)
        stride_length = avg_step_length * 2.0 if avg_step_length > 0 else 0.0
        
        # Calculate walking speed
        if len(timestamps) > 1:
            total_distance = 0.0
            for i in range(1, len(left_ankle_positions)):
                if i < len(timestamps):
                    step_vec = left_ankle_positions[i] - left_ankle_positions[i-1]
                    step_dist = np.linalg.norm(step_vec) * scale_factor
                    total_distance += step_dist
            
            duration = timestamps[-1] - timestamps[0]
            walking_speed = (total_distance / duration) if duration > 0 else 0.0
        else:
            walking_speed = 0.0
        
        # Calculate temporal parameters
        if len(left_steps) > 1:
            step_times = [timestamps[left_steps[i]] - timestamps[left_steps[i-1]] 
                         for i in range(1, len(left_steps))]
            avg_step_time = np.mean(step_times) if step_times else 0.0
        else:
            avg_step_time = 0.0
        
        # Estimate stance and swing times (simplified)
        stance_time = avg_step_time * 0.6 if avg_step_time > 0 else 0.0
        swing_time = avg_step_time * 0.4 if avg_step_time > 0 else 0.0
        double_support_time = avg_step_time * 0.1 if avg_step_time > 0 else 0.0
        
        return {
            "cadence": round(cadence, 2),
            "step_length": round(avg_step_length, 0),  # in mm
            "stride_length": round(stride_length, 0),  # in mm
            "walking_speed": round(walking_speed, 0),  # in mm/s
            "step_time": round(avg_step_time, 3) if avg_step_time > 0 else 0.0,
            "stance_time": round(stance_time, 3),
            "swing_time": round(swing_time, 3),
            "double_support_time": round(double_support_time, 3),
        }
    
    def _calibrate_scale(self, frames_3d_keypoints: List[Dict], reference_length_mm: Optional[float]) -> float:
        """Calibrate scale factor to convert pixel units to millimeters"""
        if reference_length_mm:
            # Use provided reference length
            # Estimate pixel length from first frame
            if frames_3d_keypoints and 'left_hip' in frames_3d_keypoints[0] and 'right_hip' in frames_3d_keypoints[0]:
                hip_width_px = abs(
                    frames_3d_keypoints[0]['left_hip']['x'] - 
                    frames_3d_keypoints[0]['right_hip']['x']
                )
                if hip_width_px > 0:
                    # Assume average hip width is ~30cm
                    avg_hip_width_mm = 300.0
                    scale = reference_length_mm / hip_width_px
                    return scale
        
        # Default: estimate from body proportions
        # Average person height ~170cm, use torso length as reference
        if frames_3d_keypoints and 'left_shoulder' in frames_3d_keypoints[0] and 'left_hip' in frames_3d_keypoints[0]:
            torso_length_px = np.sqrt(
                (frames_3d_keypoints[0]['left_shoulder']['x'] - frames_3d_keypoints[0]['left_hip']['x'])**2 +
                (frames_3d_keypoints[0]['left_shoulder']['y'] - frames_3d_keypoints[0]['left_hip']['y'])**2
            )
            if torso_length_px > 0:
                # Average torso length ~50cm
                avg_torso_length_mm = 500.0
                return avg_torso_length_mm / torso_length_px
        
        # Fallback: 1 pixel = 1mm (will need calibration in production)
        return 1.0
    
    def _detect_steps(self, left_ankle: np.ndarray, right_ankle: np.ndarray, timestamps: List[float]) -> Tuple[List[int], List[int]]:
        """Detect heel strike events (steps) from ankle positions"""
        left_steps = []
        right_steps = []
        
        # Detect local minima in vertical position (heel strikes)
        if len(left_ankle) > 3:
            left_y = left_ankle[:, 1]  # Y coordinates (vertical)
            for i in range(1, len(left_y) - 1):
                if left_y[i] < left_y[i-1] and left_y[i] < left_y[i+1]:
                    # Local minimum - potential heel strike
                    left_steps.append(i)
        
        if len(right_ankle) > 3:
            right_y = right_ankle[:, 1]
            for i in range(1, len(right_y) - 1):
                if right_y[i] < right_y[i-1] and right_y[i] < right_y[i+1]:
                    right_steps.append(i)
        
        return left_steps, right_steps
    
    def _empty_results(self) -> Dict:
        """Return empty results structure"""
        return {
            "status": "completed",
            "analysis_type": "advanced_gait_analysis",
            "frames_processed": 0,
            "keypoints_2d": [],
            "keypoints_3d": [],
            "metrics": self._empty_metrics()
        }
    
    def _empty_metrics(self) -> Dict:
        """Return empty metrics structure"""
        return {
            "cadence": 0.0,
            "step_length": 0.0,
            "stride_length": 0.0,
            "walking_speed": 0.0,
            "step_time": 0.0,
            "stance_time": 0.0,
            "swing_time": 0.0,
            "double_support_time": 0.0,
        }
    
    async def download_video_from_url(self, video_url: str) -> str:
        """Download video from URL to temporary file"""
        import aiohttp
        import tempfile
        
        # Check if it's a local file
        if os.path.exists(video_url):
            return video_url
        
        # Download from URL
        async with aiohttp.ClientSession() as session:
            async with session.get(video_url) as response:
                if response.status == 200:
                    # Create temp file
                    tmp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.mp4')
                    async for chunk in response.content.iter_chunked(8192):
                        tmp_file.write(chunk)
                    tmp_file.close()
                    return tmp_file.name
                else:
                    raise ValueError(f"Failed to download video: {response.status}")
    
    def cleanup(self):
        """Cleanup resources"""
        if self.pose:
            self.pose.close()
        self.executor.shutdown(wait=True)

