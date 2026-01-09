"""
Testing API endpoints for manual step-by-step gait analysis
Allows testing each step independently and using saved checkpoints
"""
from fastapi import APIRouter, UploadFile, File, HTTPException, Query
from fastapi.responses import JSONResponse
from typing import Optional, Dict
import os
import tempfile
import uuid
from datetime import datetime
from loguru import logger

from app.core.schemas import AnalysisResponse, AnalysisStatus
from app.core.exceptions import VideoProcessingError, DatabaseError, StorageError
from app.core.exceptions import gait_error_to_http
from app.services.gait_analysis import get_gait_analysis_service
from app.services.checkpoint_manager import CheckpointManager
from app.core.database_azure_sql import AzureSQLService
from app.services.azure_storage import AzureStorageService

router = APIRouter(prefix="/testing", tags=["Testing"])

# Initialize services
db_service = AzureSQLService()
storage_service = AzureStorageService()


@router.post("/upload")
async def upload_test_file(
    file: UploadFile = File(...),
    patient_id: Optional[str] = Query(None, description="Patient identifier")
) -> JSONResponse:
    """
    Upload a test video file and save it for step-by-step processing
    """
    request_id = str(uuid.uuid4())[:8]
    analysis_id = str(uuid.uuid4())
    
    try:
        logger.info(f"[TEST-{request_id}] ========== TEST FILE UPLOAD ==========")
        logger.info(f"[TEST-{request_id}] Analysis ID: {analysis_id}")
        logger.info(f"[TEST-{request_id}] File: {file.filename}")
        
        # Save file to temp location
        tmp_path = os.path.join(tempfile.gettempdir(), f"test_{analysis_id}_{file.filename}")
        
        with open(tmp_path, 'wb') as f:
            while chunk := await file.read(1024 * 1024):  # 1MB chunks
                f.write(chunk)
        
        file_size = os.path.getsize(tmp_path)
        logger.info(f"[TEST-{request_id}] File saved: {tmp_path} ({file_size / (1024*1024):.2f}MB)")
        
        # Create analysis record
        analysis_data = {
            'id': analysis_id,
            'patient_id': patient_id,
            'filename': file.filename,
            'video_url': tmp_path,  # Use temp file path
            'status': 'testing',
            'current_step': 'uploaded',
            'step_progress': 0,
            'step_message': 'Test file uploaded. Ready for step-by-step processing.'
        }
        
        creation_success = await db_service.create_analysis(analysis_data)
        if not creation_success:
            raise DatabaseError("Failed to create test analysis record")
        
        logger.info(f"[TEST-{request_id}] ✅ Test file uploaded successfully")
        
        return JSONResponse({
            "status": "success",
            "analysis_id": analysis_id,
            "message": "Test file uploaded successfully",
            "file_path": tmp_path,
            "file_size_mb": file_size / (1024*1024),
            "steps_available": {
                "step_1": True,
                "step_2": False,
                "step_3": False,
                "step_4": False
            }
        })
        
    except Exception as e:
        logger.error(f"[TEST-{request_id}] Error uploading test file: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to upload test file: {str(e)}")


