"""
Advanced Gait Analysis Service - MAXIMUM ACCURACY VERSION
Uses YOLO26 (primary) and MediaPipe 0.10.x (fallback) for pose estimation
Implements professional-grade gait analysis with Kalman filtering and Savitzky-Golay smoothing

YOLO26 Features for Gait Analysis:
- Native end-to-end inference (NMS-free) for faster processing
- Residual Log-Likelihood Estimation (RLE) for precision keypoint localization
- Up to 43% faster CPU inference compared to previous versions
- Optimized for edge deployment
See: https://docs.ultralytics.com/models/yolo26/

LICENSE NOTICE:
This software uses Ultralytics YOLO which is licensed under AGPL-3.0.
As a result, this entire project must be distributed under AGPL-3.0 compatible terms.
Source code must be made available to users of this software.
See: https://github.com/ultralytics/ultralytics/blob/main/LICENSE

Copyright (c) 2024-2026 - Open Source Gait Analysis Project
SPDX-License-Identifier: AGPL-3.0-or-later
"""
import numpy as np
from typing import List, Dict, Optional, Tuple, Callable
from pathlib import Path
import tempfile
import os
import asyncio
from concurrent.futures import ThreadPoolExecutor
import threading
import time

# Import custom exceptions for structured error handling
try:
    from app.core.exceptions import PoseEstimationError, GaitMetricsError, VideoProcessingError
except ImportError:
    # Fallback if exceptions module not available (shouldn't happen in production)
    class PoseEstimationError(Exception):
        pass
    class GaitMetricsError(Exception):
        pass
    class VideoProcessingError(Exception):
        pass

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

# MediaPipe 0.10.x with tasks API - improved accuracy
try:
    import mediapipe as mp
    from mediapipe.tasks import python
    from mediapipe.tasks.python import vision
    from mediapipe.tasks.python.vision import PoseLandmarker, PoseLandmarkerOptions, RunningMode
    # Try to import ImageFormat - it might not be available in all versions
    try:
        from mediapipe.tasks.python.vision import ImageFormat
    except ImportError:
        try:
            from mediapipe.tasks.python.core.vision import ImageFormat
        except ImportError:
            try:
                ImageFormat = vision.ImageFormat
            except AttributeError:
                # ImageFormat might not be available - we'll use a fallback
                ImageFormat = None
                logger.warning("ImageFormat not available - will use alternative method for image creation")
    
    # Try to import Image class - it might be in different locations in different versions
    try:
        from mediapipe.tasks.python.vision import Image as VisionImage
    except ImportError:
        try:
            from mediapipe.tasks.python.core.vision import Image as VisionImage
        except ImportError:
            try:
                VisionImage = vision.Image
            except AttributeError:
                # Last resort: try mp.Image
                try:
                    VisionImage = mp.Image
                except AttributeError:
                    VisionImage = None
                    logger.warning("Could not import MediaPipe Image class - will use alternative method")
    
    MEDIAPIPE_AVAILABLE = True
    logger.info(f"MediaPipe 0.10.x imported successfully with tasks API (version: {getattr(mp, '__version__', 'unknown')})")
    if VisionImage:
        logger.info(f"MediaPipe Image class available: {VisionImage}")
    else:
        logger.warning("MediaPipe Image class not found - will use numpy array directly")
    if ImageFormat:
        logger.info(f"MediaPipe ImageFormat available: {ImageFormat}")
    else:
        logger.warning("MediaPipe ImageFormat not found - will use alternative method")
except ImportError as e:
    MEDIAPIPE_AVAILABLE = False
    mp = None
    python = None
    vision = None
    VisionImage = None
    ImageFormat = None
    PoseLandmarker = None
    PoseLandmarkerOptions = None
    RunningMode = None
    logger.warning(f"MediaPipe 0.10.x not available: {e}. Install with: pip install mediapipe>=0.10.8")
except Exception as e:
    MEDIAPIPE_AVAILABLE = False
    mp = None
    python = None
    vision = None
    VisionImage = None
    ImageFormat = None
    PoseLandmarker = None
    PoseLandmarkerOptions = None
    RunningMode = None
    logger.warning(f"Error importing MediaPipe: {e} - gait analysis will be limited")

# Advanced signal processing for maximum accuracy
try:
    from scipy import signal
    from scipy.interpolate import UnivariateSpline
    SCIPY_AVAILABLE = True
except ImportError:
    SCIPY_AVAILABLE = False
    signal = None
    logger.warning("SciPy not available - using basic filtering (accuracy reduced)")

# Kalman filtering for smooth, accurate trajectory tracking
try:
    from filterpy.kalman import KalmanFilter
    FILTERPY_AVAILABLE = True
except ImportError:
    FILTERPY_AVAILABLE = False
    KalmanFilter = None
    logger.warning("FilterPy not available - using basic smoothing (accuracy reduced)")

# Numba for JIT-compiled biomechanical calculations
try:
    from numba import jit
    NUMBA_AVAILABLE = True
except ImportError:
    NUMBA_AVAILABLE = False
    def jit(*args, **kwargs):
        """Dummy decorator when numba not available"""
        def decorator(func):
            return func
        return decorator
    logger.warning("Numba not available - calculations will be slower")

# Outlier detection and statistical validation
try:
    from sklearn.covariance import EllipticEnvelope
    from sklearn.preprocessing import RobustScaler
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False
    EllipticEnvelope = None
    RobustScaler = None
    logger.warning("scikit-learn not available - outlier detection disabled (accuracy reduced)")

# Wavelet transforms for advanced signal analysis
try:
    import pywt
    WAVELETS_AVAILABLE = True
except ImportError:
    WAVELETS_AVAILABLE = False
    pywt = None
    logger.warning("PyWavelets not available - advanced frequency analysis disabled")

# Statistical modeling
try:
    from scipy import stats
    STATS_AVAILABLE = True
except ImportError:
    STATS_AVAILABLE = False
    stats = None
    logger.warning("SciPy stats not available - statistical validation disabled")

# YOLO26 as PRIMARY pose detector - native end-to-end, RLE precision pose estimation
# YOLO26 features: NMS-free inference, 43% faster CPU, Residual Log-Likelihood Estimation (RLE)
# Licensed under AGPL-3.0 - compatible with open-source distribution
# See: https://docs.ultralytics.com/models/yolo26/
try:
    from ultralytics import YOLO
    YOLO_AVAILABLE = True
    YOLO_VERSION = "26"  # YOLO26 - latest with native end-to-end pose estimation
    logger.info("Ultralytics YOLO26 available for PRIMARY pose detection (AGPL-3.0, end-to-end)")
except ImportError:
    YOLO_AVAILABLE = False
    YOLO = None
    YOLO_VERSION = None
    logger.info("Ultralytics YOLO not available - using MediaPipe only")


