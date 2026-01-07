"""
Analysis API endpoints - Microsoft Native Architecture
Uses Azure Computer Vision, Blob Storage, and SQL Database
"""
from fastapi import APIRouter, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional
from loguru import logger
import tempfile
import os
from pathlib import Path
import uuid

from app.services.azure_storage import AzureStorageService
from app.services.azure_vision import AzureVisionService
from app.services.gait_analysis import GaitAnalysisService
from app.core.database_azure_sql import AzureSQLService

router = APIRouter()

# Initialize services
storage_service = AzureStorageService()
vision_service = AzureVisionService()
# Initialize gait analysis service lazily (only when needed)
# This avoids import errors if dependencies aren't available
_gait_analysis_service = None

def get_gait_analysis_service():
    """Get or create gait analysis service instance"""
    global _gait_analysis_service
    if _gait_analysis_service is None:
        try:
            _gait_analysis_service = GaitAnalysisService()
        except Exception as e:
            logger.warning(f"Failed to initialize GaitAnalysisService: {e}")
            _gait_analysis_service = None
    return _gait_analysis_service

db_service = AzureSQLService()


class AnalysisRequest(BaseModel):
    """Analysis request model"""
    patient_id: Optional[str] = None
    view_type: Optional[str] = "front"
    reference_length_mm: Optional[float] = None
    fps: Optional[float] = 30.0


class AnalysisResponse(BaseModel):
    """Analysis response model"""
    analysis_id: str
    status: str
    message: str


@router.post("/upload", response_model=AnalysisResponse)
async def upload_video(
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    patient_id: Optional[str] = None,
    view_type: str = "front",
    reference_length_mm: Optional[float] = None,
    fps: float = 30.0
):
    """
    Upload video for gait analysis using Azure native services
    
    Flow:
    1. Save uploaded file to Azure Blob Storage
    2. Store metadata in Azure SQL Database
    3. Process video using Azure Computer Vision (background)
    4. Update results in SQL Database
    """
    # Validate file
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")
    
    file_ext = Path(file.filename).suffix.lower()
    if file_ext not in ['.mp4', '.avi', '.mov', '.mkv']:
        raise HTTPException(
            status_code=400,
            detail="Unsupported file format. Supported: .mp4, .avi, .mov, .mkv"
        )
    
    # Save uploaded file temporarily
    tmp_path = None
    video_url = None
    try:
        # Create temp file
        tmp_file = tempfile.NamedTemporaryFile(delete=False, suffix=file_ext)
        tmp_path = tmp_file.name
        
        # Read file in chunks
        chunk_size = 1024 * 1024  # 1MB chunks
        total_size = 0
        while True:
            chunk = await file.read(chunk_size)
            if not chunk:
                break
            tmp_file.write(chunk)
            total_size += len(chunk)
        
        tmp_file.close()
        
        # Generate analysis ID
        analysis_id = str(uuid.uuid4())
        
        # Upload to Azure Blob Storage (or keep temp file in mock mode)
        logger.info(f"Uploading video to Blob Storage: {file.filename}")
        blob_name = f"{analysis_id}{file_ext}"
        video_url = await storage_service.upload_video(tmp_path, blob_name)
        
        # In mock mode, video_url will be "mock://..." - we need to use the temp file directly
        # Move temp file to a persistent location for background processing
        if video_url.startswith('mock://'):
            # Keep the temp file for processing (it will be cleaned up after analysis)
            # Store the temp path in the video_url field temporarily
            video_url = tmp_path
            logger.info(f"Mock mode: Using temp file directly: {video_url}")
        else:
            # Real storage - clean up temp file
            try:
                os.unlink(tmp_path)
            except:
                pass
            tmp_path = None  # Don't clean up in finally block
        
        # Store metadata in Azure SQL Database
        analysis_data = {
            'id': analysis_id,
            'patient_id': patient_id,
            'filename': file.filename,
            'video_url': video_url,
            'status': 'processing',
            'current_step': 'pose_estimation',
            'step_progress': 0,
            'step_message': 'Upload complete. Starting analysis...'
        }
        
        await db_service.create_analysis(analysis_data)
        logger.info(f"Created analysis record: {analysis_id}")
        
        # Process in background
        background_tasks.add_task(
            process_analysis_azure,
            analysis_id,
            video_url,
            patient_id,
            view_type,
            reference_length_mm,
            fps
        )
        
        return AnalysisResponse(
            analysis_id=analysis_id,
            status="processing",
            message="Video uploaded successfully. Analysis in progress."
        )
    
    except Exception as e:
        logger.error(f"Error uploading video: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error processing upload: {str(e)}")
    
    finally:
        # Clean up temp file only if it wasn't used for processing
        # (In mock mode, the temp file is passed to background task and cleaned up there)
        if tmp_path and os.path.exists(tmp_path) and video_url and not os.path.exists(video_url):
            # Only clean up if video_url is not the same as tmp_path (i.e., not mock mode)
            try:
                os.unlink(tmp_path)
            except:
                pass


