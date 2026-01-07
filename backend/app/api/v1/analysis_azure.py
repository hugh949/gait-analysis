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
from app.core.database_azure_sql import AzureSQLService

router = APIRouter()

# Initialize services
storage_service = AzureStorageService()
vision_service = AzureVisionService()
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
        
        # Upload to Azure Blob Storage
        logger.info(f"Uploading video to Blob Storage: {file.filename}")
        blob_name = f"{analysis_id}{file_ext}"
        video_url = await storage_service.upload_video(tmp_path, blob_name)
        
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
        # Clean up temp file
        if tmp_path and os.path.exists(tmp_path):
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
    """Background task to process video analysis using Azure services"""
    try:
        logger.info(f"Starting Azure-based analysis: {analysis_id}")
        
        # Update progress: Starting
        await db_service.update_analysis(analysis_id, {
            'status': 'processing',
            'current_step': 'pose_estimation',
            'step_progress': 10,
            'step_message': 'Initializing Azure Computer Vision...'
        })
        
        # Step 1: Pose Estimation (using Azure Computer Vision)
        await db_service.update_analysis(analysis_id, {
            'current_step': 'pose_estimation',
            'step_progress': 30,
            'step_message': 'Analyzing video frames...'
        })
        
        # Analyze video using Azure Computer Vision
        async def progress_callback(progress_pct: int, message: str):
            await db_service.update_analysis(analysis_id, {
                'current_step': 'pose_estimation',
                'step_progress': 30 + int(progress_pct * 0.3),
                'step_message': message
            })
        
        analysis_result = await vision_service.analyze_video(
            video_url,
            progress_callback
        )
        
        await db_service.update_analysis(analysis_id, {
            'current_step': '3d_lifting',
            'step_progress': 60,
            'step_message': 'Processing 3D analysis...'
        })
        
        # Step 2: 3D Lifting (simplified - using Azure results)
        await db_service.update_analysis(analysis_id, {
            'current_step': 'metrics_calculation',
            'step_progress': 70,
            'step_message': 'Calculating gait metrics...'
        })
        
        # Step 3: Metrics Calculation
        metrics = analysis_result.get('metrics', {})
        
        await db_service.update_analysis(analysis_id, {
            'current_step': 'report_generation',
            'step_progress': 90,
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
    
    except Exception as e:
        logger.error(f"Error processing analysis {analysis_id}: {e}", exc_info=True)
        await db_service.update_analysis(analysis_id, {
            'status': 'failed',
            'step_message': f'Analysis failed: {str(e)}'
        })


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


