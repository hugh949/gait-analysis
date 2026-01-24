"""
MINIMAL WORKING UPLOAD ENDPOINT - Based on FastAPI best practices
This is a simplified version to diagnose the 500 error
"""
from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse
from typing import Optional
from loguru import logger
import tempfile
import os
import uuid
from datetime import datetime

router = APIRouter()

@router.post("/upload-simple")
async def upload_video_simple(
    file: UploadFile = File(...)
) -> JSONResponse:
    """
    MINIMAL upload endpoint - just save file and return success
    Based on FastAPI official examples
    """
    request_id = str(uuid.uuid4())[:8]
    
    try:
        logger.info(f"[{request_id}] Simple upload started - filename: {file.filename}")
        
        # Validate file exists
        if not file.filename:
            raise HTTPException(status_code=400, detail="No filename provided")
        
        # Create temp file
        file_ext = os.path.splitext(file.filename)[1] or '.mp4'
        tmp_file = tempfile.NamedTemporaryFile(delete=False, suffix=file_ext)
        tmp_path = tmp_file.name
        tmp_file.close()
        
        logger.info(f"[{request_id}] Temp file created: {tmp_path}")
        
        # Read and save file - use simple pattern from FastAPI docs
        file_size = 0
        with open(tmp_path, 'wb') as f:
            while chunk := await file.read(1024 * 1024):  # 1MB chunks
                f.write(chunk)
                file_size += len(chunk)
        
        logger.info(f"[{request_id}] File saved: {file_size} bytes")
        
        # Return success
        return JSONResponse({
            "status": "success",
            "message": "File uploaded successfully",
            "filename": file.filename,
            "size": file_size,
            "temp_path": tmp_path,
            "request_id": request_id
        })
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[{request_id}] Upload error: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Upload failed: {str(e)}"
        )