async def process_analysis_azure(
    analysis_id: str,
    video_url: str,
    patient_id: Optional[str],
    view_type: str,
    reference_length_mm: Optional[float],
    fps: float
):
    """Background task to process video analysis using advanced gait analysis"""
    video_path = None
    try:
        logger.info(f"Starting advanced gait analysis: {analysis_id}")
        
        # Update progress: Starting
        await db_service.update_analysis(analysis_id, {
            'status': 'processing',
            'current_step': 'pose_estimation',
            'step_progress': 5,
            'step_message': 'Downloading video for analysis...'
        })
        
        # Get gait analysis service
        gait_service = get_gait_analysis_service()
        if not gait_service:
            error_msg = (
                "Gait analysis service is not available. "
                "Required dependencies (OpenCV, MediaPipe) may not be installed. "
                "Please check that opencv-python and mediapipe are installed in the Docker container."
            )
            logger.error(error_msg)
            raise ValueError(error_msg)
        
        # Download video from blob storage to temporary file
        if video_url.startswith('http') or video_url.startswith('https'):
            # Real blob storage URL - download it
            video_path = await gait_service.download_video_from_url(video_url)
        elif os.path.exists(video_url):
            # Local file path (used in mock mode or if file already exists)
            video_path = video_url
            logger.info(f"Using existing file: {video_path}")
        elif video_url.startswith('mock://'):
            # Mock mode - this shouldn't happen if we fixed the upload, but handle it
            raise ValueError("Mock storage mode: Video file was not properly saved. Please configure Azure Storage.")
        else:
            # Try to get video from blob storage by blob name
            blob_name = video_url.split('/')[-1] if '/' in video_url else video_url
            # Download from blob storage
            import tempfile
            video_path = tempfile.NamedTemporaryFile(delete=False, suffix='.mp4').name
            blob_data = await storage_service.download_blob(blob_name)
            if blob_data:
                with open(video_path, 'wb') as f:
                    f.write(blob_data)
            else:
                raise ValueError(f"Could not download video: {video_url}")
        
        logger.info(f"Video downloaded to: {video_path}")
        
        # Verify video file exists and is readable
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"Video file not found: {video_path}")
        
        if not os.access(video_path, os.R_OK):
            raise PermissionError(f"Video file is not readable: {video_path}")
        
        file_size = os.path.getsize(video_path)
        logger.info(f"Video file size: {file_size} bytes ({file_size / (1024*1024):.2f} MB)")
        
        if file_size == 0:
            raise ValueError(f"Video file is empty: {video_path}")
        
        # Progress callback that maps internal progress to UI steps
        async def progress_callback(progress_pct: int, message: str):
            """Map internal progress (0-100%) to UI steps (pose_estimation, 3d_lifting, metrics_calculation, report_generation)"""
            try:
                # Map progress to overall steps with clear boundaries
                if progress_pct <= 50:
                    # Pose estimation phase: 0-50% internal = 10-60% UI
                    step = 'pose_estimation'
                    mapped_progress = 10 + int(progress_pct * 1.0)  # 10% to 60%
                elif progress_pct < 75:
                    # 3D lifting phase: 50-75% internal = 60-75% UI
                    step = '3d_lifting'
                    mapped_progress = 60 + int((progress_pct - 50) * 0.6)  # 60% to 75%
                elif progress_pct < 95:
                    # Metrics calculation phase: 75-95% internal = 75-90% UI
                    step = 'metrics_calculation'
                    mapped_progress = 75 + int((progress_pct - 75) * 0.75)  # 75% to 90%
                else:
                    # Report generation phase: 95-100% internal = 90-100% UI
                    step = 'report_generation'
                    mapped_progress = 90 + int((progress_pct - 95) * 2.0)  # 90% to 100%
                
                logger.debug(f"Progress update: {step} {mapped_progress}% - {message}")
                await db_service.update_analysis(analysis_id, {
                    'current_step': step,
                    'step_progress': mapped_progress,
                    'step_message': message
                })
            except Exception as e:
                logger.error(f"Error updating progress: {e}", exc_info=True)
        
        # Analyze video using advanced gait analysis
        analysis_result = await gait_service.analyze_video(
            video_path,
            fps=fps,
            reference_length_mm=reference_length_mm,
            view_type=view_type,
            progress_callback=progress_callback
        )
        
        # Extract and format metrics
        raw_metrics = analysis_result.get('metrics', {})
        
        # Map to expected metric names
        metrics = {
            'cadence': raw_metrics.get('cadence', 0.0),
            'step_length': raw_metrics.get('step_length', 0.0),  # in mm
            'walking_speed': raw_metrics.get('walking_speed', 0.0),  # in mm/s
            'stride_length': raw_metrics.get('stride_length', 0.0),  # in mm
            'double_support_time': raw_metrics.get('double_support_time', 0.0),  # in seconds
            'swing_time': raw_metrics.get('swing_time', 0.0),  # in seconds
            'stance_time': raw_metrics.get('stance_time', 0.0),  # in seconds
        }
        
        await db_service.update_analysis(analysis_id, {
            'current_step': 'report_generation',
            'step_progress': 95,
            'step_message': 'Generating analysis report...'
        })
        
        # Step 4: Report Generation
        await db_service.update_analysis(analysis_id, {
            'status': 'completed',
            'current_step': 'report_generation',
            'step_progress': 100,
            'step_message': 'Analysis complete!',
            'metrics': metrics
        })
        
        logger.info(f"Analysis completed: {analysis_id}")
        logger.info(f"Metrics: {metrics}")
    
    except Exception as e:
        logger.error(f"Error processing analysis {analysis_id}: {e}", exc_info=True)
        await db_service.update_analysis(analysis_id, {
            'status': 'failed',
            'step_message': f'Analysis failed: {str(e)}'
        })
    
    finally:
        # Clean up temporary video file
        if video_path and os.path.exists(video_path) and video_path != video_url:
            try:
                os.unlink(video_path)
                logger.info(f"Cleaned up temporary video: {video_path}")
            except Exception as e:
                logger.warning(f"Failed to clean up temp file: {e}")


@router.get("/list")
async def list_analyses(limit: int = 50):
    """List all analyses, ordered by most recent first"""
    try:
        analyses = await db_service.list_analyses(limit=limit)
        return {"analyses": analyses}
    except Exception as e:
        logger.error(f"Error listing analyses: {e}")
        raise HTTPException(status_code=500, detail=f"Error retrieving analyses: {str(e)}")


@router.get("/{analysis_id}")
async def get_analysis(analysis_id: str):
    """Get analysis status and results"""
    try:
        analysis = await db_service.get_analysis(analysis_id)
        
        if not analysis:
            raise HTTPException(status_code=404, detail="Analysis not found")
        
        return analysis
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting analysis {analysis_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Error retrieving analysis: {str(e)}")