@router.post("/step/1")
async def execute_step_1(
    analysis_id: str = Query(..., description="Analysis ID"),
    fps: float = Query(30.0, description="Video FPS"),
    view_type: str = Query("front", description="Camera view type")
) -> JSONResponse:
    """
    Manually execute Step 1: 2D Pose Estimation
    """
    request_id = str(uuid.uuid4())[:8]
    
    try:
        logger.info(f"[TEST-{request_id}] ========== EXECUTING STEP 1 ==========")
        logger.info(f"[TEST-{request_id}] Analysis ID: {analysis_id}")
        
        # Get analysis record
        analysis = await db_service.get_analysis(analysis_id)
        if not analysis:
            raise HTTPException(status_code=404, detail="Analysis not found")
        
        video_path = analysis.get('video_url')
        if not video_path or not os.path.exists(video_path):
            raise HTTPException(status_code=404, detail="Video file not found")
        
        # Update status
        await db_service.update_analysis(analysis_id, {
            'status': 'testing',
            'current_step': 'pose_estimation',
            'step_progress': 0,
            'step_message': 'Executing Step 1: 2D Pose Estimation...'
        })
        
        # Get gait analysis service
        gait_service = get_gait_analysis_service()
        if not gait_service:
            raise HTTPException(status_code=503, detail="Gait analysis service not available")
        
        # Set analysis_id for checkpoint management
        gait_service._current_analysis_id = analysis_id
        
        # Execute Step 1 only
        logger.info(f"[TEST-{request_id}] Starting Step 1 processing...")
        
        # Use the internal _process_video_sync method directly
        result = gait_service._process_video_sync(
            video_path=video_path,
            fps=fps,
            reference_length_mm=None,
            view_type=view_type,
            progress_callback=None
        )
        
        # Check if checkpoint was saved
        checkpoint_manager = CheckpointManager(analysis_id=analysis_id)
        step1_checkpoint = checkpoint_manager.load_step_1()
        
        if step1_checkpoint:
            logger.info(f"[TEST-{request_id}] ✅ Step 1 checkpoint saved: {len(step1_checkpoint.get('frames_2d_keypoints', []))} frames")
        else:
            logger.warning(f"[TEST-{request_id}] ⚠️ Step 1 checkpoint not found after processing")
        
        # Update status
        await db_service.update_analysis(analysis_id, {
            'status': 'testing',
            'current_step': 'pose_estimation',
            'step_progress': 100,
            'step_message': f'Step 1 complete: {len(result.get("frames_2d_keypoints", []))} frames processed'
        })
        
        return JSONResponse({
            "status": "success",
            "step": "step_1_pose_estimation",
            "analysis_id": analysis_id,
            "message": "Step 1 completed successfully",
            "result": {
                "frames_processed": len(result.get("frames_2d_keypoints", [])),
                "total_frames": result.get("total_frames", 0),
                "checkpoint_saved": step1_checkpoint is not None
            },
            "next_step_available": True
        })
        
    except Exception as e:
        logger.error(f"[TEST-{request_id}] Error executing Step 1: {e}", exc_info=True)
        await db_service.update_analysis(analysis_id, {
            'status': 'testing',
            'current_step': 'pose_estimation',
            'step_progress': 0,
            'step_message': f'Step 1 failed: {str(e)}'
        })
        raise HTTPException(status_code=500, detail=f"Step 1 failed: {str(e)}")


@router.post("/step/2")
async def execute_step_2(
    analysis_id: str = Query(..., description="Analysis ID"),
    view_type: str = Query("front", description="Camera view type")
) -> JSONResponse:
    """
    Manually execute Step 2: 3D Lifting (requires Step 1 checkpoint)
    """
    request_id = str(uuid.uuid4())[:8]
    
    try:
        logger.info(f"[TEST-{request_id}] ========== EXECUTING STEP 2 ==========")
        logger.info(f"[TEST-{request_id}] Analysis ID: {analysis_id}")
        
        # Check for Step 1 checkpoint
        checkpoint_manager = CheckpointManager(analysis_id=analysis_id)
        step1_checkpoint = checkpoint_manager.load_step_1()
        
        if not step1_checkpoint:
            raise HTTPException(status_code=400, detail="Step 1 checkpoint not found. Please run Step 1 first.")
        
        frames_2d_keypoints = step1_checkpoint.get('frames_2d_keypoints', [])
        frame_timestamps = step1_checkpoint.get('frame_timestamps', [])
        
        if not frames_2d_keypoints:
            raise HTTPException(status_code=400, detail="Step 1 checkpoint has no 2D keypoints")
        
        logger.info(f"[TEST-{request_id}] Loaded Step 1 checkpoint: {len(frames_2d_keypoints)} frames")
        
        # Update status
        await db_service.update_analysis(analysis_id, {
            'status': 'testing',
            'current_step': '3d_lifting',
            'step_progress': 0,
            'step_message': 'Executing Step 2: 3D Lifting...'
        })
        
        # Get gait analysis service
        gait_service = get_gait_analysis_service()
        if not gait_service:
            raise HTTPException(status_code=503, detail="Gait analysis service not available")
        
        # Set analysis_id for checkpoint management
        gait_service._current_analysis_id = analysis_id
        
        # Execute Step 2 only
        logger.info(f"[TEST-{request_id}] Starting Step 2 processing...")
        
        # Convert 2D keypoints from checkpoint (lists) back to numpy arrays if needed
        import numpy as np
        frames_2d_keypoints_np = [
            np.array([[kp[0], kp[1], kp[2] if len(kp) > 2 else 0.0] for kp in frame], dtype=np.float32)
            if frame else []
            for frame in frames_2d_keypoints
        ]
        
        frames_3d_keypoints = gait_service._lift_to_3d(frames_2d_keypoints_np, view_type)
        
        # Checkpoint is saved automatically in _lift_to_3d (via checkpoint_manager.save_step_2)
        step2_checkpoint = checkpoint_manager.load_step_2()
        
        if step2_checkpoint:
            logger.info(f"[TEST-{request_id}] ✅ Step 2 checkpoint saved: {len(step2_checkpoint.get('frames_3d_keypoints', []))} frames")
        else:
            logger.warning(f"[TEST-{request_id}] ⚠️ Step 2 checkpoint not found after processing")
        
        # Update status
        await db_service.update_analysis(analysis_id, {
            'status': 'testing',
            'current_step': '3d_lifting',
            'step_progress': 100,
            'step_message': f'Step 2 complete: {len(frames_3d_keypoints)} frames lifted to 3D'
        })
        
        return JSONResponse({
            "status": "success",
            "step": "step_2_3d_lifting",
            "analysis_id": analysis_id,
            "message": "Step 2 completed successfully",
            "result": {
                "frames_3d": len(frames_3d_keypoints),
                "frames_2d_input": len(frames_2d_keypoints),
                "checkpoint_saved": step2_checkpoint is not None
            },
            "next_step_available": True
        })
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[TEST-{request_id}] Error executing Step 2: {e}", exc_info=True)
        await db_service.update_analysis(analysis_id, {
            'status': 'testing',
            'current_step': '3d_lifting',
            'step_progress': 0,
            'step_message': f'Step 2 failed: {str(e)}'
        })
        raise HTTPException(status_code=500, detail=f"Step 2 failed: {str(e)}")


