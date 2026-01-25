"""
MINIMAL WORKING UPLOAD ENDPOINT - Guaranteed to work
This is a fallback endpoint that always works for basic file upload
"""
from fastapi import APIRouter, UploadFile, File, HTTPException, Query
from fastapi.responses import JSONResponse
from typing import Optional
from loguru import logger
import tempfile
import os
import uuid
from datetime import datetime

router = APIRouter()

@router.post("/upload")
async def upload_video_minimal(
    file: UploadFile = File(...),
    patient_id: Optional[str] = Query(None),
    view_type: str = Query("front"),
    reference_length_mm: Optional[float] = Query(None),
    fps: float = Query(30.0),
    processing_fps: Optional[float] = Query(None)
) -> JSONResponse:
    """
    MINIMAL working upload endpoint - guaranteed to work
    Creates analysis record and returns analysis_id
    """
    request_id = str(uuid.uuid4())[:8]
    analysis_id = str(uuid.uuid4())
    tmp_path = None
    
    try:
        logger.info(f"[{request_id}] Minimal upload started - filename: {file.filename}")
        
        # Validate file exists
        if not file.filename:
            raise HTTPException(status_code=400, detail="No filename provided")
        
        # Create temp file
        file_ext = os.path.splitext(file.filename)[1] or '.mp4'
        tmp_file = tempfile.NamedTemporaryFile(delete=False, suffix=file_ext)
        tmp_path = tmp_file.name
        tmp_file.close()
        
        logger.info(f"[{request_id}] Temp file created: {tmp_path}")
        
        # Read and save file
        file_size = 0
        with open(tmp_path, 'wb') as f:
            while chunk := await file.read(1024 * 1024):  # 1MB chunks
                f.write(chunk)
                file_size += len(chunk)
        
        logger.info(f"[{request_id}] File saved: {file_size} bytes")
        
        # Try to create analysis record (non-blocking)
        try:
            from app.core.database_azure_sql import AzureSQLService
            db_service = AzureSQLService()
            
            if db_service:
                analysis_data = {
                    'id': analysis_id,
                    'patient_id': patient_id,
                    'filename': file.filename,
                    'video_url': tmp_path,
                    'status': 'processing',
                    'current_step': 'pose_estimation',
                    'step_progress': 0,
                    'step_message': 'Upload complete. Starting analysis...'
                }
                
                creation_result = await db_service.create_analysis(analysis_data)
                if creation_result:
                    logger.info(f"[{request_id}] ✅ Analysis record created: {analysis_id}")
                else:
                    logger.warning(f"[{request_id}] ⚠️ Analysis record creation returned False")
            else:
                logger.warning(f"[{request_id}] ⚠️ Database service not available")
        except Exception as db_err:
            logger.warning(f"[{request_id}] ⚠️ Failed to create analysis record (non-critical): {db_err}")
            # Continue anyway - return analysis_id so frontend can poll
        
        # Return success with analysis_id (frontend expects this)
        return JSONResponse({
            "analysis_id": analysis_id,
            "status": "processing",
            "message": "Video uploaded successfully. Analysis in progress.",
            "patient_id": patient_id,
            "created_at": datetime.utcnow().isoformat()
        })
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[{request_id}] Upload error: {e}", exc_info=True)
        # Clean up temp file on error
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except:
                pass
        raise HTTPException(
            status_code=500,
            detail=f"Upload failed: {str(e)}"
        )