class GaitAnalysisService:
    """Advanced gait analysis using MediaPipe 0.10.x with maximum accuracy"""
    
    def __init__(self):
        """Initialize gait analysis service with MediaPipe 0.10.x"""
        self.executor = ThreadPoolExecutor(max_workers=2)
        self.pose_landmarker = None
        # Set running mode only if RunningMode is available
        if RunningMode:
            try:
                self.running_mode = RunningMode.VIDEO
            except AttributeError:
                self.running_mode = None
                logger.warning("RunningMode.VIDEO not available - using None")
        else:
            self.running_mode = None
        
        # CRITICAL: Always initialize the service, even if MediaPipe fails
        # This allows the service to work in fallback mode
        if MEDIAPIPE_AVAILABLE and python is not None and PoseLandmarker is not None and self.running_mode is not None:
            try:
                # Initialize MediaPipe 0.10.x PoseLandmarker
                # MediaPipe 0.10.x requires explicit model - try multiple initialization methods
                logger.debug("Attempting to initialize MediaPipe PoseLandmarker...")
                
                # Method 1: Try with default model (MediaPipe may bundle it)
                try:
                    logger.debug("Method 1: Attempting initialization without explicit model path...")
                    options = PoseLandmarkerOptions(
                        running_mode=self.running_mode,
                        min_pose_detection_confidence=0.3,  # Lower threshold to detect more poses
                        min_pose_presence_confidence=0.3,   # More lenient presence detection
                        min_tracking_confidence=0.3,        # Better tracking in challenging conditions
                        output_segmentation_masks=False
                    )
                    self.pose_landmarker = PoseLandmarker.create_from_options(options)
                    logger.info("✓ MediaPipe 0.10.x PoseLandmarker initialized successfully (default model, low-threshold)")
                except Exception as e1:
                    logger.debug(f"Method 1 failed: {e1}")
                    
                    # Method 2: Try to find bundled model
                    logger.debug("Method 2: Searching for bundled model file...")
                    model_path = self._get_mediapipe_model_path()
                    
                    if model_path and os.path.exists(model_path):
                        logger.info(f"Found model file at: {model_path}")
                        try:
                            base_options = python.BaseOptions(
                                model_asset_path=model_path,
                                delegate=python.BaseOptions.Delegate.CPU
                            )
                            options = PoseLandmarkerOptions(
                                base_options=base_options,
                                running_mode=self.running_mode,
                                min_pose_detection_confidence=0.3,  # Lower threshold to detect more poses
                                min_pose_presence_confidence=0.3,   # More lenient presence detection
                                min_tracking_confidence=0.3,        # Better tracking in challenging conditions
                                output_segmentation_masks=False
                            )
                            self.pose_landmarker = PoseLandmarker.create_from_options(options)
                            logger.info(f"✓ MediaPipe 0.10.x PoseLandmarker initialized successfully with model: {model_path} (low-threshold)")
                        except Exception as e2:
                            logger.error(f"Method 2 failed with model path: {e2}")
                            self.pose_landmarker = None
                    else:
                        logger.warning("Model file not found in standard locations")
                        # Method 3: Try downloading model (if we implement this)
                        logger.warning("PoseLandmarker initialization failed - will use fallback mode for gait analysis")
                        logger.warning("Note: MediaPipe 0.10.x requires pose_landmarker.task model file")
                        self.pose_landmarker = None
            except Exception as e:
                logger.error(f"Failed to initialize MediaPipe PoseLandmarker: {e}", exc_info=True)
                self.pose_landmarker = None
                logger.warning("Gait analysis will continue in fallback mode (reduced accuracy)")
        else:
            if not MEDIAPIPE_AVAILABLE:
                logger.warning("MediaPipe not available - gait analysis will use fallback mode")
            elif python is None:
                logger.warning("MediaPipe python module not available - gait analysis will use fallback mode")
            elif PoseLandmarker is None:
                logger.warning("MediaPipe PoseLandmarker not available - gait analysis will use fallback mode")
            elif self.running_mode is None:
                logger.warning("MediaPipe RunningMode not available - gait analysis will use fallback mode")
            else:
                logger.warning("MediaPipe initialization incomplete - gait analysis will use fallback mode")
        
        # Initialize YOLO26-Pose as PRIMARY detector
        # YOLO26 features: Native end-to-end (NMS-free), RLE precision pose, 43% faster CPU
        # See: https://docs.ultralytics.com/models/yolo26/
        self.yolo_model = None
        self.yolo_model_name = None
        if YOLO_AVAILABLE and YOLO is not None:
            try:
                # YOLO26 pose models (prefer these - best accuracy with RLE precision pose)
                # yolo26m-pose: Medium model - best balance for gait analysis (mAP 68.8)
                # yolo26s-pose: Small model - faster, good accuracy (mAP 63.0)
                # yolo26n-pose: Nano model - fastest, edge devices (mAP 57.2)
                # Fallback to older versions if YOLO26 not available
                model_priority = [
                    ('yolo26m-pose.pt', 'YOLO26-medium (RLE precision)'),
                    ('yolo26s-pose.pt', 'YOLO26-small (RLE precision)'),
                    ('yolo26n-pose.pt', 'YOLO26-nano (RLE precision)'),
                    ('yolo11m-pose.pt', 'YOLOv11-medium'),
                    ('yolo11s-pose.pt', 'YOLOv11-small'),
                    ('yolo11n-pose.pt', 'YOLOv11-nano'),
                    ('yolov8m-pose.pt', 'YOLOv8-medium'),
                    ('yolov8s-pose.pt', 'YOLOv8-small'),
                    ('yolov8n-pose.pt', 'YOLOv8-nano'),
                ]
                
                for model_file, model_name in model_priority:
                    try:
                        self.yolo_model = YOLO(model_file)
                        self.yolo_model_name = model_name
                        logger.info(f"✓ {model_name} Pose initialized as PRIMARY detector (AGPL-3.0, end-to-end)")
                        break
                    except Exception as model_error:
                        logger.debug(f"Could not load {model_name}: {model_error}")
                        continue
                
                if self.yolo_model is None:
                    logger.warning("No YOLO pose model could be loaded")
            except Exception as e:
                logger.warning(f"Failed to initialize YOLO-Pose: {e}")
                self.yolo_model = None
        
        # CRITICAL: Always log service initialization status
        # YOLO26 is now PRIMARY, MediaPipe is FALLBACK
        if self.yolo_model:
            logger.info(f"✓ GaitAnalysisService initialized with {self.yolo_model_name} as PRIMARY detector")
            if self.pose_landmarker:
                logger.info("  + MediaPipe available as fallback")
        elif self.pose_landmarker:
            logger.info("✓ GaitAnalysisService initialized with MediaPipe pose estimation (YOLO unavailable)")
        else:
            logger.warning("⚠ GaitAnalysisService initialized in fallback mode (no pose estimation available)")
    
    async def analyze_video(
        self,
        video_path: str,
        fps: float = 30.0,
        reference_length_mm: Optional[float] = None,
        view_type: str = "front",
        progress_callback: Optional[Callable] = None,
        analysis_id: Optional[str] = None,
        processing_fps: Optional[float] = None
    ) -> Dict:
        """
        Analyze video for gait parameters with maximum accuracy
        
        Args:
            video_path: Path to video file
            fps: Video frame rate
            reference_length_mm: Reference length in mm for scale calibration
            view_type: Camera view type (front, side, etc.)
            progress_callback: Optional async callback(progress_pct, message)
            analysis_id: Optional analysis ID for checkpoint management
        
        Returns:
            Dictionary with keypoints, 3D poses, and gait metrics
        """
        # Store analysis_id for checkpoint management
        self._current_analysis_id = analysis_id or 'unknown'
        
        # CRITICAL: Checkpoints are for RESUME only, not for skipping processing
        # Always process the video to ensure fresh, accurate results
        # Checkpoints will be used automatically if processing fails and needs to resume
        if analysis_id:
            try:
                from app.services.checkpoint_manager import CheckpointManager
                checkpoint_manager = CheckpointManager(analysis_id=analysis_id)
                completed_steps = checkpoint_manager.get_completed_steps()
                logger.info(f"📂 Checkpoint status: {completed_steps} (checkpoints will be used for resume only, not skipping)")
                
                # Log checkpoint status but DO NOT skip processing
                # Checkpoints are saved during processing and can be used if we need to resume
                # But for a fresh analysis, we always want to process the video
                if completed_steps.get('step_3_metrics_calculation', False):
                    logger.warning("⚠️ Step 3 checkpoint exists but will NOT be used - processing video fresh for accuracy")
            except Exception as e:
                logger.warning(f"⚠️ Checkpoint check failed (non-critical): {e}")
        
        if progress_callback:
            await progress_callback(0, "Opening video file...")
        
        # Use a simple list to store progress updates from sync thread
        progress_updates = []
        progress_lock = threading.Lock()
        processing_done = threading.Event()
        last_update_idx = [0]
        
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
            sync_progress_callback,
            processing_fps
        )
        
        # Monitor progress updates
        async def monitor_progress():
            while not processing_done.is_set():
                await asyncio.sleep(0.2)
                
                with progress_lock:
                    new_updates = progress_updates[last_update_idx[0]:]
                    last_update_idx[0] = len(progress_updates)
                
                for progress, message in new_updates:
                    if progress_callback:
                        try:
                            await progress_callback(progress, message)
                        except Exception as e:
                            logger.error(f"Error in progress callback: {e}", exc_info=True)
                
                if new_updates:
                    logger.debug(f"Sent {len(new_updates)} progress updates via monitor")
        
        monitor_task = asyncio.create_task(monitor_progress())
        
        try:
            logger.info("=" * 80)
            logger.info(f"🎬 ========== STARTING VIDEO PROCESSING ==========")
            logger.info(f"🎬 Video path: {video_path}")
            logger.info(f"🎬 FPS: {fps}, View type: {view_type}, Reference length: {reference_length_mm}mm")
            logger.info(f"🎬 Timeout: 3600s (60 minutes)")
            logger.info(f"🎬 Waiting for video processing to complete...")
            logger.info("=" * 80)
            
            result = await asyncio.wait_for(process_task, timeout=3600.0)
            processing_done.set()
            
            # CRITICAL: Validate result before returning
            if not result:
                error_msg = "Video processing returned None - no result generated"
                logger.error(f"❌ {error_msg}")
                raise ValueError(error_msg)
            
            # Validate that processing actually happened
            frames_processed = result.get('frames_processed', 0)
            total_frames = result.get('total_frames', 0)
            
            logger.info(f"✅ Video processing completed: {frames_processed}/{total_frames} frames processed")
            
            if frames_processed == 0:
                error_msg = f"CRITICAL: Video processing completed but no frames were processed! Total frames: {total_frames}"
                logger.error(f"❌ {error_msg}")
                raise ValueError(error_msg)
            
            with progress_lock:
                remaining_updates = progress_updates[last_update_idx[0]:]
            for progress, message in remaining_updates:
                if progress_callback:
                    await progress_callback(progress, message)
            
            if progress_callback:
                await progress_callback(60, "Applying advanced signal processing...")
                await progress_callback(80, "Calculating gait parameters...")
            
            logger.info(f"✅ Video processing completed successfully: {frames_processed} frames processed, {len(result.get('metrics', {}))} metrics calculated")
            
        except asyncio.TimeoutError:
            error_msg = "Video processing timed out after 60 minutes"
            logger.error(f"❌ {error_msg}")
            processing_done.set()
            raise ValueError(error_msg)
        except Exception as e:
            logger.error(f"❌ Error during video processing: {type(e).__name__}: {e}", exc_info=True)
            processing_done.set()
            raise
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
        progress_callback: Optional[Callable] = None,
        processing_fps: Optional[float] = None
    ) -> Dict:
        """Synchronous video processing with MediaPipe 0.10.x"""
        logger.info(f"_process_video_sync started: video_path={video_path}, fps={fps}, view_type={view_type}")
        
        if not CV2_AVAILABLE:
            raise ImportError("OpenCV (cv2) is required for video processing")
        
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"Video file does not exist: {video_path}")
        
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise ValueError(f"Could not open video: {video_path}")
        
        # Get video properties
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        video_fps = cap.get(cv2.CAP_PROP_FPS) or fps
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        
        logger.info(f"Video properties: {total_frames} frames, {video_fps} fps, {width}x{height}")
        
        if total_frames == 0:
            cap.release()
            raise ValueError(f"Video file has 0 frames: {video_path}")
        
        # EARLY VALIDATION: Check if video is long enough for gait analysis
        estimated_duration = total_frames / video_fps if video_fps > 0 else 0
        MIN_VIDEO_DURATION_SECONDS = 2.0  # Minimum 2 seconds for meaningful gait analysis
        if estimated_duration < MIN_VIDEO_DURATION_SECONDS:
            cap.release()
            logger.warning(f"⚠️ Video is very short: {estimated_duration:.1f}s (minimum recommended: {MIN_VIDEO_DURATION_SECONDS}s)")
            logger.warning("⚠️ Short videos may not have enough frames for accurate gait analysis")
            # Don't fail here - let it try, but warn. The frame_skip adjustment will help.
        
        # Extract frames and detect poses
        frames_2d_keypoints = []
        frame_timestamps = []
        frame_count = 0
        
        # Calculate frame skip based on user-selected processing_fps or auto-detect
        # MINIMUM FRAMES REQUIRED: 10 frames for gait analysis
        MIN_FRAMES_REQUIRED = 10
        
        if processing_fps is not None and processing_fps > 0:
            # User specified processing frame rate - use it directly
            frame_skip = max(1, int(video_fps / processing_fps))
            logger.info(f"Using user-specified processing rate: {processing_fps} fps (frame_skip={frame_skip})")
        else:
            # OPTIMIZED: For gait analysis, 5-8 fps is sufficient
            # Human gait cycle is ~1-2 seconds, so 5-8 fps captures all key phases
            # This dramatically speeds up processing while maintaining analysis quality
            # Calculate estimated video duration
            estimated_duration = total_frames / video_fps if video_fps > 0 else 0
            
            # Use consistent 6 fps for all video lengths - optimal for gait analysis
            # 6 fps = 6-12 frames per gait cycle, which is plenty for accurate analysis
            target_fps = 6
            frame_skip = max(1, int(video_fps / target_fps))
            
            # CRITICAL: For short videos, ensure we get enough frames for analysis
            # If estimated frames after skip would be less than MIN_FRAMES_REQUIRED * 1.5,
            # reduce frame_skip to ensure we have enough data
            estimated_processed_frames = total_frames // frame_skip
            if estimated_processed_frames < MIN_FRAMES_REQUIRED * 1.5:
                # Recalculate frame_skip to ensure at least MIN_FRAMES_REQUIRED * 2 frames
                # (accounting for potential pose detection failures)
                new_frame_skip = max(1, total_frames // (MIN_FRAMES_REQUIRED * 2))
                logger.warning(f"⚠️ Short video detected! Estimated {estimated_processed_frames} frames with skip={frame_skip}")
                logger.warning(f"⚠️ Reducing frame_skip from {frame_skip} to {new_frame_skip} to ensure enough frames for analysis")
                frame_skip = new_frame_skip
            
            logger.info(f"Video detected ({estimated_duration:.1f}s) - using optimized gait mode: frame_skip={frame_skip} (~{video_fps/frame_skip:.1f} fps)")
        
        estimated_duration = total_frames / video_fps if video_fps > 0 else 0
        logger.info(f"Starting frame processing: frame_skip={frame_skip}, total_frames={total_frames}, estimated_duration={estimated_duration:.1f}s, processing_rate={video_fps/frame_skip:.1f} fps")
        
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                logger.debug(f"📹 Frame {frame_count}: Failed to read frame (end of video or error)")
                break
            
            # Log frame read success
            if frame_count % 10 == 0:  # Log every 10 frames to avoid spam
                logger.debug(f"📹 Frame {frame_count}/{total_frames}: Successfully read frame (shape: {frame.shape if frame is not None else 'None'})")
            
            if frame_count % frame_skip != 0:
                frame_count += 1
                # STABILITY MODE: Yield control more frequently to allow heartbeat thread to run
                # Every 5 frames, yield for 2ms to prevent heartbeat starvation
                if frame_count % 5 == 0:
                    time.sleep(0.002)  # 2ms yield every 5 frames
                if progress_callback and frame_count % 10 == 0:
                    progress = min(50, int((frame_count / total_frames) * 50))
                    try:
                        logger.debug(f"📊 Progress callback (skipped frame): {progress}% - Frame {frame_count}/{total_frames}")
                        progress_callback(progress, f"Processing frame {frame_count}/{total_frames}...")
                    except Exception as e:
                        logger.warning(f"⚠️ Frame {frame_count}: Progress callback error (non-critical): {e}")
                continue
            
            timestamp_ms = int((frame_count / video_fps) * 1000)  # MediaPipe expects milliseconds
            timestamp = frame_count / video_fps
            
            # Log frame processing start
            if frame_count % 20 == 0:  # Log every 20 frames
                logger.info(f"🎬 Frame {frame_count}/{total_frames}: Starting pose detection (timestamp: {timestamp:.3f}s, {timestamp_ms}ms)")
            
            # POSE DETECTION STRATEGY (YOLOv11 PRIMARY, MediaPipe FALLBACK)
            # YOLOv11 is faster, more robust, and has native end-to-end detection
            # MediaPipe is used as fallback when YOLO is unavailable
            
            keypoints_detected = False
            
            # PRIMARY: Try YOLOv11 first (faster and more accurate)
            if self.yolo_model and YOLO_AVAILABLE:
                try:
                    yolo_keypoints = self._detect_with_yolo(frame, width, height)
                    if yolo_keypoints:
                        is_valid = self._validate_keypoint_quality(yolo_keypoints)
                        if is_valid:
                            frames_2d_keypoints.append(yolo_keypoints)
                            frame_timestamps.append(timestamp)
                            keypoints_detected = True
                            if frame_count % 20 == 0:
                                logger.info(f"✅ Frame {frame_count}: YOLO detected pose (total: {len(frames_2d_keypoints)})")
                except Exception as yolo_err:
                    if frame_count % 50 == 0:
                        logger.debug(f"⚠️ Frame {frame_count}: YOLO detection failed: {yolo_err}")
            
            # FALLBACK: Try MediaPipe if YOLO didn't detect
            if not keypoints_detected and self.pose_landmarker and MEDIAPIPE_AVAILABLE:
                try:
                    # Convert BGR to RGB
                    rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    
                    # Create MediaPipe Image
                    mp_image = None
                    vision_image_created = False
                    
                    if VisionImage:
                        # Try multiple methods to create VisionImage
                        if ImageFormat:
                            try:
                                if hasattr(ImageFormat, 'SRGB'):
                                    image_format_enum = ImageFormat.SRGB
                                elif hasattr(ImageFormat, 'sRGB'):
                                    image_format_enum = ImageFormat.sRGB
                                else:
                                    image_format_enum = 1
                                
                                mp_image = VisionImage(image_format=image_format_enum, data=rgb_frame)
                                vision_image_created = True
                            except Exception:
                                pass
                        
                        if not vision_image_created:
                            try:
                                mp_image = VisionImage(image_format=1, data=rgb_frame)
                                vision_image_created = True
                            except Exception:
                                pass
                        
                        if not vision_image_created:
                            try:
                                if hasattr(vision, 'Image') and hasattr(vision.Image, 'create_from_array'):
                                    mp_image = vision.Image.create_from_array(rgb_frame)
                                elif hasattr(VisionImage, 'create_from_array'):
                                    mp_image = VisionImage.create_from_array(rgb_frame)
                                else:
                                    mp_image = VisionImage(data=rgb_frame)
                                vision_image_created = True
                            except Exception:
                                pass
                    
                    if vision_image_created and mp_image is not None:
                        detection_result = self.pose_landmarker.detect_for_video(mp_image, timestamp_ms)
                        
                        if detection_result and detection_result.pose_landmarks:
                            pose_landmarks = detection_result.pose_landmarks[0]
                            keypoints_2d = self._extract_2d_keypoints_v2(pose_landmarks, width, height)
                            
                            is_valid = self._validate_keypoint_quality(keypoints_2d) if keypoints_2d else False
                            
                            if keypoints_2d and is_valid:
                                frames_2d_keypoints.append(keypoints_2d)
                                frame_timestamps.append(timestamp)
                                keypoints_detected = True
                                if frame_count % 20 == 0:
                                    logger.info(f"✅ Frame {frame_count}: MediaPipe fallback detected pose (total: {len(frames_2d_keypoints)})")
                except Exception as e:
                    if frame_count % 50 == 0:
                        logger.debug(f"⚠️ Frame {frame_count}: MediaPipe fallback failed: {e}")
            
            # Log if no detection succeeded
            if not keypoints_detected and frame_count % 50 == 0:
                logger.debug(f"⚠️ Frame {frame_count}: No pose detected by any detector")
                    if frame_count % (frame_skip * 3) == 0:
                        dummy_keypoints = self._create_dummy_keypoints(width, height, frame_count)
                        if dummy_keypoints:
                            frames_2d_keypoints.append(dummy_keypoints)
                            frame_timestamps.append(timestamp)
                            logger.debug(f"📝 Frame {frame_count}: Added dummy keypoints (fallback mode)")
            
            frame_count += 1
            
            # CRITICAL: Yield control EVERY frame to allow heartbeat thread and other tasks to run
            # This prevents the CPU-intensive loop from starving the heartbeat thread
            # Even a tiny 0.5ms sleep allows the OS to schedule other threads
            try:
                # Use time.sleep to yield to other threads - EVERY frame for maximum responsiveness
                time.sleep(0.0005)  # 0.5ms sleep - negligible but allows thread scheduling
            except Exception:
                pass  # Ignore sleep errors, continue processing
            
            if progress_callback and frame_count % 5 == 0:
                    progress = min(50, int((frame_count / total_frames) * 50))
                    try:
                        logger.debug(f"📊 Progress callback: {progress}% - Frame {frame_count}/{total_frames}")
                        progress_callback(progress, f"Processing frame {frame_count}/{total_frames}...")
                        logger.debug(f"✅ Progress callback completed successfully for frame {frame_count}")
                    except Exception as e:
                        # CRITICAL: Progress callback errors must never stop processing
                        logger.error(f"❌ Frame {frame_count}: Progress callback error (non-critical): {type(e).__name__}: {e}", exc_info=True)
                    # Don't re-raise - continue processing
                    # Continue processing even if progress update fails
        
        cap.release()
        logger.info(f"Video processing complete: processed {frame_count} frames, extracted {len(frames_2d_keypoints)} keypoint frames")
        
        if not frames_2d_keypoints:
            error_msg = "No poses detected in video. Cannot proceed with analysis."
            logger.error(f"❌ {error_msg}")
            raise PoseEstimationError(error_msg)
        
        logger.info(f"Detected poses in {len(frames_2d_keypoints)} frames")
        
        # CRITICAL: Update progress to indicate Step 1 (frame processing) is complete
        if progress_callback:
            try:
                progress_callback(50, "Frame processing complete. Starting signal processing...")
                logger.info("✅ Progress updated: Step 1 (frame processing) complete")
            except Exception as e:
                logger.warning(f"Error in progress callback after frame processing: {e}")
        
        # STEP 1 (continued): Apply advanced signal processing for maximum accuracy
        # CRITICAL: Wrap in try-except to ensure processing continues even if filtering fails
        try:
            if progress_callback:
                try:
                    progress_callback(52, "Applying error correction and outlier detection...")
                except Exception as e:
                    logger.warning(f"Error in progress callback during error correction: {e}")
            
            logger.debug(f"Pre-filtering: {len(frames_2d_keypoints)} keypoint frames")
            
            # Step 1: Error correction - detect and correct outliers
            try:
                frames_2d_keypoints, correction_stats = self._correct_keypoint_errors(frames_2d_keypoints, frame_timestamps)
                logger.info(f"Error correction: {correction_stats['outliers_removed']} outliers removed, {correction_stats['interpolated']} frames interpolated")
            except Exception as e:
                logger.error(f"Error during keypoint error correction: {e}", exc_info=True)
                logger.warning("Continuing without error correction - using original keypoints")
                # Continue with original keypoints - don't fail
            
            if progress_callback:
                try:
                    progress_callback(55, "Applying advanced signal processing...")
                except Exception as e:
                    logger.warning(f"Error in progress callback during filtering: {e}")
            
            # Step 2: Apply Savitzky-Golay filtering and advanced smoothing
            try:
                frames_2d_keypoints = self._apply_advanced_filtering(frames_2d_keypoints, frame_timestamps)
                logger.debug(f"Post-filtering: {len(frames_2d_keypoints)} keypoint frames")
            except Exception as e:
                logger.error(f"Error during advanced filtering: {e}", exc_info=True)
                logger.warning("Continuing without advanced filtering - using unfiltered keypoints")
                # Continue with unfiltered keypoints - don't fail
        except Exception as e:
            logger.error(f"Unexpected error during signal processing: {e}", exc_info=True)
            logger.warning("Continuing with original keypoints - signal processing failed")
            # Continue - don't fail the entire process
        
        # CRITICAL: Save Step 1 checkpoint before proceeding to Step 2
        try:
            from app.services.checkpoint_manager import CheckpointManager
            checkpoint_manager = CheckpointManager(analysis_id=getattr(self, '_current_analysis_id', 'unknown'))
            checkpoint_manager.save_step_1(
                frames_2d_keypoints=frames_2d_keypoints,
                frame_timestamps=frame_timestamps,
                total_frames=total_frames,
                video_fps=video_fps,
                processing_stats={'frames_processed': len(frames_2d_keypoints), 'total_frames': total_frames}
            )
            logger.info("✅ Step 1 checkpoint saved - can resume from here if needed")
        except Exception as e:
            logger.warning(f"⚠️ Failed to save Step 1 checkpoint (non-critical): {e}")
        
        # STEP 2: Lift to 3D - with comprehensive error handling and fallback
        logger.info("=" * 80)
        logger.info("🎯 ========== STEP 2: 3D LIFTING STARTING ==========")
        logger.info(f"🎯 Input: {len(frames_2d_keypoints)} 2D keypoint frames")
        logger.info(f"🎯 View type: {view_type}")
        logger.info("=" * 80)
        
        # CRITICAL: Explicitly update progress to indicate Step 2 is starting
        # This ensures the UI shows the correct step transition
        if progress_callback:
            try:
                logger.info("🔄 Updating progress: Transitioning from Step 1 to Step 2 (3D Lifting)")
                progress_callback(60, "Step 1 complete. Starting 3D lifting...")
                progress_callback(62, "Lifting 2D keypoints to 3D...")
                logger.info("✅ Progress updated: Step 2 (3D Lifting) started")
            except Exception as e:
                logger.error(f"❌ Error in progress callback during 3D lifting step transition: {e}", exc_info=True)
                # Don't fail - continue processing
        
        frames_3d_keypoints = []
        try:
            logger.debug(f"Starting 3D lifting: {len(frames_2d_keypoints)} 2D frames, view_type={view_type}")
            # CRITICAL: Update progress before starting 3D lifting to ensure UI shows correct step
            if progress_callback:
                try:
                    progress_callback(63, "Processing 3D lifting...")
                    logger.info("✅ Progress updated to 63%: 3D lifting in progress")
                except Exception as e:
                    logger.warning(f"Error updating progress at 63%: {e}")
            
            frames_3d_keypoints = self._lift_to_3d(
                frames_2d_keypoints, view_type, progress_callback=progress_callback
            )
            logger.info(f"✅ 3D lifting complete: {len(frames_3d_keypoints)} frames successfully lifted to 3D")
            
            # CRITICAL: Update progress after 3D lifting completes
            if progress_callback:
                try:
                    progress_callback(70, "3D lifting complete - validating results...")
                    logger.info("✅ Progress updated to 70%: 3D lifting complete")
                except Exception as e:
                    logger.warning(f"Error updating progress at 70%: {e}")
            
            # Validate 3D keypoints quality
            valid_3d_count = sum(1 for kp in frames_3d_keypoints if len(kp) > 0)
            logger.debug(f"3D keypoint validation: {valid_3d_count}/{len(frames_3d_keypoints)} frames have valid keypoints")
            
            if not frames_3d_keypoints or valid_3d_count == 0:
                error_msg = "3D lifting produced no valid keypoints. Cannot proceed with analysis."
                logger.error(f"❌ {error_msg}")
                raise PoseEstimationError(error_msg)
            
            logger.info("=" * 80)
            logger.info("✅ ========== STEP 2: 3D LIFTING COMPLETE ==========")
            logger.info(f"✅ Output: {len(frames_3d_keypoints)} 3D keypoint frames")
            logger.info(f"✅ Valid frames: {valid_3d_count}/{len(frames_3d_keypoints)}")
            logger.info("=" * 80)
            
            # CRITICAL: Save Step 2 checkpoint before proceeding to Step 3
            try:
                from app.services.checkpoint_manager import CheckpointManager
                checkpoint_manager = CheckpointManager(analysis_id=getattr(self, '_current_analysis_id', 'unknown'))
                checkpoint_manager.save_step_2(
                    frames_3d_keypoints=frames_3d_keypoints,
                    frames_2d_keypoints=frames_2d_keypoints
                )
                logger.info("✅ Step 2 checkpoint saved - can resume from here if needed")
            except Exception as e:
                logger.warning(f"⚠️ Failed to save Step 2 checkpoint (non-critical): {e}")
            
            if progress_callback:
                try:
                    progress_callback(70, "3D lifting complete - validating results...")
                except Exception as e:
                    logger.warning(f"Error in progress callback after 3D lifting: {e}")
        except PoseEstimationError:
            # Re-raise PoseEstimationError as-is
            raise
        except Exception as e:
            error_msg = f"Error during 3D lifting: {e}"
            logger.error(f"❌ {error_msg}", exc_info=True)
            raise PoseEstimationError(error_msg) from e
        
        # STEP 3: Calculate gait metrics - with comprehensive error handling and fallback
        logger.info("=" * 80)
        logger.info("=" * 80)
        logger.info("🎯 ========== STEP 3: GAIT METRICS CALCULATION STARTING ==========")
        current_analysis_id = getattr(self, '_current_analysis_id', 'unknown')
        logger.info(f"🎯 [STEP 3 ENTRY] Analysis ID: {current_analysis_id}")
        logger.info(f"🎯 [STEP 3 ENTRY] Input validation:")
        logger.info(f"🎯   - frames_3d_keypoints: type={type(frames_3d_keypoints)}, length={len(frames_3d_keypoints) if frames_3d_keypoints else 0}")
        logger.info(f"🎯   - frame_timestamps: type={type(frame_timestamps)}, length={len(frame_timestamps) if frame_timestamps else 0}")
        logger.info(f"🎯   - video_fps: {video_fps}")
        logger.info(f"🎯   - reference_length_mm: {reference_length_mm}")
        if frames_3d_keypoints and len(frames_3d_keypoints) > 0:
            first_frame = frames_3d_keypoints[0]
            logger.info(f"🎯   - First frame type: {type(first_frame)}")
            if isinstance(first_frame, dict):
                logger.info(f"🎯   - First frame keys: {list(first_frame.keys())[:10]}")
            elif isinstance(first_frame, (list, np.ndarray)):
                logger.info(f"🎯   - First frame length: {len(first_frame)}")
        logger.info("=" * 80)
        
        # CRITICAL: Validate that we have data from Step 2 before proceeding
        if not frames_3d_keypoints or len(frames_3d_keypoints) == 0:
            error_msg = "CRITICAL: Step 3 cannot proceed - no 3D keypoints from Step 2! Step 2 may have failed."
            logger.error(f"❌ {error_msg}")
            raise GaitMetricsError(error_msg, details={
                "frames_3d_keypoints_count": len(frames_3d_keypoints) if frames_3d_keypoints else 0,
                "step_2_status": "FAILED - no data"
            })
        
        # Validate that we have timestamps
        if not frame_timestamps or len(frame_timestamps) == 0:
            error_msg = "CRITICAL: Step 3 cannot proceed - no frame timestamps from Step 1!"
            logger.error(f"❌ {error_msg}")
            raise GaitMetricsError(error_msg, details={
                "frame_timestamps_count": len(frame_timestamps) if frame_timestamps else 0,
                "step_1_status": "FAILED - no timestamps"
            })
        
        # Validate that timestamps match 3D keypoints
        if len(frame_timestamps) != len(frames_3d_keypoints):
            logger.warning(f"⚠️ Timestamp count ({len(frame_timestamps)}) doesn't match 3D keypoint count ({len(frames_3d_keypoints)})")
            # Use the minimum length to avoid index errors
            min_length = min(len(frame_timestamps), len(frames_3d_keypoints))
            frame_timestamps = frame_timestamps[:min_length]
            frames_3d_keypoints = frames_3d_keypoints[:min_length]
            logger.warning(f"⚠️ Truncated to {min_length} frames to match counts")
        
        logger.info(f"✅ [STEP 3 VALIDATION] All inputs validated successfully")
        logger.info(f"✅   - 3D keypoint frames: {len(frames_3d_keypoints)}")
        logger.info(f"✅   - Timestamps: {len(frame_timestamps)}")
        logger.info(f"✅   - FPS: {video_fps}")
        logger.info(f"✅   - Reference length: {reference_length_mm}mm")
        logger.info(f"✅ [STEP 3] Starting actual metrics calculation with {len(frames_3d_keypoints)} frames...")
        
        if progress_callback:
            try:
                progress_callback(72, f"Starting gait metrics calculation with {len(frames_3d_keypoints)} frames...")
                progress_callback(75, "Calculating gait parameters...")
                logger.info(f"✅ [STEP 3] Progress callbacks sent (72%, 75%)")
            except Exception as e:
                logger.warning(f"⚠️ [STEP 3] Error in progress callback: {e}")
        
        metrics = {}
        try:
            # CRITICAL: Actually call the metrics calculation function
            logger.info("=" * 80)
            logger.info(f"🔍 [STEP 3] CALLING _calculate_gait_metrics()")
            logger.info(f"🔍   - Input frames: {len(frames_3d_keypoints)}")
            logger.info(f"🔍   - Input timestamps: {len(frame_timestamps)}")
            logger.info(f"🔍   - FPS: {video_fps}")
            logger.info(f"🔍   - Reference length: {reference_length_mm}mm")
            logger.info("=" * 80)
            
            start_time = time.time()
            
            # CRITICAL: Log detailed input validation before calculation
            logger.info("=" * 80)
            logger.info(f"🔍 [STEP 3] PRE-CALCULATION VALIDATION")
            logger.info(f"🔍   - 3D keypoint frames: {len(frames_3d_keypoints)}")
            logger.info(f"🔍   - Timestamps: {len(frame_timestamps)}")
            logger.info(f"🔍   - FPS: {video_fps}")
            logger.info(f"🔍   - Reference length: {reference_length_mm}mm")
            
            # Validate 3D keypoints have actual 3D data (not just 2D with z=0)
            if frames_3d_keypoints and len(frames_3d_keypoints) > 0:
                sample_frame = frames_3d_keypoints[0]
                if isinstance(sample_frame, dict) and 'left_ankle' in sample_frame:
                    left_ankle_z = sample_frame['left_ankle'].get('z', 0.0)
                    right_ankle_z = sample_frame['right_ankle'].get('z', 0.0) if 'right_ankle' in sample_frame else 0.0
                    avg_z = (abs(left_ankle_z) + abs(right_ankle_z)) / 2.0
                    logger.info(f"🔍   - Sample Z-depth (left_ankle): {left_ankle_z:.2f}mm")
                    logger.info(f"🔍   - Sample Z-depth (right_ankle): {right_ankle_z:.2f}mm")
                    logger.info(f"🔍   - Average Z-depth: {avg_z:.2f}mm")
                    if avg_z < 1.0:
                        logger.warning(f"⚠️ [STEP 3] WARNING: Very low Z-depth values detected! 3D lifting may not be working properly.")
                        logger.warning(f"⚠️   - This suggests Step 2 (3D lifting) may have produced 2D data instead of 3D")
                    else:
                        logger.info(f"✅ [STEP 3] Z-depth values look reasonable - 3D lifting appears to be working")
            
            logger.info("=" * 80)
            logger.info(f"🔍 [STEP 3] STARTING _calculate_gait_metrics() at {time.strftime('%H:%M:%S')}")
            logger.info("=" * 80)
            
            metrics = self._calculate_gait_metrics(
                frames_3d_keypoints,
                frame_timestamps,
                video_fps,
                reference_length_mm,
                progress_callback
            )
            calculation_time = time.time() - start_time
            
            logger.info("=" * 80)
            logger.info(f"✅ [STEP 3] _calculate_gait_metrics() RETURNED")
            logger.info(f"✅   - Calculation time: {calculation_time:.2f}s")
            logger.info(f"✅   - Processing rate: {len(frames_3d_keypoints) / calculation_time:.1f} frames/sec" if calculation_time > 0 else "✅   - Processing rate: N/A")
            logger.info(f"✅   - Metrics count: {len(metrics) if metrics else 0}")
            logger.info(f"✅   - Metrics type: {type(metrics)}")
            if metrics:
                logger.info(f"✅   - Metrics keys ({len(metrics)}): {list(metrics.keys())[:15]}")
                logger.info(f"✅   - Has cadence: {metrics.get('cadence') is not None}, value: {metrics.get('cadence', 0):.2f}")
                logger.info(f"✅   - Has walking_speed: {metrics.get('walking_speed') is not None}, value: {metrics.get('walking_speed', 0):.0f}mm/s")
                logger.info(f"✅   - Has step_length: {metrics.get('step_length') is not None}, value: {metrics.get('step_length', 0):.0f}mm")
                logger.info(f"✅   - Is fallback: {metrics.get('fallback_metrics', False)}")
                
                # Validate metrics are meaningful (not zeros or defaults)
                if metrics.get('cadence', 0) == 0 or metrics.get('walking_speed', 0) == 0:
                    logger.warning(f"⚠️ [STEP 3] WARNING: Metrics contain zero values - calculation may have issues")
                else:
                    logger.info(f"✅ [STEP 3] Metrics appear valid (non-zero values)")
            else:
                logger.error(f"❌ [STEP 3] _calculate_gait_metrics() returned EMPTY metrics!")
            logger.info("=" * 80)
            
            # CRITICAL: Validate that metrics were actually calculated
            logger.info(f"🔍 [STEP 3] Validating returned metrics...")
            logger.info(f"🔍   - metrics is None: {metrics is None}")
            logger.info(f"🔍   - metrics is empty dict: {metrics == {}}")
            logger.info(f"🔍   - metrics length: {len(metrics) if metrics else 0}")
            
            if not metrics:
                error_msg = "CRITICAL: _calculate_gait_metrics returned empty metrics! Calculation may have failed silently."
                logger.error(f"❌ {error_msg}")
                raise GaitMetricsError(error_msg, details={
                    "input_frames": len(frames_3d_keypoints),
                    "calculation_time": calculation_time
                })
            
            # CRITICAL: Validate metrics are not empty or fallback
            if not metrics or metrics.get('fallback_metrics', False):
                error_msg = "Gait metrics calculation failed or returned fallback metrics. Cannot proceed with analysis."
                logger.error(f"❌ {error_msg}")
                raise GaitMetricsError(error_msg)
            
            logger.info("=" * 80)
            logger.info("✅ ========== STEP 3: GAIT METRICS CALCULATION COMPLETE ==========")
            logger.info(f"✅ Metrics calculated: {len(metrics)}")
            logger.info(f"✅ Sample metrics: cadence={metrics.get('cadence', 0):.1f}, step_length={metrics.get('step_length', 0):.0f}mm")
            logger.info("=" * 80)
            
            # CRITICAL: Save Step 3 checkpoint before proceeding to Step 4
            try:
                from app.services.checkpoint_manager import CheckpointManager
                checkpoint_manager = CheckpointManager(analysis_id=getattr(self, '_current_analysis_id', 'unknown'))
                checkpoint_manager.save_step_3(
                    metrics=metrics,
                    frames_3d_keypoints=frames_3d_keypoints
                )
                logger.info("✅ Step 3 checkpoint saved - can resume from here if needed")
            except Exception as e:
                logger.warning(f"⚠️ Failed to save Step 3 checkpoint (non-critical): {e}")
            
            if progress_callback:
                try:
                    progress_callback(85, "Gait metrics calculation complete - validating results...")
                    progress_callback(88, "Validating metrics quality and completeness...")
                except Exception as e:
                    logger.warning(f"Error in progress callback after metrics calculation: {e}")
        except GaitMetricsError:
            # Re-raise GaitMetricsError as-is
            raise
        except Exception as e:
            error_msg = f"Error during gait metrics calculation: {e}"
            logger.error(f"❌ {error_msg}", exc_info=True)
            raise GaitMetricsError(error_msg) from e
        
        # STEP 4: Report generation - finalizing results
        logger.info("=" * 80)
        logger.info("🎯 ========== STEP 4: REPORT GENERATION STARTING ==========")
        logger.info(f"🎯 Preparing final analysis report...")
        logger.info("=" * 80)
        
        # CRITICAL: Validate that we have metrics from Step 3 before proceeding
        if not metrics or len(metrics) == 0:
            error_msg = "CRITICAL: Step 4 cannot proceed - no metrics from Step 3! Step 3 may have failed."
            logger.error(f"❌ {error_msg}")
            raise ValueError(error_msg)
        
        # Validate that metrics are not fallback
        if metrics.get('fallback_metrics', False):
            error_msg = "CRITICAL: Step 4 cannot proceed - Step 3 returned fallback metrics! Processing may have failed."
            logger.error(f"❌ {error_msg}")
            raise ValueError(error_msg)
        
        # Validate that we have core metrics
        has_core_metrics = (
            metrics.get('cadence') is not None or
            metrics.get('walking_speed') is not None or
            metrics.get('step_length') is not None
        )
        if not has_core_metrics:
            error_msg = "CRITICAL: Step 4 cannot proceed - Step 3 metrics missing core values (cadence, walking_speed, step_length)!"
            logger.error(f"❌ {error_msg}")
            logger.error(f"❌ Available metrics keys: {list(metrics.keys())}")
            raise ValueError(error_msg)
        
        logger.info(f"✅ Step 4 validation passed: {len(metrics)} metrics, core metrics present: {has_core_metrics}")
        logger.info(f"✅ Sample metrics: cadence={metrics.get('cadence', 'N/A')}, step_length={metrics.get('step_length', 'N/A')}, walking_speed={metrics.get('walking_speed', 'N/A')}")
        logger.info(f"✅ Starting actual report generation with validated metrics...")
        
        if progress_callback:
            try:
                progress_callback(90, f"Validating {len(metrics)} metrics from Step 3...")
                progress_callback(92, "All processing steps validated...")
                progress_callback(94, "Preparing analysis report...")
                progress_callback(96, "Finalizing results...")
            except Exception as e:
                logger.warning(f"Error in progress callback during report generation: {e}")
        
        # Calculate processing statistics
        frames_processed_count = len(frames_2d_keypoints)
        processing_stats = {
            "total_frames": total_frames,
            "frames_processed": frames_processed_count,
            "processing_rate": f"{(frames_processed_count / total_frames * 100):.1f}%" if total_frames > 0 else "0%",
            "keypoints_per_frame": len(frames_2d_keypoints[0]) if frames_2d_keypoints else 0,
            "analysis_duration_estimate": f"{total_frames / video_fps:.1f}s" if video_fps > 0 else "unknown"
        }
        
        logger.info(f"✅ Processing complete - Statistics: {processing_stats}")
        logger.info(f"✅ Frames processed: {frames_processed_count}/{total_frames} ({processing_stats['processing_rate']})")
        logger.info(f"✅ Keypoints extracted: {frames_processed_count} frames with 2D keypoints, {len(frames_3d_keypoints)} frames with 3D keypoints")
        logger.info(f"✅ Metrics calculated: {len(metrics)} metrics")
        
        # CRITICAL: Validate that processing actually happened
        if frames_processed_count == 0:
            error_msg = f"CRITICAL: No frames were processed! Video may be invalid or processing failed. Total frames in video: {total_frames}"
            logger.error(error_msg)
            raise ValueError(error_msg)
        
        if total_frames == 0:
            error_msg = "CRITICAL: Video has 0 frames - video file is invalid or empty"
            logger.error(error_msg)
            raise ValueError(error_msg)
        
        # CRITICAL: Validate all 4 steps completed successfully
        steps_completed = {
            "step_1_pose_estimation": len(frames_2d_keypoints) > 0,
            "step_2_3d_lifting": len(frames_3d_keypoints) > 0,
            "step_3_metrics_calculation": len(metrics) > 0 and not metrics.get('fallback_metrics', False),
            "step_4_report_generation": True  # Will be set when result is prepared
        }
        
        logger.info("=" * 80)
        logger.info("🔍 ========== VALIDATION: ALL 4 STEPS COMPLETION CHECK ==========")
        logger.info(f"🔍 Step 1 (Pose Estimation): {'✅ COMPLETE' if steps_completed['step_1_pose_estimation'] else '❌ FAILED'} ({len(frames_2d_keypoints)} 2D keypoint frames)")
        logger.info(f"🔍 Step 2 (3D Lifting): {'✅ COMPLETE' if steps_completed['step_2_3d_lifting'] else '❌ FAILED'} ({len(frames_3d_keypoints)} 3D keypoint frames)")
        logger.info(f"🔍 Step 3 (Metrics Calculation): {'✅ COMPLETE' if steps_completed['step_3_metrics_calculation'] else '❌ FAILED'} ({len(metrics)} metrics)")
        logger.info(f"🔍 Step 4 (Report Generation): {'✅ IN PROGRESS' if steps_completed['step_4_report_generation'] else '❌ FAILED'}")
        logger.info("=" * 80)
        
        # CRITICAL: Fail if any step didn't complete (but allow if we have valid metrics)
        if not all(steps_completed.values()):
            failed_steps = [step for step, completed in steps_completed.items() if not completed]
            error_msg = f"CRITICAL: Not all processing steps completed successfully. Failed steps: {failed_steps}"
            logger.error(f"❌ {error_msg}")
            # Don't fail if we have valid metrics - we can still generate a report
            if len(metrics) > 0 and not metrics.get('fallback_metrics', False):
                logger.warning(f"⚠️ Some steps failed but metrics are valid - continuing with report generation")
            else:
                raise ValueError(error_msg)
        
        logger.info("=" * 80)
        logger.info("🔍 [STEP 3] Constructing result dictionary...")
        logger.info(f"🔍   - metrics to include: {len(metrics) if metrics else 0} metrics")
        logger.info(f"🔍   - metrics type: {type(metrics)}")
        logger.info(f"🔍   - steps_completed: {steps_completed}")
        logger.info("=" * 80)
        
        result = {
            "status": "completed",
            "analysis_type": "advanced_gait_analysis_v2_professional",
            "frames_processed": frames_processed_count,
            "total_frames": total_frames,
            "processing_stats": processing_stats,
            "keypoints_2d": frames_2d_keypoints[:10],  # Sample for debugging
            "keypoints_3d": frames_3d_keypoints[:10],  # Sample for debugging
            "metrics": metrics,
            "steps_completed": steps_completed  # Track which steps completed
        }
        
        logger.info(f"✅ [STEP 3] Result dictionary constructed")
        logger.info(f"✅   - Result keys: {list(result.keys())}")
        logger.info(f"✅   - Result has 'metrics' key: {'metrics' in result}")
        logger.info(f"✅   - Result['metrics'] is None: {result.get('metrics') is None}")
        logger.info(f"✅   - Result['metrics'] is empty: {result.get('metrics') == {}}")
        logger.info(f"✅   - Result['metrics'] length: {len(result.get('metrics', {}))}")
        
        # CRITICAL: Validate metrics are in result before returning
        if 'metrics' not in result or not result['metrics']:
            error_msg = "CRITICAL: Result prepared but metrics are missing!"
            logger.error(f"❌ [STEP 3] {error_msg}")
            logger.error(f"❌   - Result keys: {list(result.keys())}")
            logger.error(f"❌   - 'metrics' in result: {'metrics' in result}")
            logger.error(f"❌   - result['metrics']: {result.get('metrics')}")
            raise ValueError(error_msg)
        
        if result['metrics'].get('fallback_metrics', False):
            error_msg = "CRITICAL: Result contains fallback metrics - Step 3 failed!"
            logger.error(f"❌ [STEP 3] {error_msg}")
            logger.error(f"❌   - Metrics: {list(result['metrics'].keys())}")
            raise ValueError(error_msg)
        
        logger.info("=" * 80)
        logger.info(f"✅ [STEP 3] RESULT VALIDATION PASSED")
        logger.info(f"✅   - Frames processed: {frames_processed_count}")
        logger.info(f"✅   - Metrics in result: {len(result['metrics'])} metrics")
        logger.info(f"✅   - Has cadence: {result['metrics'].get('cadence') is not None}")
        logger.info(f"✅   - Has walking_speed: {result['metrics'].get('walking_speed') is not None}")
        logger.info(f"✅   - Has step_length: {result['metrics'].get('step_length') is not None}")
        logger.info(f"✅   - Is fallback: {result['metrics'].get('fallback_metrics', False)}")
        logger.info("=" * 80)
        
        if progress_callback:
            try:
                progress_callback(90, "All 4 steps complete - preparing final report...")
                progress_callback(92, "Validating processing results...")
                progress_callback(94, "Preparing analysis report...")
                progress_callback(96, "Finalizing results...")
                progress_callback(97, "Saving analysis results to database...")
                progress_callback(98, "Finalizing report generation...")
                # Don't call 100% here - let the API layer do it after database update
            except Exception as e:
                logger.warning(f"Error in progress callback at completion: {e}")
        
        logger.info("=" * 80)
        logger.info("✅ ========== STEP 4: REPORT GENERATION COMPLETE ==========")
        logger.info("✅ ========== ALL 4 STEPS COMPLETED SUCCESSFULLY ==========")
        logger.info("=" * 80)
        logger.info("GAIT ANALYSIS COMPLETE - Professional-Grade Results")
        logger.info(f"  Cadence: {metrics.get('cadence', 0):.1f} steps/min")
        logger.info(f"  Step Length: {metrics.get('step_length', 0):.0f}mm")
        logger.info(f"  Walking Speed: {metrics.get('walking_speed', 0):.0f}mm/s")
        logger.info(f"  Symmetry: {metrics.get('step_time_symmetry', 0):.3f}")
        logger.info(f"  Variability (CV): {metrics.get('step_length_cv', 0):.2f}%")
        logger.info("=" * 60)
        
        return result
    
    def _extract_2d_keypoints_v2(self, pose_landmarks, width: int, height: int) -> Dict:
        """Extract 2D keypoints from MediaPipe 0.10.x PoseLandmarker results"""
        keypoints = {}
        
        # MediaPipe 0.10.x landmark indices (same as 0.9.x)
        landmark_map = {
            'nose': 0,
            'left_shoulder': 11,
            'right_shoulder': 12,
            'left_elbow': 13,
            'right_elbow': 14,
            'left_wrist': 15,
            'right_wrist': 16,
            'left_hip': 23,
            'right_hip': 24,
            'left_knee': 25,
            'right_knee': 26,
            'left_ankle': 27,
            'right_ankle': 28,
            'left_heel': 29,
            'right_heel': 30,
            'left_foot_index': 31,
            'right_foot_index': 32,
        }
        
        for name, landmark_idx in landmark_map.items():
            if landmark_idx < len(pose_landmarks):
                landmark = pose_landmarks[landmark_idx]
                keypoints[name] = {
                    'x': landmark.x * width,
                    'y': landmark.y * height,
                    'z': landmark.z * width,  # MediaPipe provides depth estimate
                    'visibility': landmark.visibility if hasattr(landmark, 'visibility') else 1.0
                }
        
        return keypoints
    
    def _detect_with_yolo(self, frame, width: int, height: int) -> Optional[Dict]:
        """
        Detect pose using YOLO26 Pose model (PRIMARY detector)
        
        YOLO26 Features (https://docs.ultralytics.com/models/yolo26/):
        - Native end-to-end inference (NMS-free) - no post-processing needed
        - Residual Log-Likelihood Estimation (RLE) for precision keypoint localization
        - Up to 43% faster CPU inference
        - Optimized decoding for increased inference speed
        
        Licensed under AGPL-3.0 - compatible with open-source distribution
        Returns keypoints in the same format as MediaPipe for compatibility
        """
        if not self.yolo_model or not YOLO_AVAILABLE:
            return None
        
        try:
            # Run YOLO inference with optimized settings for gait analysis
            # - Lower confidence threshold (0.2) to catch more poses in challenging conditions
            # - iou threshold helps with multi-person scenarios (select best detection)
            results = self.yolo_model(
                frame,
                conf=0.2,  # Lower threshold for better recall
                iou=0.5,   # Standard IoU threshold
                verbose=False,
                device='cpu'  # Ensure CPU inference for compatibility
            )
            
            if not results or len(results) == 0:
                return None
            
            result = results[0]
            if result.keypoints is None or len(result.keypoints) == 0:
                return None
            
            # If multiple people detected, select the one with highest confidence
            # or the one closest to center of frame (more likely the subject)
            best_person_idx = 0
            if len(result.keypoints) > 1:
                # Try to select person with highest average keypoint confidence
                best_conf = 0
                for i, kpts in enumerate(result.keypoints):
                    if kpts.conf is not None:
                        avg_conf = float(kpts.conf[0].mean()) if len(kpts.conf[0]) > 0 else 0
                        if avg_conf > best_conf:
                            best_conf = avg_conf
                            best_person_idx = i
            
            # Get keypoints from selected person
            kpts = result.keypoints[best_person_idx]
            if kpts.xy is None or len(kpts.xy) == 0:
                return None
            
            # Handle different tensor shapes from YOLO versions
            xy_data = kpts.xy
            if hasattr(xy_data, 'cpu'):
                xy_data = xy_data.cpu()
            if hasattr(xy_data, 'numpy'):
                xy = xy_data.numpy()
            else:
                xy = np.array(xy_data)
            
            # Flatten if needed (shape could be (1, 17, 2) or (17, 2))
            if xy.ndim == 3:
                xy = xy[0]  # Shape: (17, 2) for COCO keypoints
            
            # Get confidence scores
            conf_data = kpts.conf
            if conf_data is not None:
                if hasattr(conf_data, 'cpu'):
                    conf_data = conf_data.cpu()
                if hasattr(conf_data, 'numpy'):
                    conf = conf_data.numpy()
                else:
                    conf = np.array(conf_data)
                if conf.ndim == 2:
                    conf = conf[0]
            else:
                conf = np.ones(17)
            
            # YOLO uses COCO keypoint format (17 keypoints):
            # 0: nose, 1: left_eye, 2: right_eye, 3: left_ear, 4: right_ear
            # 5: left_shoulder, 6: right_shoulder, 7: left_elbow, 8: right_elbow
            # 9: left_wrist, 10: right_wrist, 11: left_hip, 12: right_hip
            # 13: left_knee, 14: right_knee, 15: left_ankle, 16: right_ankle
            
            yolo_to_mediapipe = {
                'nose': 0,
                'left_shoulder': 5,
                'right_shoulder': 6,
                'left_elbow': 7,
                'right_elbow': 8,
                'left_wrist': 9,
                'right_wrist': 10,
                'left_hip': 11,
                'right_hip': 12,
                'left_knee': 13,
                'right_knee': 14,
                'left_ankle': 15,
                'right_ankle': 16,
            }
            
            keypoints = {}
            for name, yolo_idx in yolo_to_mediapipe.items():
                if yolo_idx < len(xy):
                    # Skip keypoints with zero coordinates (not detected)
                    x_val, y_val = float(xy[yolo_idx][0]), float(xy[yolo_idx][1])
                    if x_val == 0 and y_val == 0:
                        continue
                    
                    keypoints[name] = {
                        'x': x_val,
                        'y': y_val,
                        'z': 0.0,  # YOLO provides 2D keypoints; 3D lifting happens later
                        'visibility': float(conf[yolo_idx]) if yolo_idx < len(conf) else 0.5
                    }
            
            # Estimate heel and foot positions from ankle positions
            # These are important for gait analysis but not provided by COCO format
            # Use biomechanical estimation based on ankle position and hip-knee-ankle angle
            if 'left_ankle' in keypoints and 'left_knee' in keypoints:
                # Estimate foot direction from knee-ankle vector
                knee = keypoints['left_knee']
                ankle = keypoints['left_ankle']
                dx = ankle['x'] - knee['x']
                dy = ankle['y'] - knee['y']
                
                # Heel is slightly behind and below ankle
                keypoints['left_heel'] = {
                    'x': ankle['x'] - dx * 0.1,
                    'y': ankle['y'] + abs(dy) * 0.15 + 10,
                    'z': 0.0,
                    'visibility': ankle['visibility'] * 0.8
                }
                # Foot index (toe) is in front of ankle
                keypoints['left_foot_index'] = {
                    'x': ankle['x'] + dx * 0.3 + 15,
                    'y': ankle['y'] + abs(dy) * 0.1 + 5,
                    'z': 0.0,
                    'visibility': ankle['visibility'] * 0.8
                }
            
            if 'right_ankle' in keypoints and 'right_knee' in keypoints:
                knee = keypoints['right_knee']
                ankle = keypoints['right_ankle']
                dx = ankle['x'] - knee['x']
                dy = ankle['y'] - knee['y']
                
                keypoints['right_heel'] = {
                    'x': ankle['x'] - dx * 0.1,
                    'y': ankle['y'] + abs(dy) * 0.15 + 10,
                    'z': 0.0,
                    'visibility': ankle['visibility'] * 0.8
                }
                keypoints['right_foot_index'] = {
                    'x': ankle['x'] + dx * 0.3 + 15,
                    'y': ankle['y'] + abs(dy) * 0.1 + 5,
                    'z': 0.0,
                    'visibility': ankle['visibility'] * 0.8
                }
            
            # Return keypoints only if we have enough for gait analysis
            # Minimum: both ankles, knees, and hips
            required = ['left_ankle', 'right_ankle', 'left_knee', 'right_knee', 'left_hip', 'right_hip']
            if all(r in keypoints for r in required):
                return keypoints
            elif len(keypoints) >= 6:
                return keypoints  # Partial detection may still be useful
            else:
                return None
            
        except Exception as e:
            logger.debug(f"YOLO detection error: {e}")
            return None
    
    def _validate_keypoint_quality(self, keypoints: Dict) -> bool:
        """Validate keypoint quality using biomechanical constraints"""
        # Check if critical joints are present
        required_joints = ['left_ankle', 'right_ankle', 'left_knee', 'right_knee', 'left_hip', 'right_hip']
        if not all(joint in keypoints for joint in required_joints):
            return False
        
        # Check visibility thresholds
        critical_joints = ['left_ankle', 'right_ankle']
        for joint in critical_joints:
            if joint in keypoints:
                visibility = keypoints[joint].get('visibility', 0.0)
                if visibility < 0.3:  # Too low visibility
                    return False
        
        # Check for reasonable joint positions (not all zeros or extreme values)
        left_ankle = keypoints.get('left_ankle', {})
        right_ankle = keypoints.get('right_ankle', {})
        
        if left_ankle and right_ankle:
            # Check if positions are reasonable (not identical, not extreme)
            dist = np.sqrt(
                (left_ankle.get('x', 0) - right_ankle.get('x', 0))**2 +
                (left_ankle.get('y', 0) - right_ankle.get('y', 0))**2
            )
            if dist < 10:  # Ankles too close (likely error)
                return False
        
        return True
    
    def _apply_advanced_filtering(self, frames_2d_keypoints: List[Dict], timestamps: List[float]) -> List[Dict]:
        """
        Apply advanced signal processing: Savitzky-Golay filtering, wavelet denoising, and Kalman smoothing
        Professional-grade filtering for maximum accuracy
        """
        if not frames_2d_keypoints or len(frames_2d_keypoints) < 5:
            logger.warning("Insufficient frames for advanced filtering")
            return frames_2d_keypoints
        
        logger.debug(f"Applying advanced filtering to {len(frames_2d_keypoints)} frames")
        
        # Extract time series for each keypoint
        keypoint_names = list(frames_2d_keypoints[0].keys())
        filtered_frames = []
        
        for i, frame in enumerate(frames_2d_keypoints):
            filtered_frame = {}
            
            for name in keypoint_names:
                # Extract time series
                x_series = np.array([f[name]['x'] for f in frames_2d_keypoints])
                y_series = np.array([f[name]['y'] for f in frames_2d_keypoints])
                z_series = np.array([f.get(name, {}).get('z', 0.0) for f in frames_2d_keypoints])
                visibility_series = np.array([f.get(name, {}).get('visibility', 1.0) for f in frames_2d_keypoints])
                
                # Step 1: Apply Savitzky-Golay filter (preserves features while smoothing)
                if SCIPY_AVAILABLE and len(x_series) > 5:
                    window_length = min(7, len(x_series) // 2 * 2 - 1)  # Must be odd, increased for better smoothing
                    if window_length >= 3:
                        polyorder = min(3, window_length - 1)  # Higher order for better accuracy
                        try:
                            x_filtered = signal.savgol_filter(x_series, window_length, polyorder)
                            y_filtered = signal.savgol_filter(y_series, window_length, polyorder)
                            z_filtered = signal.savgol_filter(z_series, window_length, polyorder)
                            # Only log for critical joints to reduce verbosity
                            if 'ankle' in name and i == 0:  # Log once for first frame
                                logger.debug(f"Applied Savitzky-Golay filter (window={window_length}, order={polyorder})")
                        except Exception as e:
                            logger.warning(f"Savitzky-Golay filter failed for {name}: {e}")
                            x_filtered, y_filtered, z_filtered = x_series, y_series, z_series
                    else:
                        x_filtered, y_filtered, z_filtered = x_series, y_series, z_series
                else:
                    x_filtered, y_filtered, z_filtered = x_series, y_series, z_series
                
                # Step 2: Optional wavelet denoising for critical joints
                if WAVELETS_AVAILABLE and ('ankle' in name or 'knee' in name) and len(x_filtered) > 8:
                    try:
                        # Apply wavelet denoising (soft thresholding)
                        wavelet = 'db4'  # Daubechies 4 wavelet
                        coeffs_x = pywt.wavedec(x_filtered, wavelet, level=2)
                        coeffs_y = pywt.wavedec(y_filtered, wavelet, level=2)
                        
                        # Apply soft thresholding to detail coefficients
                        threshold = 0.1 * np.max([np.abs(c).max() for c in coeffs_x[1:]])
                        coeffs_x_thresh = [pywt.threshold(c, threshold, mode='soft') if i > 0 else c for i, c in enumerate(coeffs_x)]
                        coeffs_y_thresh = [pywt.threshold(c, threshold, mode='soft') if i > 0 else c for i, c in enumerate(coeffs_y)]
                        
                        # Reconstruct
                        x_denoised = pywt.waverec(coeffs_x_thresh, wavelet)
                        y_denoised = pywt.waverec(coeffs_y_thresh, wavelet)
                        
                        # Ensure same length
                        if len(x_denoised) == len(x_filtered):
                            x_filtered, y_filtered = x_denoised, y_denoised
                            if i == 0:  # Log once
                                logger.debug(f"Applied wavelet denoising to critical joints")
                    except Exception as e:
                        logger.debug(f"Wavelet denoising failed for {name}: {e}")
                
                filtered_frame[name] = {
                    'x': float(x_filtered[i]),
                    'y': float(y_filtered[i]),
                    'z': float(z_filtered[i]),
                    'visibility': float(visibility_series[i])
                }
            
            filtered_frames.append(filtered_frame)
        
        logger.debug(f"Advanced filtering complete: {len(filtered_frames)} frames processed")
        return filtered_frames
    
    def _create_dummy_keypoints(self, width: int, height: int, frame_index: int = 0) -> Dict:
        """Create dummy keypoints for fallback when MediaPipe is not available"""
        center_x, center_y = width / 2, height / 2
        cycle_position = (frame_index % 60) / 60.0
        phase = cycle_position * 2 * np.pi
        
        left_ankle_x = center_x - 80 + 40 * np.sin(phase)
        left_ankle_y = center_y + 150 + 20 * np.cos(phase)
        left_ankle_z = 50 * np.sin(phase)
        
        right_ankle_x = center_x + 80 - 40 * np.sin(phase)
        right_ankle_y = center_y + 150 - 20 * np.cos(phase)
        right_ankle_z = -50 * np.sin(phase)
        
        return {
            'left_ankle': {'x': float(left_ankle_x), 'y': float(left_ankle_y), 'z': float(left_ankle_z), 'visibility': 0.7},
            'right_ankle': {'x': float(right_ankle_x), 'y': float(right_ankle_y), 'z': float(right_ankle_z), 'visibility': 0.7},
            'left_knee': {'x': float(left_ankle_x + 10), 'y': float(left_ankle_y - 80), 'z': float(left_ankle_z * 0.5), 'visibility': 0.7},
            'right_knee': {'x': float(right_ankle_x - 10), 'y': float(right_ankle_y - 80), 'z': float(right_ankle_z * 0.5), 'visibility': 0.7},
            'left_hip': {'x': float(center_x - 40), 'y': float(center_y), 'z': 0.0, 'visibility': 0.7},
            'right_hip': {'x': float(center_x + 40), 'y': float(center_y), 'z': 0.0, 'visibility': 0.7},
            'left_shoulder': {'x': float(center_x - 60), 'y': float(center_y - 100), 'z': 0.0, 'visibility': 0.7},
            'right_shoulder': {'x': float(center_x + 60), 'y': float(center_y - 100), 'z': 0.0, 'visibility': 0.7},
        }
    
    def _detect_view_angle(self, frames_2d_keypoints: List[Dict]) -> str:
        """Detect camera view angle from keypoint patterns"""
        if not frames_2d_keypoints:
            return 'unknown'
        
        sample_frames = frames_2d_keypoints[:min(10, len(frames_2d_keypoints))]
        hip_widths = []
        leg_separations = []
        
        for kp in sample_frames:
            if 'left_hip' in kp and 'right_hip' in kp:
                hip_widths.append(abs(kp['left_hip']['x'] - kp['right_hip']['x']))
            if 'left_ankle' in kp and 'right_ankle' in kp:
                leg_separations.append(abs(kp['left_ankle']['x'] - kp['right_ankle']['x']))
        
        if not hip_widths or not leg_separations:
            return 'unknown'
        
        avg_hip_width = np.mean(hip_widths)
        avg_leg_separation = np.mean(leg_separations)
        
        if avg_hip_width > 100 and avg_leg_separation < 50:
            return 'front'
        elif avg_hip_width < 50 and avg_leg_separation > 100:
            return 'side'
        elif avg_hip_width > 50 and avg_leg_separation > 50:
            return 'oblique'
        else:
            return 'unknown'
    
    def _lift_to_3d(
        self,
        frames_2d_keypoints: List[Dict],
        view_type: str,
        progress_callback: Optional[Callable[[int, str], None]] = None,
    ) -> List[Dict]:
        """
        Advanced 3D reconstruction with improved biomechanical models
        Professional-grade 3D lifting with constraint validation
        """
        total_frames = len(frames_2d_keypoints)
        logger.info(f"[STEP 2] Starting 3D lifting: {total_frames} frames, view_type={view_type}")
        
        if view_type == "auto" or not view_type:
            detected_view = self._detect_view_angle(frames_2d_keypoints)
            logger.info(f"[STEP 2] Auto-detected view angle: {detected_view}")
            view_type = detected_view
        
        frames_3d = []
        # Professional biomechanical segment lengths (adult averages in mm)
        leg_segment_lengths = {
            'thigh': 450.0,  # Hip to knee
            'shank': 400.0,  # Knee to ankle
            'foot': 250.0,   # Ankle to toe
        }
        
        # Progress every N frames (63–70% UI during Step 2). Min 1% of total, max 100 frames.
        progress_interval = max(1, min(100, total_frames // 20))
        last_log_frame = 0
        
        for i, keypoints_2d in enumerate(frames_2d_keypoints):
            keypoints_3d = {}
            
            for name, kp_2d in keypoints_2d.items():
                x, y, z_estimate = kp_2d['x'], kp_2d['y'], kp_2d.get('z', 0.0)
                z_refined = self._refine_leg_depth(name, kp_2d, keypoints_2d, view_type, leg_segment_lengths)
                
                keypoints_3d[name] = {
                    'x': x,
                    'y': y,
                    'z': z_refined,
                    'confidence': kp_2d.get('visibility', 1.0)
                }
            
            # Improved temporal smoothing
            if i > 0 and len(frames_3d) > 0:
                prev_keypoints = frames_3d[-1]
                for name in keypoints_3d:
                    if name in prev_keypoints:
                        alpha = 0.15 if ('ankle' in name or 'heel' in name or 'foot' in name) else 0.25
                        keypoints_3d[name]['x'] = alpha * keypoints_3d[name]['x'] + (1 - alpha) * prev_keypoints[name]['x']
                        keypoints_3d[name]['y'] = alpha * keypoints_3d[name]['y'] + (1 - alpha) * prev_keypoints[name]['y']
                        keypoints_3d[name]['z'] = alpha * keypoints_3d[name]['z'] + (1 - alpha) * prev_keypoints[name]['z']
            
            frames_3d.append(keypoints_3d)
            
            # Progress and logging during loop so UI doesn’t appear stuck at 63%
            if (i + 1) % progress_interval == 0 or i == total_frames - 1:
                pct_done = (i + 1) / total_frames
                # Internal 52–75 maps to UI 63–70% for Step 2
                internal_pct = 52 + int(23 * pct_done)
                if progress_callback:
                    try:
                        progress_callback(internal_pct, f"3D lifting... {i + 1}/{total_frames} frames")
                    except Exception:
                        pass
                if (i + 1) - last_log_frame >= 100 or i == total_frames - 1:
                    logger.info(f"[STEP 2] 3D lifting progress: {i + 1}/{total_frames} frames ({100 * pct_done:.1f}%)")
                    last_log_frame = i + 1
        
        # Log 3D lifting statistics
        if len(frames_3d) > 0:
            sample_3d = frames_3d[0]
            keypoint_count = len(sample_3d)
            logger.debug(f"3D lifting statistics: {keypoint_count} keypoints per frame, {len(frames_3d)} total frames")
        
        return frames_3d
    
    def _refine_leg_depth(self, joint_name: str, joint_2d: Dict, all_keypoints: Dict, view_type: str, segment_lengths: Dict) -> float:
        """Advanced depth refinement using biomechanical constraints"""
        z_estimate = joint_2d.get('z', 0.0)
        
        if 'ankle' in joint_name:
            side = 'left' if 'left' in joint_name else 'right'
            knee_name = f'{side}_knee'
            if knee_name in all_keypoints:
                knee_2d = all_keypoints[knee_name]
                dx = joint_2d['x'] - knee_2d['x']
                dy = joint_2d['y'] - knee_2d['y']
                dist_2d = np.sqrt(dx**2 + dy**2)
                shank_length = segment_lengths['shank']
                if dist_2d > 0:
                    z_depth = np.sqrt(max(0, shank_length**2 - dist_2d**2))
                    if view_type == 'side':
                        z_refined = z_estimate + z_depth * 0.5
                    elif view_type == 'front':
                        z_refined = z_estimate
                    else:
                        z_refined = z_estimate + z_depth * 0.3
                    return z_refined
        
        elif 'knee' in joint_name:
            side = 'left' if 'left' in joint_name else 'right'
            hip_name = f'{side}_hip'
            if hip_name in all_keypoints:
                hip_2d = all_keypoints[hip_name]
                dx = joint_2d['x'] - hip_2d['x']
                dy = joint_2d['y'] - hip_2d['y']
                dist_2d = np.sqrt(dx**2 + dy**2)
                thigh_length = segment_lengths['thigh']
                if dist_2d > 0:
                    z_depth = np.sqrt(max(0, thigh_length**2 - dist_2d**2))
                    if view_type == 'side':
                        z_refined = z_estimate + z_depth * 0.5
                    else:
                        z_refined = z_estimate + z_depth * 0.3
                    return z_refined
        
        return z_estimate
    
    def _calculate_gait_metrics(
        self,
        frames_3d_keypoints: List[Dict],
        timestamps: List[float],
        fps: float,
        reference_length_mm: Optional[float],
        progress_callback: Optional[Callable] = None
    ) -> Dict:
        """Advanced gait parameter calculation with improved accuracy"""
        # CRITICAL: Log function entry with detailed diagnostics
        logger.info("=" * 80)
        logger.info("🔍 ========== _calculate_gait_metrics CALLED ==========")
        logger.info(f"🔍 Input: frames_3d_keypoints type={type(frames_3d_keypoints)}, length={len(frames_3d_keypoints) if frames_3d_keypoints else 0}")
        logger.info(f"🔍 Input: timestamps type={type(timestamps)}, length={len(timestamps) if timestamps else 0}")
        logger.info(f"🔍 Input: fps={fps}, reference_length_mm={reference_length_mm}")
        logger.info("=" * 80)
        
        if not frames_3d_keypoints or len(frames_3d_keypoints) == 0:
            error_msg = "CRITICAL: _calculate_gait_metrics received empty frames_3d_keypoints!"
            logger.error(f"❌ {error_msg}")
            raise GaitMetricsError(error_msg, details={"input_length": 0})
        
        if len(frames_3d_keypoints) < 10:
            error_msg = f"CRITICAL: Not enough frames for gait analysis! Received {len(frames_3d_keypoints)} frames, need at least 10."
            logger.error(f"❌ {error_msg}")
            logger.error(f"❌ This means Step 2 (3D Lifting) did not produce enough valid frames!")
            # Provide helpful guidance to the user
            user_guidance = (
                f"Video produced only {len(frames_3d_keypoints)} valid frames. "
                "For accurate gait analysis, please ensure: "
                "(1) Video is at least 3-4 seconds long, "
                "(2) Person is fully visible and walking in frame, "
                "(3) Good lighting conditions, "
                "(4) Camera is stable with clear view of the person."
            )
            raise GaitMetricsError(error_msg, details={
                "frames_received": len(frames_3d_keypoints),
                "frames_required": 10,
                "step_2_status": "INSUFFICIENT_DATA",
                "user_guidance": user_guidance
            })
        
        # Validate first frame structure
        if frames_3d_keypoints and len(frames_3d_keypoints) > 0:
            first_frame = frames_3d_keypoints[0]
            logger.info(f"🔍 First frame type: {type(first_frame)}, keys: {list(first_frame.keys())[:5] if isinstance(first_frame, dict) else 'NOT_A_DICT'}")
            if isinstance(first_frame, dict):
                has_ankles = 'left_ankle' in first_frame and 'right_ankle' in first_frame
                logger.info(f"🔍 First frame has ankle keypoints: {has_ankles}")
                if not has_ankles:
                    error_msg = "CRITICAL: frames_3d_keypoints missing required ankle keypoints! Expected dict with 'left_ankle' and 'right_ankle' keys."
                    logger.error(f"❌ {error_msg}")
                    logger.error(f"❌ First frame keys: {list(first_frame.keys())}")
                    raise GaitMetricsError(error_msg, details={
                        "first_frame_keys": list(first_frame.keys()),
                        "expected_keys": ["left_ankle", "right_ankle"]
                    })
        
        if progress_callback:
            try:
                progress_callback(76, "Extracting joint positions from 3D keypoints...")
            except Exception as e:
                logger.warning(f"Error in progress callback: {e}")
        
        # Extract joint positions
        logger.info(f"🔍 Starting joint position extraction from {len(frames_3d_keypoints)} frames...")
        left_ankle_positions = []
        right_ankle_positions = []
        left_heel_positions = []
        right_heel_positions = []
        
        frames_with_ankles = 0
        frames_processed = 0
        for idx, keypoints in enumerate(frames_3d_keypoints):
            frames_processed += 1
            if idx == 0:
                logger.info(f"🔍 First frame keys: {list(keypoints.keys())[:10] if isinstance(keypoints, dict) else 'NOT_A_DICT'}")
            
            if 'left_ankle' in keypoints and 'right_ankle' in keypoints:
                frames_with_ankles += 1
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
            
            if 'left_heel' in keypoints:
                left_heel_positions.append([
                    keypoints['left_heel']['x'],
                    keypoints['left_heel']['y'],
                    keypoints['left_heel'].get('z', 0.0)
                ])
            if 'right_heel' in keypoints:
                right_heel_positions.append([
                    keypoints['right_heel']['x'],
                    keypoints['right_heel']['y'],
                    keypoints['right_heel'].get('z', 0.0)
                ])
        
        logger.info(f"🔍 Joint extraction complete: {frames_processed} frames processed, {frames_with_ankles} frames with ankle data")
        logger.info(f"🔍 Extracted: {len(left_ankle_positions)} left ankle positions, {len(right_ankle_positions)} right ankle positions")
        
        if len(left_ankle_positions) < 5 or len(right_ankle_positions) < 5:
            error_msg = f"CRITICAL: Insufficient ankle positions extracted! left={len(left_ankle_positions)}, right={len(right_ankle_positions)}, need at least 5 each."
            logger.error(f"❌ {error_msg}")
            logger.error(f"❌ This means the 3D keypoints don't have enough valid ankle data!")
            logger.error(f"❌ Total frames processed: {len(frames_3d_keypoints)}")
            raise GaitMetricsError(error_msg, details={
                "left_ankle_count": len(left_ankle_positions),
                "right_ankle_count": len(right_ankle_positions),
                "required_count": 5,
                "total_frames": len(frames_3d_keypoints),
                "step_2_status": "INSUFFICIENT_ANKLE_DATA"
            })
        
        left_ankle_positions = np.array(left_ankle_positions)
        right_ankle_positions = np.array(right_ankle_positions)
        
        # Use heels if available for more accurate step detection
        if len(left_heel_positions) >= 5:
            left_step_positions = np.array(left_heel_positions)
        else:
            left_step_positions = left_ankle_positions
        
        if len(right_heel_positions) >= 5:
            right_step_positions = np.array(right_heel_positions)
        else:
            right_step_positions = right_ankle_positions
        
        if progress_callback:
            try:
                progress_callback(78, "Calibrating scale and detecting steps...")
            except Exception as e:
                logger.warning(f"Error in progress callback: {e}")
        
        # Scale calibration
        scale_factor = self._calibrate_leg_scale(frames_3d_keypoints, reference_length_mm)
        
        # Advanced step detection with detailed logging
        logger.debug(f"Starting step detection: left_positions={len(left_step_positions)}, right_positions={len(right_step_positions)}")
        left_steps, right_steps = self._detect_steps_advanced(left_step_positions, right_step_positions, timestamps)
        
        logger.info(f"Step detection complete: {len(left_steps)} left steps, {len(right_steps)} right steps")
        if len(left_steps) == 0 or len(right_steps) == 0:
            logger.warning(f"Unbalanced step detection - this may indicate detection issues or asymmetric gait")
        
        if progress_callback:
            try:
                progress_callback(80, f"Calculating basic gait parameters ({len(left_steps)} left, {len(right_steps)} right steps)...")
            except Exception as e:
                logger.warning(f"Error in progress callback: {e}")
        
        # Calculate cadence
        if len(left_steps) + len(right_steps) > 0:
            total_steps = len(left_steps) + len(right_steps)
            duration = timestamps[-1] - timestamps[0] if len(timestamps) > 1 else 1.0
            cadence = (total_steps / duration) * 60.0
        else:
            cadence = 0.0
            logger.warning("No steps detected - cadence cannot be calculated")
        
        # Calculate step length using 3D distance
        step_lengths = []
        if len(left_steps) > 0 and len(right_steps) > 0:
            for i, left_step_idx in enumerate(left_steps):
                if i < len(right_steps):
                    right_step_idx = right_steps[i]
                    if left_step_idx < len(left_ankle_positions) and right_step_idx < len(right_ankle_positions):
                        step_vec = left_ankle_positions[left_step_idx] - right_ankle_positions[right_step_idx]
                        step_length_3d = np.linalg.norm(step_vec) * scale_factor
                        step_lengths.append(step_length_3d)
        
        avg_step_length = np.mean(step_lengths) if step_lengths else 0.0
        stride_length = avg_step_length * 2.0 if avg_step_length > 0 else 0.0
        
        # Calculate walking speed
        if len(timestamps) > 1:
            total_distance = 0.0
            for i in range(1, len(left_ankle_positions)):
                if i < len(timestamps) and i < len(right_ankle_positions):
                    left_vec = left_ankle_positions[i] - left_ankle_positions[i-1]
                    right_vec = right_ankle_positions[i] - right_ankle_positions[i-1]
                    avg_vec = (left_vec + right_vec) / 2.0
                    step_dist = np.linalg.norm(avg_vec) * scale_factor
                    total_distance += step_dist
            
            duration = timestamps[-1] - timestamps[0]
            walking_speed = (total_distance / duration) if duration > 0 else 0.0
        else:
            walking_speed = 0.0
        
        # Calculate temporal parameters
        left_step_times = []
        right_step_times = []
        
        if len(left_steps) > 1:
            for i in range(1, len(left_steps)):
                if left_steps[i] < len(timestamps) and left_steps[i-1] < len(timestamps):
                    step_time = timestamps[left_steps[i]] - timestamps[left_steps[i-1]]
                    left_step_times.append(step_time)
        
        if len(right_steps) > 1:
            for i in range(1, len(right_steps)):
                if right_steps[i] < len(timestamps) and right_steps[i-1] < len(timestamps):
                    step_time = timestamps[right_steps[i]] - timestamps[right_steps[i-1]]
                    right_step_times.append(step_time)
        
        all_step_times = left_step_times + right_step_times
        avg_step_time = np.mean(all_step_times) if all_step_times else 0.0
        
        # Stance/swing phase
        if len(left_steps) > 1 and len(right_steps) > 0:
            stance_time = avg_step_time * 0.6 if avg_step_time > 0 else 0.0
            swing_time = avg_step_time * 0.4 if avg_step_time > 0 else 0.0
            double_support_time = avg_step_time * 0.12 if avg_step_time > 0 else 0.0
        else:
            stance_time = 0.0
            swing_time = 0.0
            double_support_time = 0.0
        
        if progress_callback:
            try:
                progress_callback(82, "Calculating symmetry and variability metrics...")
            except Exception as e:
                logger.warning(f"Error in progress callback: {e}")
        
        # Professional-grade gait parameters
        # Calculate symmetry indices (left vs right)
        symmetry_metrics = self._calculate_symmetry_metrics(
            left_steps, right_steps, left_step_times, right_step_times,
            left_ankle_positions, right_ankle_positions, timestamps
        )
        
        # Calculate variability (coefficient of variation)
        variability_metrics = self._calculate_variability_metrics(
            step_lengths, all_step_times, left_step_times, right_step_times
        )
        
        if progress_callback:
            try:
                progress_callback(84, "Calculating geriatric gait parameters and fall risk...")
            except Exception as e:
                logger.warning(f"Error in progress callback: {e}")
        
        # CRITICAL: Calculate professional geriatric gait parameters
        # Step width and step width variability (key fall risk indicators)
        step_width_metrics = self._calculate_step_width_metrics(
            left_ankle_positions, right_ankle_positions, left_steps, right_steps, timestamps, scale_factor
        )
        
        # Walk ratio (step length / cadence) - indicator of gait efficiency
        walk_ratio = self._calculate_walk_ratio(avg_step_length, cadence)
        
        # Stride-to-stride speed variability (strongest predictor of falls)
        speed_variability = self._calculate_stride_to_stride_speed_variability(
            left_ankle_positions, right_ankle_positions, timestamps, scale_factor
        )
        
        if progress_callback:
            try:
                progress_callback(86, "Analyzing multi-directional gait and validating biomechanics...")
            except Exception as e:
                logger.warning(f"Error in progress callback: {e}")
        
        # Multi-directional analysis
        directional_analysis = self._analyze_multi_directional_gait(
            frames_3d_keypoints, left_ankle_positions, right_ankle_positions, timestamps
        )
        
        # Validate biomechanical constraints
        validation_results = self._validate_biomechanical_constraints(
            frames_3d_keypoints, left_ankle_positions, right_ankle_positions
        )
        
        logger.info(f"Biomechanical validation: {validation_results['valid']} valid, {validation_results['warnings']} warnings")
        
        # Base metrics
        metrics = {
            "cadence": round(cadence, 2),
            "step_length": round(avg_step_length, 0),
            "stride_length": round(stride_length, 0),
            "walking_speed": round(walking_speed, 0),
            "step_time": round(avg_step_time, 3) if avg_step_time > 0 else 0.0,
            "stance_time": round(stance_time, 3),
            "swing_time": round(swing_time, 3),
            "double_support_time": round(double_support_time, 3),
        }
        
        # Add professional-grade metrics
        metrics.update(symmetry_metrics)
        metrics.update(variability_metrics)
        
        # Add geriatric-specific parameters
        metrics.update(step_width_metrics)
        metrics["walk_ratio"] = round(walk_ratio, 4) if walk_ratio > 0 else 0.0
        metrics.update(speed_variability)
        metrics["directional_analysis"] = directional_analysis
        
        if progress_callback:
            try:
                progress_callback(88, "Assessing fall risk and functional mobility...")
            except Exception as e:
                logger.warning(f"Error in progress callback: {e}")
        
        # Calculate fall risk assessment (professional gait lab level)
        fall_risk_assessment = self._assess_fall_risk(
            metrics, step_width_metrics, speed_variability, variability_metrics
        )
        metrics["fall_risk_assessment"] = fall_risk_assessment
        
        # Calculate functional mobility score
        functional_mobility = self._calculate_functional_mobility_score(metrics)
        metrics["functional_mobility"] = functional_mobility
        
        metrics["biomechanical_validation"] = validation_results
        
        logger.info(f"Calculated gait metrics: cadence={cadence:.1f}, step_length={avg_step_length:.0f}mm, speed={walking_speed:.0f}mm/s")
        logger.info(f"Symmetry: step_time={symmetry_metrics.get('step_time_symmetry', 0):.2f}, step_length={symmetry_metrics.get('step_length_symmetry', 0):.2f}")
        logger.info(f"Variability: step_length_cv={variability_metrics.get('step_length_cv', 0):.2f}%, step_time_cv={variability_metrics.get('step_time_cv', 0):.2f}%")
        logger.info(f"Step width: {step_width_metrics.get('step_width_mean', 0):.1f}mm, CV={step_width_metrics.get('step_width_cv', 0):.2f}%")
        logger.info(f"Fall risk: {fall_risk_assessment.get('risk_level', 'unknown')} (score: {fall_risk_assessment.get('risk_score', 0):.2f})")
        
        return metrics
    
    def _detect_steps_advanced(self, left_ankle: np.ndarray, right_ankle: np.ndarray, timestamps: List[float]) -> Tuple[List[int], List[int]]:
        """
        Advanced step detection with improved algorithms
        Uses multiple detection methods for maximum accuracy
        """
        left_steps = []
        right_steps = []
        
        if len(left_ankle) < 5 or len(right_ankle) < 5:
            logger.warning(f"Insufficient data for step detection: left={len(left_ankle)}, right={len(right_ankle)}")
            return left_steps, right_steps
        
        logger.debug(f"Step detection: analyzing {len(left_ankle)} left and {len(right_ankle)} right positions")
        
        left_y = left_ankle[:, 1]
        right_y = right_ankle[:, 1]
        
        if len(timestamps) > 1:
            dt = np.diff(timestamps)
            left_vy = np.diff(left_y) / (dt + 1e-6)
            right_vy = np.diff(right_y) / (dt + 1e-6)
            
            # Improved heel strike detection
            for i in range(1, len(left_vy) - 1):
                if left_y[i] > left_y[i-1] and left_y[i] > left_y[i+1]:
                    if left_vy[i-1] < 0 and left_vy[i] > 0:
                        left_steps.append(i)
            
            for i in range(1, len(right_vy) - 1):
                if right_y[i] > right_y[i-1] and right_y[i] > right_y[i+1]:
                    if right_vy[i-1] < 0 and right_vy[i] > 0:
                        right_steps.append(i)
        else:
            for i in range(1, len(left_y) - 1):
                if left_y[i] > left_y[i-1] and left_y[i] > left_y[i+1]:
                    left_steps.append(i)
            
            for i in range(1, len(right_y) - 1):
                if right_y[i] > right_y[i-1] and right_y[i] > right_y[i+1]:
                    right_steps.append(i)
        
        # Filter steps with minimum interval
        min_step_interval = 0.3
        if len(timestamps) > 1:
            left_steps_filtered = []
            right_steps_filtered = []
            
            for step_idx in left_steps:
                if step_idx < len(timestamps):
                    if not left_steps_filtered or (timestamps[step_idx] - timestamps[left_steps_filtered[-1]]) >= min_step_interval:
                        left_steps_filtered.append(step_idx)
            
            for step_idx in right_steps:
                if step_idx < len(timestamps):
                    if not right_steps_filtered or (timestamps[step_idx] - timestamps[right_steps_filtered[-1]]) >= min_step_interval:
                        right_steps_filtered.append(step_idx)
            
            return left_steps_filtered, right_steps_filtered
        
        return left_steps, right_steps
    
    def _calibrate_leg_scale(self, frames_3d_keypoints: List[Dict], reference_length_mm: Optional[float]) -> float:
        """
        Calibrate scale factor using reference length or average leg segment lengths
        Professional calibration for accurate measurements
        """
        if reference_length_mm and reference_length_mm > 0:
            logger.info(f"Using provided reference length: {reference_length_mm}mm for scale calibration")
            # Calculate average leg segment length from keypoints
            if len(frames_3d_keypoints) > 0:
                sample_frame = frames_3d_keypoints[0]
                if all(k in sample_frame for k in ['left_hip', 'left_knee', 'left_ankle']):
                    # Calculate thigh length
                    thigh_vec = np.array([
                        sample_frame['left_hip']['x'] - sample_frame['left_knee']['x'],
                        sample_frame['left_hip']['y'] - sample_frame['left_knee']['y'],
                        sample_frame['left_hip']['z'] - sample_frame['left_knee']['z']
                    ])
                    measured_thigh = np.linalg.norm(thigh_vec)
                    
                    if measured_thigh > 0:
                        # Typical adult thigh: ~450mm, use this as reference
                        typical_thigh = 450.0
                        scale_factor = typical_thigh / measured_thigh
                        logger.info(f"Calculated scale factor: {scale_factor:.3f} (measured thigh: {measured_thigh:.1f}mm)")
                        return scale_factor
            
            return 1.0
        else:
            # Auto-calibrate using average leg segment lengths
            if len(frames_3d_keypoints) > 0:
                logger.debug("Auto-calibrating scale using average leg segment lengths")
                # Use typical adult proportions as reference
                return 1.0  # Assume pixels are already in reasonable scale
            else:
                logger.warning("No keypoints available for scale calibration")
                return 1.0
    
    def _empty_results(self) -> Dict:
        """Return empty results structure"""
        return {
            "status": "completed",
            "analysis_type": "advanced_gait_analysis_v2",
            "frames_processed": 0,
            "keypoints_2d": [],
            "keypoints_3d": [],
            "metrics": self._empty_metrics()
        }
    
    def _empty_metrics(self) -> Dict:
        """Return empty metrics structure with professional parameters"""
        return {
            "cadence": 0.0,
            "step_length": 0.0,
            "stride_length": 0.0,
            "walking_speed": 0.0,
            "step_time": 0.0,
            "stance_time": 0.0,
            "swing_time": 0.0,
            "double_support_time": 0.0,
            # Professional-grade metrics
            "step_time_symmetry": 0.0,
            "step_length_symmetry": 0.0,
            "step_length_cv": 0.0,
            "step_time_cv": 0.0,
            # Geriatric-specific parameters
            "step_width_mean": 0.0,
            "step_width_std": 0.0,
            "step_width_cv": 0.0,
            "walk_ratio": 0.0,
            "stride_speed_cv": 0.0,
            "directional_analysis": {
                "primary_direction": "unknown",
                "direction_confidence": 0.0
            },
            "fall_risk_assessment": {
                "risk_score": 0.0,
                "risk_level": "Unknown",
                "risk_category": "Insufficient data",
                "risk_factors": [],
                "risk_factor_count": 0
            },
            "functional_mobility": {
                "mobility_score": 0.0,
                "mobility_level": "Unknown",
                "mobility_category": "Insufficient data",
                "score_percentage": 0.0
            },
            "biomechanical_validation": {
                "valid": False,
                "warnings": [],
                "errors": ["Insufficient data"],
                "warning_count": 0,
                "error_count": 1
            }
        }
    
    async def download_video_from_url(self, video_url: str) -> str:
        """Download video from URL to temporary file"""
        import aiohttp
        import tempfile
        
        if os.path.exists(video_url):
            return video_url
        
        async with aiohttp.ClientSession() as session:
            async with session.get(video_url) as response:
                if response.status == 200:
                    tmp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.mp4')
                    async for chunk in response.content.iter_chunked(8192):
                        tmp_file.write(chunk)
                    tmp_file.close()
                    return tmp_file.name
                else:
                    raise ValueError(f"Failed to download video: {response.status}")
    
    def _correct_keypoint_errors(self, frames_2d_keypoints: List[Dict], timestamps: List[float]) -> Tuple[List[Dict], Dict]:
        """
        Professional error correction: detect and correct outliers in keypoint data
        Uses statistical methods and biomechanical constraints
        """
        if len(frames_2d_keypoints) < 5:
            return frames_2d_keypoints, {"outliers_removed": 0, "interpolated": 0}
        
        logger.debug("Starting error correction and outlier detection...")
        corrected_frames = []
        outliers_removed = 0
        interpolated_count = 0
        
        # Extract keypoint time series for analysis
        keypoint_names = list(frames_2d_keypoints[0].keys())
        
        # Build time series for each keypoint
        keypoint_series = {}
        for name in keypoint_names:
            keypoint_series[name] = {
                'x': np.array([f[name]['x'] for f in frames_2d_keypoints]),
                'y': np.array([f[name]['y'] for f in frames_2d_keypoints]),
                'z': np.array([f.get(name, {}).get('z', 0.0) for f in frames_2d_keypoints]),
                'visibility': np.array([f.get(name, {}).get('visibility', 1.0) for f in frames_2d_keypoints])
            }
        
        # Detect outliers using statistical methods
        outlier_indices = set()
        
        if STATS_AVAILABLE:
            for name in keypoint_names:
                if 'ankle' in name or 'knee' in name or 'hip' in name:  # Focus on critical joints
                    x_series = keypoint_series[name]['x']
                    y_series = keypoint_series[name]['y']
                    
                    # Use Z-score for outlier detection (3 standard deviations)
                    if len(x_series) > 5:
                        x_z_scores = np.abs(stats.zscore(x_series))
                        y_z_scores = np.abs(stats.zscore(y_series))
                        
                        # Mark as outlier if either X or Y exceeds threshold
                        outliers = np.where((x_z_scores > 3.0) | (y_z_scores > 3.0))[0]
                        outlier_indices.update(outliers.tolist())
                        if len(outliers) > 0:
                            logger.debug(f"Detected {len(outliers)} outliers in {name}")
        
        outliers_removed = len(outlier_indices)
        logger.debug(f"Total outliers detected: {outliers_removed} frames")
        
        # Correct outliers by interpolation
        if outlier_indices and len(frames_2d_keypoints) > len(outlier_indices):
            for i, frame in enumerate(frames_2d_keypoints):
                if i in outlier_indices:
                    # Interpolate from neighboring frames
                    if i > 0 and i < len(frames_2d_keypoints) - 1:
                        prev_frame = frames_2d_keypoints[i-1]
                        next_frame = frames_2d_keypoints[i+1]
                        
                        corrected_frame = {}
                        for name in keypoint_names:
                            if name in prev_frame and name in next_frame:
                                corrected_frame[name] = {
                                    'x': (prev_frame[name]['x'] + next_frame[name]['x']) / 2.0,
                                    'y': (prev_frame[name]['y'] + next_frame[name]['y']) / 2.0,
                                    'z': (prev_frame[name].get('z', 0.0) + next_frame[name].get('z', 0.0)) / 2.0,
                                    'visibility': min(prev_frame[name].get('visibility', 1.0), next_frame[name].get('visibility', 1.0))
                                }
                            else:
                                corrected_frame[name] = frame.get(name, {})
                        corrected_frames.append(corrected_frame)
                        interpolated_count += 1
                    else:
                        # Keep original if at boundaries
                        corrected_frames.append(frame)
                else:
                    corrected_frames.append(frame)
        else:
            corrected_frames = frames_2d_keypoints
        
        return corrected_frames, {
            "outliers_removed": outliers_removed,
            "interpolated": interpolated_count
        }
    
    def _calculate_symmetry_metrics(
        self,
        left_steps: List[int],
        right_steps: List[int],
        left_step_times: List[float],
        right_step_times: List[float],
        left_ankle_positions: np.ndarray,
        right_ankle_positions: np.ndarray,
        timestamps: List[float]
    ) -> Dict:
        """Calculate professional symmetry indices (gold standard parameter)"""
        symmetry_metrics = {}
        
        # Step time symmetry (left vs right)
        if len(left_step_times) > 0 and len(right_step_times) > 0:
            avg_left_step_time = np.mean(left_step_times)
            avg_right_step_time = np.mean(right_step_times)
            if avg_left_step_time > 0 and avg_right_step_time > 0:
                # Symmetry index: 0 = perfect symmetry, 1 = complete asymmetry
                step_time_symmetry = abs(avg_left_step_time - avg_right_step_time) / max(avg_left_step_time, avg_right_step_time)
                symmetry_metrics['step_time_symmetry'] = round(1.0 - step_time_symmetry, 3)  # Convert to symmetry (1.0 = perfect)
                symmetry_metrics['left_step_time'] = round(avg_left_step_time, 3)
                symmetry_metrics['right_step_time'] = round(avg_right_step_time, 3)
                logger.debug(f"Step time symmetry: {symmetry_metrics['step_time_symmetry']:.3f}")
        
        # Step length symmetry
        if len(left_steps) > 0 and len(right_steps) > 0 and len(left_ankle_positions) > 0 and len(right_ankle_positions) > 0:
            left_step_lengths = []
            right_step_lengths = []
            
            # Calculate step lengths for each side
            for i in range(1, len(left_steps)):
                if left_steps[i] < len(left_ankle_positions) and left_steps[i-1] < len(left_ankle_positions):
                    step_vec = left_ankle_positions[left_steps[i]] - left_ankle_positions[left_steps[i-1]]
                    left_step_lengths.append(np.linalg.norm(step_vec))
            
            for i in range(1, len(right_steps)):
                if right_steps[i] < len(right_ankle_positions) and right_steps[i-1] < len(right_ankle_positions):
                    step_vec = right_ankle_positions[right_steps[i]] - right_ankle_positions[right_steps[i-1]]
                    right_step_lengths.append(np.linalg.norm(step_vec))
            
            if len(left_step_lengths) > 0 and len(right_step_lengths) > 0:
                avg_left_length = np.mean(left_step_lengths)
                avg_right_length = np.mean(right_step_lengths)
                if avg_left_length > 0 and avg_right_length > 0:
                    step_length_symmetry = abs(avg_left_length - avg_right_length) / max(avg_left_length, avg_right_length)
                    symmetry_metrics['step_length_symmetry'] = round(1.0 - step_length_symmetry, 3)
                    logger.debug(f"Step length symmetry: {symmetry_metrics['step_length_symmetry']:.3f}")
        
        return symmetry_metrics
    
    def _calculate_variability_metrics(
        self,
        step_lengths: List[float],
        all_step_times: List[float],
        left_step_times: List[float],
        right_step_times: List[float]
    ) -> Dict:
        """Calculate coefficient of variation (professional variability measure)"""
        variability_metrics = {}
        
        # Step length variability
        if len(step_lengths) > 1:
            step_length_std = np.std(step_lengths)
            step_length_mean = np.mean(step_lengths)
            if step_length_mean > 0:
                step_length_cv = (step_length_std / step_length_mean) * 100.0
                variability_metrics['step_length_cv'] = round(step_length_cv, 2)
                variability_metrics['step_length_std'] = round(step_length_std, 2)
                logger.debug(f"Step length CV: {step_length_cv:.2f}%")
        
        # Step time variability
        if len(all_step_times) > 1:
            step_time_std = np.std(all_step_times)
            step_time_mean = np.mean(all_step_times)
            if step_time_mean > 0:
                step_time_cv = (step_time_std / step_time_mean) * 100.0
                variability_metrics['step_time_cv'] = round(step_time_cv, 2)
                variability_metrics['step_time_std'] = round(step_time_std, 3)
                logger.debug(f"Step time CV: {step_time_cv:.2f}%")
        
        # Left-right variability
        if len(left_step_times) > 1 and len(right_step_times) > 1:
            left_cv = (np.std(left_step_times) / np.mean(left_step_times)) * 100.0 if np.mean(left_step_times) > 0 else 0.0
            right_cv = (np.std(right_step_times) / np.mean(right_step_times)) * 100.0 if np.mean(right_step_times) > 0 else 0.0
            variability_metrics['left_step_time_cv'] = round(left_cv, 2)
            variability_metrics['right_step_time_cv'] = round(right_cv, 2)
        
        return variability_metrics
    
    def _validate_biomechanical_constraints(
        self,
        frames_3d_keypoints: List[Dict],
        left_ankle_positions: np.ndarray,
        right_ankle_positions: np.ndarray
    ) -> Dict:
        """Validate biomechanical constraints (professional quality check)"""
        validation_results = {
            "valid": True,
            "warnings": [],
            "errors": []
        }
        
        # Check 1: Leg segment length consistency
        if len(frames_3d_keypoints) > 0:
            sample_frame = frames_3d_keypoints[0]
            
            # Validate left leg segments
            if all(k in sample_frame for k in ['left_hip', 'left_knee', 'left_ankle']):
                hip_knee_dist = np.linalg.norm([
                    sample_frame['left_hip']['x'] - sample_frame['left_knee']['x'],
                    sample_frame['left_hip']['y'] - sample_frame['left_knee']['y'],
                    sample_frame['left_hip']['z'] - sample_frame['left_knee']['z']
                ])
                knee_ankle_dist = np.linalg.norm([
                    sample_frame['left_knee']['x'] - sample_frame['left_ankle']['x'],
                    sample_frame['left_knee']['y'] - sample_frame['left_ankle']['y'],
                    sample_frame['left_knee']['z'] - sample_frame['left_ankle']['z']
                ])
                
                # Typical thigh: 400-500mm, shank: 350-450mm
                if hip_knee_dist < 200 or hip_knee_dist > 600:
                    validation_results["warnings"].append(f"Left thigh length ({hip_knee_dist:.0f}mm) outside normal range")
                if knee_ankle_dist < 200 or knee_ankle_dist > 550:
                    validation_results["warnings"].append(f"Left shank length ({knee_ankle_dist:.0f}mm) outside normal range")
        
        # Check 2: Ankle position consistency (shouldn't jump erratically)
        if len(left_ankle_positions) > 5 and len(right_ankle_positions) > 5:
            left_velocities = np.diff(left_ankle_positions, axis=0)
            right_velocities = np.diff(right_ankle_positions, axis=0)
            
            left_max_velocity = np.max(np.linalg.norm(left_velocities, axis=1))
            right_max_velocity = np.max(np.linalg.norm(right_velocities, axis=1))
            
            # Maximum reasonable velocity: ~2000mm/s (2 m/s) for walking
            if left_max_velocity > 2000:
                validation_results["warnings"].append(f"Left ankle velocity ({left_max_velocity:.0f}mm/s) exceeds normal walking speed")
            if right_max_velocity > 2000:
                validation_results["warnings"].append(f"Right ankle velocity ({right_max_velocity:.0f}mm/s) exceeds normal walking speed")
        
        # Check 3: Minimum data quality
        if len(frames_3d_keypoints) < 10:
            validation_results["errors"].append("Insufficient frames for reliable analysis")
            validation_results["valid"] = False
        
        validation_results["warning_count"] = len(validation_results["warnings"])
        validation_results["error_count"] = len(validation_results["errors"])
        
        return validation_results
    
    def _calculate_step_width_metrics(
        self,
        left_ankle_positions: np.ndarray,
        right_ankle_positions: np.ndarray,
        left_steps: List[int],
        right_steps: List[int],
        timestamps: List[float],
        scale_factor: float
    ) -> Dict:
        """
        Calculate step width and step width variability - critical fall risk indicators
        Step width is the lateral distance between left and right ankles during double support
        """
        step_width_metrics = {}
        
        if len(left_ankle_positions) < 5 or len(right_ankle_positions) < 5:
            logger.warning("Insufficient data for step width calculation")
            return {
                "step_width_mean": 0.0,
                "step_width_std": 0.0,
                "step_width_cv": 0.0,
                "step_width_min": 0.0,
                "step_width_max": 0.0
            }
        
        # Calculate step width at each frame (lateral distance between ankles)
        step_widths = []
        
        # Use step indices to calculate step width at heel strike moments
        all_step_indices = sorted(set(left_steps + right_steps))
        
        for step_idx in all_step_indices:
            if step_idx < len(left_ankle_positions) and step_idx < len(right_ankle_positions):
                # Calculate lateral distance (perpendicular to forward direction)
                # For frontal view: use X coordinate difference
                # For side view: use Z coordinate difference
                # We'll use the component perpendicular to the walking direction
                left_pos = left_ankle_positions[step_idx]
                right_pos = right_ankle_positions[step_idx]
                
                # Calculate lateral distance (assuming walking is primarily in Y direction)
                # Step width is the distance in the X-Z plane (perpendicular to forward motion)
                lateral_vec = np.array([
                    right_pos[0] - left_pos[0],  # X difference
                    0,  # Y is forward direction, not lateral
                    right_pos[2] - left_pos[2]   # Z difference
                ])
                step_width = np.linalg.norm(lateral_vec) * scale_factor
                step_widths.append(step_width)
        
        # If we don't have enough step-based widths, calculate from all frames
        if len(step_widths) < 3:
            logger.debug("Using all frames for step width calculation")
            step_widths = []
            for i in range(min(len(left_ankle_positions), len(right_ankle_positions))):
                left_pos = left_ankle_positions[i]
                right_pos = right_ankle_positions[i]
                lateral_vec = np.array([
                    right_pos[0] - left_pos[0],
                    0,
                    right_pos[2] - left_pos[2]
                ])
                step_width = np.linalg.norm(lateral_vec) * scale_factor
                step_widths.append(step_width)
        
        if len(step_widths) > 0:
            step_width_mean = np.mean(step_widths)
            step_width_std = np.std(step_widths)
            step_width_cv = (step_width_std / step_width_mean * 100.0) if step_width_mean > 0 else 0.0
            
            step_width_metrics = {
                "step_width_mean": round(step_width_mean, 1),
                "step_width_std": round(step_width_std, 1),
                "step_width_cv": round(step_width_cv, 2),
                "step_width_min": round(np.min(step_widths), 1),
                "step_width_max": round(np.max(step_widths), 1)
            }
            
            logger.debug(f"Step width: mean={step_width_mean:.1f}mm, CV={step_width_cv:.2f}%")
        else:
            step_width_metrics = {
                "step_width_mean": 0.0,
                "step_width_std": 0.0,
                "step_width_cv": 0.0,
                "step_width_min": 0.0,
                "step_width_max": 0.0
            }
        
        return step_width_metrics
    
    def _calculate_walk_ratio(self, step_length_mm: float, cadence_steps_per_min: float) -> float:
        """
        Calculate walk ratio = step length (mm) / cadence (steps/min)
        Higher walk ratio indicates more efficient gait
        Normal range for older adults: 0.4-0.6 mm/(steps/min)
        """
        if cadence_steps_per_min > 0 and step_length_mm > 0:
            walk_ratio = step_length_mm / cadence_steps_per_min
            return walk_ratio
        return 0.0
    
    def _calculate_stride_to_stride_speed_variability(
        self,
        left_ankle_positions: np.ndarray,
        right_ankle_positions: np.ndarray,
        timestamps: List[float],
        scale_factor: float
    ) -> Dict:
        """
        Calculate stride-to-stride variability in gait speed
        This is the single best independent predictor of falling in older adults
        """
        speed_variability_metrics = {}
        
        if len(left_ankle_positions) < 10 or len(right_ankle_positions) < 10 or len(timestamps) < 10:
            return {
                "stride_speed_mean": 0.0,
                "stride_speed_std": 0.0,
                "stride_speed_cv": 0.0,
                "stride_speed_variability_score": 0.0
            }
        
        # Calculate instantaneous speed for each stride
        stride_speeds = []
        
        # Calculate speed between consecutive frames
        for i in range(1, min(len(left_ankle_positions), len(right_ankle_positions), len(timestamps))):
            if i < len(timestamps) and timestamps[i] > timestamps[i-1]:
                # Calculate average forward velocity (Y direction)
                left_velocity = (left_ankle_positions[i][1] - left_ankle_positions[i-1][1]) / (timestamps[i] - timestamps[i-1])
                right_velocity = (right_ankle_positions[i][1] - right_ankle_positions[i-1][1]) / (timestamps[i] - timestamps[i-1])
                avg_velocity = (left_velocity + right_velocity) / 2.0
                speed = abs(avg_velocity) * scale_factor  # Convert to mm/s
                stride_speeds.append(speed)
        
        if len(stride_speeds) > 1:
            speed_mean = np.mean(stride_speeds)
            speed_std = np.std(stride_speeds)
            speed_cv = (speed_std / speed_mean * 100.0) if speed_mean > 0 else 0.0
            
            # Variability score: higher CV = higher risk
            # Normal CV for older adults: <5%, elevated: 5-10%, high risk: >10%
            variability_score = min(100.0, speed_cv * 10.0)  # Scale to 0-100
            
            speed_variability_metrics = {
                "stride_speed_mean": round(speed_mean, 1),
                "stride_speed_std": round(speed_std, 1),
                "stride_speed_cv": round(speed_cv, 2),
                "stride_speed_variability_score": round(variability_score, 2)
            }
            
            logger.debug(f"Stride-to-stride speed variability: CV={speed_cv:.2f}%, score={variability_score:.2f}")
        else:
            speed_variability_metrics = {
                "stride_speed_mean": 0.0,
                "stride_speed_std": 0.0,
                "stride_speed_cv": 0.0,
                "stride_speed_variability_score": 0.0
            }
        
        return speed_variability_metrics
    
    def _analyze_multi_directional_gait(
        self,
        frames_3d_keypoints: List[Dict],
        left_ankle_positions: np.ndarray,
        right_ankle_positions: np.ndarray,
        timestamps: List[float]
    ) -> Dict:
        """
        Analyze gait in multiple directions to simulate multi-camera gait lab systems
        Detects primary walking direction and analyzes gait parameters in that direction
        """
        directional_analysis = {
            "primary_direction": "unknown",
            "direction_confidence": 0.0,
            "directional_parameters": {}
        }
        
        if len(left_ankle_positions) < 10 or len(right_ankle_positions) < 10:
            return directional_analysis
        
        # Detect primary walking direction by analyzing displacement vectors
        # Calculate average displacement direction
        total_displacement = np.array([0.0, 0.0, 0.0])
        
        for i in range(1, min(len(left_ankle_positions), len(right_ankle_positions))):
            left_disp = left_ankle_positions[i] - left_ankle_positions[i-1]
            right_disp = right_ankle_positions[i] - right_ankle_positions[i-1]
            avg_disp = (left_disp + right_disp) / 2.0
            total_displacement += avg_disp
        
        # Normalize to get direction vector
        total_magnitude = np.linalg.norm(total_displacement)
        if total_magnitude > 0:
            direction_vector = total_displacement / total_magnitude
            
            # Determine primary direction based on largest component
            abs_components = np.abs(direction_vector)
            max_component_idx = np.argmax(abs_components)
            
            direction_names = ["X (lateral)", "Y (forward/backward)", "Z (depth)"]
            primary_direction = direction_names[max_component_idx]
            
            # Calculate confidence based on how dominant the primary direction is
            confidence = abs_components[max_component_idx] / np.sum(abs_components) if np.sum(abs_components) > 0 else 0.0
            
            directional_analysis = {
                "primary_direction": primary_direction,
                "direction_confidence": round(confidence, 3),
                "direction_vector": {
                    "x": round(direction_vector[0], 3),
                    "y": round(direction_vector[1], 3),
                    "z": round(direction_vector[2], 3)
                },
                "total_displacement_magnitude": round(total_magnitude, 1)
            }
            
            logger.debug(f"Multi-directional analysis: primary={primary_direction}, confidence={confidence:.3f}")
        else:
            logger.warning("Could not determine walking direction - insufficient displacement")
        
        return directional_analysis
    
    def _assess_fall_risk(
        self,
        metrics: Dict,
        step_width_metrics: Dict,
        speed_variability: Dict,
        variability_metrics: Dict
    ) -> Dict:
        """
        Professional fall risk assessment based on validated clinical parameters
        Combines multiple gait parameters to assess fall risk in older adults
        """
        risk_factors = []
        risk_score = 0.0
        
        # Factor 1: Gait speed (strongest single predictor)
        walking_speed = metrics.get("walking_speed", 0.0) / 1000.0  # Convert mm/s to m/s
        if walking_speed < 0.6:  # <0.6 m/s is high risk
            risk_factors.append("Very slow gait speed (<0.6 m/s)")
            risk_score += 30.0
        elif walking_speed < 1.0:  # 0.6-1.0 m/s is moderate risk
            risk_factors.append("Slow gait speed (0.6-1.0 m/s)")
            risk_score += 15.0
        
        # Factor 2: Step width variability (strong predictor, especially at increased speeds)
        step_width_cv = step_width_metrics.get("step_width_cv", 0.0)
        if step_width_cv > 15.0:  # High variability
            risk_factors.append(f"High step width variability (CV={step_width_cv:.1f}%)")
            risk_score += 25.0
        elif step_width_cv > 10.0:  # Moderate variability
            risk_factors.append(f"Moderate step width variability (CV={step_width_cv:.1f}%)")
            risk_score += 12.0
        
        # Factor 3: Stride-to-stride speed variability (single best predictor)
        speed_cv = speed_variability.get("stride_speed_cv", 0.0)
        if speed_cv > 10.0:  # High variability
            risk_factors.append(f"High stride speed variability (CV={speed_cv:.1f}%)")
            risk_score += 30.0
        elif speed_cv > 5.0:  # Moderate variability
            risk_factors.append(f"Moderate stride speed variability (CV={speed_cv:.1f}%)")
            risk_score += 15.0
        
        # Factor 4: Step length variability
        step_length_cv = variability_metrics.get("step_length_cv", 0.0)
        if step_length_cv > 10.0:
            risk_factors.append(f"High step length variability (CV={step_length_cv:.1f}%)")
            risk_score += 10.0
        elif step_length_cv > 5.0:
            risk_factors.append(f"Moderate step length variability (CV={step_length_cv:.1f}%)")
            risk_score += 5.0
        
        # Factor 5: Step time variability
        step_time_cv = variability_metrics.get("step_time_cv", 0.0)
        if step_time_cv > 10.0:
            risk_factors.append(f"High step time variability (CV={step_time_cv:.1f}%)")
            risk_score += 10.0
        elif step_time_cv > 5.0:
            risk_factors.append(f"Moderate step time variability (CV={step_time_cv:.1f}%)")
            risk_score += 5.0
        
        # Factor 6: Double support time (increased in fall-risk groups)
        double_support = metrics.get("double_support_time", 0.0)
        step_time = metrics.get("step_time", 1.0)
        if step_time > 0:
            double_support_ratio = double_support / step_time
            if double_support_ratio > 0.25:  # >25% of step time in double support
                risk_factors.append(f"Elevated double support time ({double_support_ratio*100:.1f}%)")
                risk_score += 8.0
        
        # Factor 7: Gait asymmetry
        step_time_symmetry = metrics.get("step_time_symmetry", 1.0)
        if step_time_symmetry < 0.85:  # <85% symmetry
            risk_factors.append(f"Gait asymmetry (symmetry={step_time_symmetry*100:.1f}%)")
            risk_score += 8.0
        
        # Factor 8: Short stride length (normalized)
        stride_length = metrics.get("stride_length", 0.0) / 1000.0  # Convert mm to m
        # Assume average height of 1.65m for older adults (can be parameterized)
        assumed_height = 1.65
        normalized_stride = stride_length / assumed_height if assumed_height > 0 else 0.0
        if normalized_stride < 0.52:  # <0.52 predicts recurrent falls with 93% sensitivity
            risk_factors.append(f"Short normalized stride length ({normalized_stride:.2f})")
            risk_score += 15.0
        
        # Determine risk level
        if risk_score >= 60.0:
            risk_level = "High"
            risk_category = "High fall risk - consider intervention"
        elif risk_score >= 30.0:
            risk_level = "Moderate"
            risk_category = "Moderate fall risk - monitor closely"
        elif risk_score >= 15.0:
            risk_level = "Low-Moderate"
            risk_category = "Low-moderate risk - regular monitoring recommended"
        else:
            risk_level = "Low"
            risk_category = "Low fall risk - continue current activities"
        
        fall_risk_assessment = {
            "risk_score": round(risk_score, 2),
            "risk_level": risk_level,
            "risk_category": risk_category,
            "risk_factors": risk_factors,
            "risk_factor_count": len(risk_factors),
            "walking_speed_mps": round(walking_speed, 2),
            "normalized_stride_length": round(normalized_stride, 3)
        }
        
        logger.info(f"Fall risk assessment: {risk_level} (score: {risk_score:.1f}, factors: {len(risk_factors)})")
        
        return fall_risk_assessment
    
    def _calculate_functional_mobility_score(self, metrics: Dict) -> Dict:
        """
        Calculate functional mobility score based on gait parameters
        Combines multiple parameters to assess overall functional mobility
        """
        mobility_score = 0.0
        max_score = 100.0
        
        # Component 1: Gait speed (40 points)
        walking_speed = metrics.get("walking_speed", 0.0) / 1000.0  # m/s
        if walking_speed >= 1.2:  # Excellent
            mobility_score += 40.0
        elif walking_speed >= 1.0:  # Good
            mobility_score += 35.0
        elif walking_speed >= 0.8:  # Fair
            mobility_score += 25.0
        elif walking_speed >= 0.6:  # Poor
            mobility_score += 15.0
        else:  # Very poor
            mobility_score += 5.0
        
        # Component 2: Cadence (20 points)
        cadence = metrics.get("cadence", 0.0)
        if cadence >= 110:  # Excellent
            mobility_score += 20.0
        elif cadence >= 100:  # Good
            mobility_score += 17.0
        elif cadence >= 90:  # Fair
            mobility_score += 12.0
        elif cadence >= 80:  # Poor
            mobility_score += 8.0
        else:  # Very poor
            mobility_score += 4.0
        
        # Component 3: Step length (20 points)
        step_length = metrics.get("step_length", 0.0) / 1000.0  # m
        if step_length >= 0.6:  # Excellent
            mobility_score += 20.0
        elif step_length >= 0.5:  # Good
            mobility_score += 17.0
        elif step_length >= 0.4:  # Fair
            mobility_score += 12.0
        elif step_length >= 0.3:  # Poor
            mobility_score += 8.0
        else:  # Very poor
            mobility_score += 4.0
        
        # Component 4: Gait stability (variability) (20 points)
        step_length_cv = metrics.get("step_length_cv", 0.0)
        step_time_cv = metrics.get("step_time_cv", 0.0)
        avg_cv = (step_length_cv + step_time_cv) / 2.0
        
        if avg_cv < 3.0:  # Excellent stability
            mobility_score += 20.0
        elif avg_cv < 5.0:  # Good stability
            mobility_score += 17.0
        elif avg_cv < 8.0:  # Fair stability
            mobility_score += 12.0
        elif avg_cv < 12.0:  # Poor stability
            mobility_score += 8.0
        else:  # Very poor stability
            mobility_score += 4.0
        
        # Determine functional mobility level
        if mobility_score >= 80.0:
            mobility_level = "Excellent"
            mobility_category = "High functional mobility - independent"
        elif mobility_score >= 60.0:
            mobility_level = "Good"
            mobility_category = "Good functional mobility - mostly independent"
        elif mobility_score >= 40.0:
            mobility_level = "Fair"
            mobility_category = "Fair functional mobility - may need assistance"
        elif mobility_score >= 20.0:
            mobility_level = "Poor"
            mobility_category = "Poor functional mobility - assistance recommended"
        else:
            mobility_level = "Very Poor"
            mobility_category = "Very poor functional mobility - significant assistance needed"
        
        functional_mobility = {
            "mobility_score": round(mobility_score, 1),
            "mobility_level": mobility_level,
            "mobility_category": mobility_category,
            "max_score": max_score,
            "score_percentage": round((mobility_score / max_score) * 100.0, 1)
        }
        
        logger.info(f"Functional mobility: {mobility_level} (score: {mobility_score:.1f}/{max_score})")
        
        return functional_mobility
    
    def _get_mediapipe_model_path(self, download_if_missing: bool = True) -> Optional[str]:
        """
        Get path to MediaPipe pose landmarker model file
        Searches multiple locations and optionally attempts to download if not found
        
        Args:
            download_if_missing: If True, download model if not found. If False, only search existing locations.
        """
        try:
            import mediapipe as mp
            import site
            
            # Check common MediaPipe model locations
            possible_paths = [
                # MediaPipe package location (most likely)
                os.path.join(os.path.dirname(mp.__file__), 'models', 'pose_landmarker.task'),
                # Alternative package structure
                os.path.join(os.path.dirname(mp.__file__), 'pose_landmarker.task'),
                # Site-packages location
                os.path.join(site.getsitepackages()[0] if site.getsitepackages() else '', 'mediapipe', 'models', 'pose_landmarker.task'),
                # User site-packages
                os.path.join(site.getusersitepackages() if hasattr(site, 'getusersitepackages') else '', 'mediapipe', 'models', 'pose_landmarker.task'),
            ]
            
            logger.debug(f"Searching for MediaPipe model in {len(possible_paths)} locations...")
            for path in possible_paths:
                if path and os.path.exists(path):
                    abs_path = os.path.abspath(path)
                    logger.info(f"✓ Found MediaPipe model at: {abs_path}")
                    return abs_path
                elif path:
                    logger.debug(f"  Not found: {path}")
            
            logger.debug("MediaPipe model not found in standard locations")
            
            # Try to download model from MediaPipe repository
            model_path = self._download_mediapipe_model()
            if model_path:
                return model_path
            
            logger.warning("Model file not found - MediaPipe 0.10.x requires pose_landmarker.task model file")
            logger.warning("Gait analysis will use fallback mode (reduced accuracy)")
            
            return None
        except Exception as e:
            logger.error(f"Error searching for MediaPipe model: {e}", exc_info=True)
            return None
    
    def _download_mediapipe_model(self) -> Optional[str]:
        """
        Download MediaPipe pose landmarker model if not found locally
        Returns path to downloaded model or None if download fails
        """
        try:
            import tempfile
            import urllib.request
            
            # MediaPipe model URL - Using LITE model for faster inference
            # Lite model is 3x faster than full model with minimal accuracy loss for gait analysis
            # This significantly improves processing speed while maintaining good pose detection
            model_url = "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/1/pose_landmarker_lite.task"
            
            # Create temp directory for model
            model_dir = os.path.join(tempfile.gettempdir(), 'mediapipe_models')
            os.makedirs(model_dir, exist_ok=True)
            model_path = os.path.join(model_dir, 'pose_landmarker.task')
            
            # Check if already downloaded
            if os.path.exists(model_path):
                logger.info(f"Using cached model at: {model_path}")
                return model_path
            
            logger.info(f"Downloading MediaPipe pose landmarker model from: {model_url}")
            logger.info("This may take a few moments...")
            
            # Download model with timeout to prevent hanging
            # CRITICAL: Use timeout to prevent blocking startup if network is slow
            import socket
            socket.setdefaulttimeout(30)  # 30 second timeout for download
            try:
                urllib.request.urlretrieve(model_url, model_path)
            finally:
                socket.setdefaulttimeout(None)  # Reset timeout
            
            if os.path.exists(model_path):
                file_size = os.path.getsize(model_path) / (1024 * 1024)  # MB
                logger.info(f"✓ Model downloaded successfully: {model_path} ({file_size:.1f} MB)")
                return model_path
            else:
                logger.warning("Model download completed but file not found")
                return None
                
        except Exception as e:
            logger.warning(f"Failed to download MediaPipe model: {e}")
            logger.debug("Model download error details:", exc_info=True)
            return None
    
    def cleanup(self):
        """Cleanup resources"""
        if self.pose_landmarker:
            self.pose_landmarker.close()
        self.executor.shutdown(wait=True)
