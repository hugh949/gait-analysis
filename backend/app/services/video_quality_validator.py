"""
Video Quality Validator for Gait Analysis
Validates that videos are suitable for AI vision models and provides user guidance
"""
from typing import Dict, List, Optional, Tuple
import numpy as np
from loguru import logger
import os

try:
    import cv2
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False
    cv2 = None

try:
    import mediapipe as mp
    from mediapipe.tasks import python
    from mediapipe.tasks.python import vision
    from mediapipe.tasks.python.vision import PoseLandmarker, PoseLandmarkerOptions, RunningMode
    # Try to import ImageFormat and VisionImage (same pattern as gait_analysis.py)
    try:
        from mediapipe.tasks.python.vision import ImageFormat
    except ImportError:
        try:
            from mediapipe.tasks.python.core.vision import ImageFormat
        except ImportError:
            try:
                ImageFormat = vision.ImageFormat
            except AttributeError:
                ImageFormat = None
    
    try:
        from mediapipe.tasks.python.vision import Image as VisionImage
    except ImportError:
        try:
            from mediapipe.tasks.python.core.vision import Image as VisionImage
        except ImportError:
            try:
                VisionImage = vision.Image
            except AttributeError:
                try:
                    VisionImage = mp.Image
                except AttributeError:
                    VisionImage = None
    
    MEDIAPIPE_AVAILABLE = True
except ImportError:
    MEDIAPIPE_AVAILABLE = False
    VisionImage = None
    ImageFormat = None