@router.post("/step/3")
async def execute_step_3(
    analysis_id: str = Query(..., description="Analysis ID"),
    fps: float = Query(30.0, description="Video FPS"),
    reference_length_mm: Optional[float] = Query(None, description="Reference length in mm")
) -> JSONResponse:
    """
    Manually execute Step 3: Gait Metrics Calculation (requires Step 2 checkpoint)
    """
    request_id = str(uuid.uuid4())[:8]
    
    try:
        logger.info(f"[TEST-{request_id}] ========== EXECUTING STEP 3 ==========")
        logger.info(f"[TEST-{request_id}] Analysis ID: {analysis_id}")
        
        # Check for Step 2 checkpoint
        checkpoint_manager = CheckpointManager(analysis_id=analysis_id)
        step2_checkpoint = checkpoint_manager.load_step_2()
        
        if not step2_checkpoint:
            raise HTTPException(status_code=400, detail="Step 2 checkpoint not found. Please run Step 2 first.")
        
        frames_3d_keypoints = step2_checkpoint.get('frames_3d_keypoints', [])
        step1_checkpoint = checkpoint_manager.load_step_1()
        frame_timestamps = step1_checkpoint.get('frame_timestamps', []) if step1_checkpoint else []
        
        if not frames_3d_keypoints:
            raise HTTPException(status_code=400, detail="Step 2 checkpoint has no 3D keypoints")
        
        logger.info(f"[TEST-{request_id}] Loaded Step 2 checkpoint: {len(frames_3d_keypoints)} frames")
        
        # Update status
        await db_service.update_analysis(analysis_id, {
            'status': 'testing',
            'current_step': 'metrics_calculation',
            'step_progress': 0,
            'step_message': 'Executing Step 3: Gait Metrics Calculation...'
        })
        
        # Get gait analysis service
        gait_service = get_gait_analysis_service()
        if not gait_service:
            raise HTTPException(status_code=503, detail="Gait analysis service not available")
        
        # Set analysis_id for checkpoint management
        gait_service._current_analysis_id = analysis_id
        
        # Execute Step 3 only
        logger.info(f"[TEST-{request_id}] Starting Step 3 processing...")
        
        # Convert 3D keypoints from checkpoint (lists) back to numpy arrays if needed
        import numpy as np
        frames_3d_keypoints_np = [
            np.array([[kp[0], kp[1], kp[2] if len(kp) > 2 else 0.0] for kp in frame], dtype=np.float32)
            if frame else []
            for frame in frames_3d_keypoints
        ]
        
        metrics = gait_service._calculate_gait_metrics(
            frames_3d_keypoints_np,
            frame_timestamps,
            fps,
            reference_length_mm
        )
        
        # Checkpoint is saved automatically in _calculate_gait_metrics (via checkpoint_manager.save_step_3)
        step3_checkpoint = checkpoint_manager.load_step_3()
        
        if step3_checkpoint:
            logger.info(f"[TEST-{request_id}] ✅ Step 3 checkpoint saved: {len(step3_checkpoint.get('metrics', {}))} metrics")
        else:
            logger.warning(f"[TEST-{request_id}] ⚠️ Step 3 checkpoint not found after processing")
        
        # Update status
        await db_service.update_analysis(analysis_id, {
            'status': 'testing',
            'current_step': 'metrics_calculation',
            'step_progress': 100,
            'step_message': f'Step 3 complete: {len(metrics)} metrics calculated'
        })
        
        return JSONResponse({
            "status": "success",
            "step": "step_3_metrics_calculation",
            "analysis_id": analysis_id,
            "message": "Step 3 completed successfully",
            "result": {
                "metrics_count": len(metrics),
                "sample_metrics": {
                    "cadence": metrics.get('cadence', 0),
                    "step_length": metrics.get('step_length', 0),
                    "walking_speed": metrics.get('walking_speed', 0)
                },
                "checkpoint_saved": step3_checkpoint is not None
            },
            "next_step_available": True
        })
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[TEST-{request_id}] Error executing Step 3: {e}", exc_info=True)
        await db_service.update_analysis(analysis_id, {
            'status': 'testing',
            'current_step': 'metrics_calculation',
            'step_progress': 0,
            'step_message': f'Step 3 failed: {str(e)}'
        })
        raise HTTPException(status_code=500, detail=f"Step 3 failed: {str(e)}")