class VideoQualityValidator:
    """
    Validates video quality for gait analysis and provides recommendations
    Based on geriatric care gold standards for functional mobility assessment
    """
    
    def __init__(self, pose_landmarker=None):
        self.pose_landmarker = pose_landmarker
        self.quality_issues = []
        self.recommendations = []
    
    def validate_video_for_gait_analysis(
        self,
        video_path: str,
        view_type: str = "front",
        sample_frames: int = 20
    ) -> Dict:
        """
        Comprehensive video quality validation for gait analysis
        
        Returns:
            Dict with:
                - is_valid: bool
                - quality_score: float (0-100)
                - issues: List[str]
                - recommendations: List[str]
                - pose_detection_rate: float (0-1)
                - critical_joints_detected: bool
        """
        logger.info(f"🔍 Starting video quality validation: {video_path}")
        
        validation_result = {
            "is_valid": False,
            "quality_score": 0.0,
            "issues": [],
            "recommendations": [],
            "pose_detection_rate": 0.0,
            "critical_joints_detected": False,
            "video_properties": {},
            "sample_analysis": {}
        }
        
        # Step 1: Basic file validation
        if not os.path.exists(video_path):
            validation_result["issues"].append("Video file does not exist")
            validation_result["recommendations"].append("Please check that the video file was uploaded correctly")
            return validation_result
        
        if not CV2_AVAILABLE:
            validation_result["issues"].append("OpenCV not available - cannot process video")
            validation_result["recommendations"].append("Contact system administrator - video processing library missing")
            return validation_result
        
        # Step 2: Video file can be opened
        try:
            cap = cv2.VideoCapture(video_path)
            if not cap.isOpened():
                validation_result["issues"].append("Video file cannot be opened - may be corrupted or unsupported format")
                validation_result["recommendations"].append(
                    "Please ensure video is in a supported format (MP4, AVI, MOV, MKV) and not corrupted"
                )
                return validation_result
            
            # Get video properties
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            fps = cap.get(cv2.CAP_PROP_FPS)
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            duration = total_frames / fps if fps > 0 else 0
            
            validation_result["video_properties"] = {
                "total_frames": total_frames,
                "fps": fps,
                "width": width,
                "height": height,
                "duration_seconds": duration
            }
            
            logger.info(f"🔍 Video properties: {width}x{height}, {fps} fps, {total_frames} frames, {duration:.1f}s")
            
            # Validate video properties
            if total_frames == 0:
                validation_result["issues"].append("Video has 0 frames - file may be corrupted")
                validation_result["recommendations"].append("Please check the video file and try re-encoding it")
                cap.release()
                return validation_result
            
            if fps < 15:
                validation_result["issues"].append(f"Video frame rate too low ({fps:.1f} fps) - need at least 15 fps for accurate gait analysis")
                validation_result["recommendations"].append(
                    "Record video at 30 fps or higher for best results. Lower frame rates reduce gait analysis accuracy."
                )
            
            if duration < 3:
                validation_result["issues"].append(f"Video too short ({duration:.1f}s) - need at least 3 seconds for gait analysis")
                validation_result["recommendations"].append(
                    "Record at least 3-5 seconds of walking. For geriatric assessment, 5-10 seconds is recommended."
                )
            
            if width < 320 or height < 240:
                validation_result["issues"].append(f"Video resolution too low ({width}x{height}) - need at least 640x480")
                validation_result["recommendations"].append(
                    "Record video at 640x480 or higher resolution. Higher resolution improves pose detection accuracy."
                )
            
            # Step 3: Sample frames and test pose detection
            if MEDIAPIPE_AVAILABLE and self.pose_landmarker:
                pose_detection_results = self._test_pose_detection(cap, total_frames, sample_frames, view_type)
                validation_result["pose_detection_rate"] = pose_detection_results["detection_rate"]
                validation_result["critical_joints_detected"] = pose_detection_results["critical_joints_detected"]
                validation_result["sample_analysis"] = pose_detection_results["sample_analysis"]
                
                # Analyze pose detection quality
                if pose_detection_results["detection_rate"] < 0.3:
                    validation_result["issues"].append(
                        f"Pose detection rate too low ({pose_detection_results['detection_rate']*100:.1f}%) - "
                        f"AI cannot reliably detect person in video"
                    )
                    validation_result["recommendations"].extend([
                        "Ensure person is clearly visible and fully in frame",
                        "Use good lighting - avoid shadows and backlighting",
                        "Record against a contrasting background (person should stand out)",
                        "Ensure person is walking, not standing still",
                        "Avoid occlusions (objects blocking the person)"
                    ])
                elif pose_detection_results["detection_rate"] < 0.6:
                    validation_result["issues"].append(
                        f"Pose detection rate moderate ({pose_detection_results['detection_rate']*100:.1f}%) - "
                        f"may affect analysis accuracy"
                    )
                    validation_result["recommendations"].extend([
                        "Improve lighting conditions",
                        "Ensure person is fully visible in frame",
                        "Record from side view for better gait parameter visibility"
                    ])
                
                if not pose_detection_results["critical_joints_detected"]:
                    validation_result["issues"].append(
                        "Critical joints (ankles, knees) not reliably detected - cannot calculate gait parameters"
                    )
                    validation_result["recommendations"].extend([
                        "Record from side view - this provides best visibility of leg joints",
                        "Ensure legs are fully visible (not blocked by clothing or objects)",
                        "Wear form-fitting clothing that doesn't obscure leg joints",
                        "Ensure person is walking, not standing still"
                    ])
                
                # View-specific recommendations
                if view_type == "front":
                    if pose_detection_results["sample_analysis"].get("ankle_visibility_avg", 0) < 0.5:
                        validation_result["recommendations"].append(
                            "For front view, ensure ankles are clearly visible. Side view is recommended for better gait analysis."
                        )
                elif view_type == "side":
                    if pose_detection_results["sample_analysis"].get("ankle_visibility_avg", 0) < 0.7:
                        validation_result["recommendations"].append(
                            "For side view, ensure full side profile is visible with clear ankle and knee visibility"
                        )
            else:
                validation_result["issues"].append("Pose detection library not available - cannot validate video quality")
                validation_result["recommendations"].append("Contact system administrator - AI vision library missing")
            
            cap.release()
            
            # Calculate quality score
            quality_score = self._calculate_quality_score(validation_result)
            validation_result["quality_score"] = quality_score
            validation_result["is_valid"] = quality_score >= 60.0  # Minimum 60% quality score
            
            # Add geriatric care specific recommendations
            if validation_result["is_valid"]:
                validation_result["recommendations"].extend([
                    "✅ Video quality is acceptable for gait analysis",
                    "For geriatric functional mobility assessment:",
                    "  - Record 5-10 seconds of continuous walking",
                    "  - Ensure person walks at comfortable pace",
                    "  - Include at least 3-4 complete gait cycles",
                    "  - Record on flat, level surface"
                ])
            else:
                validation_result["recommendations"].extend([
                    "❌ Video quality is insufficient for accurate gait analysis",
                    "Please re-record video following the recommendations above"
                ])
            
            logger.info(f"🔍 Validation complete: is_valid={validation_result['is_valid']}, "
                       f"quality_score={quality_score:.1f}%, "
                       f"pose_detection_rate={validation_result['pose_detection_rate']*100:.1f}%")
            
            return validation_result
        
        except Exception as e:
            logger.error(f"❌ Error during video validation: {e}", exc_info=True)
            validation_result["issues"].append(f"Error validating video: {str(e)}")
            validation_result["recommendations"].append("Please check video file and try again")
            return validation_result
    
    def _test_pose_detection(
        self,
        cap: cv2.VideoCapture,
        total_frames: int,
        sample_frames: int,
        view_type: str
    ) -> Dict:
        """Test pose detection on sample frames"""
        logger.info(f"🔍 Testing pose detection on {sample_frames} sample frames...")
        
        detections = 0
        critical_joints_detected_count = 0
        ankle_visibilities = []
        knee_visibilities = []
        
        # Sample frames evenly throughout video
        frame_indices = np.linspace(0, total_frames - 1, sample_frames, dtype=int)
        
        for sample_idx, frame_num in enumerate(frame_indices):
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_num)
            ret, frame = cap.read()
            
            if not ret or frame is None:
                continue
            
            # Convert to RGB for MediaPipe
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            
            # Detect pose
            try:
                # Create MediaPipe Image object (same pattern as gait_analysis.py)
                mp_image = None
                vision_image_created = False
                
                if VisionImage:
                    # Method 1: Try with ImageFormat enum
                    if ImageFormat:
                        try:
                            if hasattr(ImageFormat, 'SRGB'):
                                image_format_enum = ImageFormat.SRGB
                            elif hasattr(ImageFormat, 'sRGB'):
                                image_format_enum = ImageFormat.sRGB
                            else:
                                image_format_enum = 1  # SRGB is typically 1
                            
                            mp_image = VisionImage(
                                image_format=image_format_enum,
                                data=rgb_frame
                            )
                            vision_image_created = True
                        except Exception:
                            pass
                    
                    # Method 2: Try with integer format value
                    if not vision_image_created:
                        try:
                            mp_image = VisionImage(
                                image_format=1,  # SRGB
                                data=rgb_frame
                            )
                            vision_image_created = True
                        except Exception:
                            pass
                
                # Method 3: Use numpy array directly (fallback)
                if not vision_image_created:
                    mp_image = rgb_frame
                
                detection_result = self.pose_landmarker.detect(mp_image)
                
                if detection_result and detection_result.pose_landmarks:
                    detections += 1
                    
                    # Check for critical joints
                    pose_landmarks = detection_result.pose_landmarks[0]
                    
                    # MediaPipe landmark indices for critical joints
                    # Left: 27 (ankle), 25 (knee), 23 (hip)
                    # Right: 28 (ankle), 26 (knee), 24 (hip)
                    left_ankle_idx = 27
                    right_ankle_idx = 28
                    left_knee_idx = 25
                    right_knee_idx = 26
                    
                    has_critical_joints = (
                        len(pose_landmarks) > max(left_ankle_idx, right_ankle_idx, left_knee_idx, right_knee_idx)
                    )
                    
                    if has_critical_joints:
                        # Check visibility of critical joints
                        left_ankle = pose_landmarks[left_ankle_idx] if len(pose_landmarks) > left_ankle_idx else None
                        right_ankle = pose_landmarks[right_ankle_idx] if len(pose_landmarks) > right_ankle_idx else None
                        left_knee = pose_landmarks[left_knee_idx] if len(pose_landmarks) > left_knee_idx else None
                        right_knee = pose_landmarks[right_knee_idx] if len(pose_landmarks) > right_knee_idx else None
                        
                        if left_ankle and right_ankle:
                            ankle_visibilities.append((left_ankle.visibility + right_ankle.visibility) / 2)
                        if left_knee and right_knee:
                            knee_visibilities.append((left_knee.visibility + right_knee.visibility) / 2)
                        
                        # Consider critical joints detected if visibility is reasonable
                        if (left_ankle and left_ankle.visibility > 0.3 and
                            right_ankle and right_ankle.visibility > 0.3):
                            critical_joints_detected_count += 1
                
            except Exception as e:
                logger.debug(f"Error detecting pose in sample frame {frame_num}: {e}")
                continue
        
        detection_rate = detections / len(frame_indices) if frame_indices else 0
        critical_joints_rate = critical_joints_detected_count / detections if detections > 0 else 0
        
        logger.info(f"🔍 Pose detection test results: {detections}/{len(frame_indices)} frames detected "
                   f"({detection_rate*100:.1f}%), "
                   f"critical joints in {critical_joints_detected_count}/{detections} detections "
                   f"({critical_joints_rate*100:.1f}%)")
        
        return {
            "detection_rate": detection_rate,
            "critical_joints_detected": critical_joints_rate >= 0.5,
            "sample_analysis": {
                "frames_tested": len(frame_indices),
                "poses_detected": detections,
                "ankle_visibility_avg": np.mean(ankle_visibilities) if ankle_visibilities else 0,
                "knee_visibility_avg": np.mean(knee_visibilities) if knee_visibilities else 0,
                "critical_joints_rate": critical_joints_rate
            }
        }
    
    def _calculate_quality_score(self, validation_result: Dict) -> float:
        """Calculate overall quality score (0-100)"""
        score = 100.0
        
        # Deduct points for issues
        issues = validation_result.get("issues", [])
        for issue in issues:
            if "too low" in issue.lower() or "too short" in issue.lower() or "cannot" in issue.lower():
                score -= 20
            elif "moderate" in issue.lower() or "may affect" in issue.lower():
                score -= 10
            elif "not reliably" in issue.lower() or "insufficient" in issue.lower():
                score -= 15
            else:
                score -= 5
        
        # Adjust based on pose detection rate
        pose_rate = validation_result.get("pose_detection_rate", 0)
        if pose_rate < 0.3:
            score -= 30
        elif pose_rate < 0.6:
            score -= 15
        elif pose_rate >= 0.8:
            score += 10  # Bonus for excellent detection
        
        # Adjust based on critical joints
        if not validation_result.get("critical_joints_detected", False):
            score -= 25
        
        return max(0.0, min(100.0, score))