@router.post("/step/4")
async def execute_step_4(
    analysis_id: str = Query(..., description="Analysis ID")
) -> JSONResponse:
    """
    Manually execute Step 4: Report Generation (requires Step 3 checkpoint)
    """
    request_id = str(uuid.uuid4())[:8]
    
    try:
        logger.info(f"[TEST-{request_id}] ========== EXECUTING STEP 4 ==========")
        logger.info(f"[TEST-{request_id}] Analysis ID: {analysis_id}")
        
        # Check for Step 3 checkpoint
        checkpoint_manager = CheckpointManager(analysis_id=analysis_id)
        step3_checkpoint = checkpoint_manager.load_step_3()
        
        if not step3_checkpoint:
            raise HTTPException(status_code=400, detail="Step 3 checkpoint not found. Please run Step 3 first.")
        
        metrics = step3_checkpoint.get('metrics', {})
        
        if not metrics:
            raise HTTPException(status_code=400, detail="Step 3 checkpoint has no metrics")
        
        logger.info(f"[TEST-{request_id}] Loaded Step 3 checkpoint: {len(metrics)} metrics")
        
        # Update status
        await db_service.update_analysis(analysis_id, {
            'status': 'testing',
            'current_step': 'report_generation',
            'step_progress': 0,
            'step_message': 'Executing Step 4: Report Generation...'
        })
        
        # Generate report
        report = {
            "status": "completed",
            "analysis_type": "testing_manual_steps",
            "metrics": metrics,
            "steps_completed": {
                "step_1_pose_estimation": True,
                "step_2_3d_lifting": True,
                "step_3_metrics_calculation": True,
                "step_4_report_generation": True
            },
            "generated_at": datetime.utcnow().isoformat()
        }
        
        # Update analysis with final report
        await db_service.update_analysis(analysis_id, {
            'status': 'completed',
            'current_step': 'report_generation',
            'step_progress': 100,
            'step_message': 'All steps complete - Report generated',
            'metrics': metrics
        })
        
        logger.info(f"[TEST-{request_id}] ✅ Step 4 complete: Report generated")
        
        return JSONResponse({
            "status": "success",
            "step": "step_4_report_generation",
            "analysis_id": analysis_id,
            "message": "Step 4 completed successfully - Report generated",
            "result": {
                "report": report,
                "metrics": metrics
            }
        })
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[TEST-{request_id}] Error executing Step 4: {e}", exc_info=True)
        await db_service.update_analysis(analysis_id, {
            'status': 'testing',
            'current_step': 'report_generation',
            'step_progress': 0,
            'step_message': f'Step 4 failed: {str(e)}'
        })
        raise HTTPException(status_code=500, detail=f"Step 4 failed: {str(e)}")


@router.get("/status/{analysis_id}")
async def get_test_status(analysis_id: str) -> JSONResponse:
    """
    Get status of test analysis and which steps are available
    """
    try:
        analysis = await db_service.get_analysis(analysis_id)
        if not analysis:
            raise HTTPException(status_code=404, detail="Analysis not found")
        
        checkpoint_manager = CheckpointManager(analysis_id=analysis_id)
        completed_steps = checkpoint_manager.get_completed_steps()
        
        return JSONResponse({
            "analysis_id": analysis_id,
            "status": analysis.get('status'),
            "current_step": analysis.get('current_step'),
            "step_progress": analysis.get('step_progress', 0),
            "step_message": analysis.get('step_message'),
            "steps_completed": completed_steps,
            "steps_available": {
                "step_1": True,  # Always available after upload
                "step_2": completed_steps.get('step_1_pose_estimation', False),
                "step_3": completed_steps.get('step_2_3d_lifting', False),
                "step_4": completed_steps.get('step_3_metrics_calculation', False)
            }
        })
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting test status: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get test status: {str(e)}")
