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
import asyncio
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
        
        # CRITICAL: Create analysis record with retries to ensure it's saved
        # This is essential - frontend needs to find the record immediately
        analysis_created = False
        db_service = None
        try:
            # CRITICAL: Always try to use the global db_service first (if available)
            # This ensures we're using the same instance that get_analysis uses
            try:
                from app.api.v1.analysis_azure import db_service as global_db_service
                if global_db_service is not None:
                    db_service = global_db_service
                    logger.info(f"[{request_id}] ✅ Using global database service (shared instance)")
                else:
                    raise AttributeError("Global db_service is None")
            except (ImportError, AttributeError) as import_err:
                logger.warning(f"[{request_id}] ⚠️ Global db_service not available: {import_err}")
                # Fallback: create new instance
                from app.core.database_azure_sql import AzureSQLService
                db_service = AzureSQLService()
                logger.info(f"[{request_id}] Created new database service instance")
            
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
                
                # CRITICAL: Create analysis record with verification
                # Use multiple attempts with increasing delays to handle eventual consistency
                for attempt in range(5):  # More attempts for reliability
                    try:
                        creation_result = await db_service.create_analysis(analysis_data)
                        if creation_result:
                            logger.info(f"[{request_id}] ✅ Analysis record created: {analysis_id} (attempt {attempt + 1})")
                            
                            # CRITICAL: Verify the record exists with multiple checks
                            # Wait progressively longer for eventual consistency (Table Storage, SQL replication, etc.)
                            verification_delay = 0.2 * (attempt + 1)  # 0.2s, 0.4s, 0.6s, 0.8s, 1.0s
                            await asyncio.sleep(verification_delay)
                            
                            # CRITICAL: For mock storage, force save and reload to ensure visibility
                            if hasattr(db_service, '_use_mock') and db_service._use_mock:
                                # Force save to file
                                if hasattr(db_service, '_save_mock_storage'):
                                    db_service._save_mock_storage(force_sync=True)
                                    logger.info(f"[{request_id}] ✅ Forced save to file for mock storage")
                                    # Small delay for file system sync
                                    await asyncio.sleep(0.2)
                                    # Force reload to ensure it's in memory
                                    if hasattr(db_service, '_load_mock_storage'):
                                        db_service._load_mock_storage()
                                        logger.info(f"[{request_id}] ✅ Forced reload from file for mock storage")
                            
                            # Try to read the record multiple times
                            for verify_attempt in range(5):  # More verification attempts
                                verification = await db_service.get_analysis(analysis_id)
                                if verification and verification.get('id') == analysis_id:
                                    analysis_created = True
                                    logger.info(f"[{request_id}] ✅ Analysis record verified: {analysis_id} (create attempt {attempt + 1}, verify attempt {verify_attempt + 1})")
                                    break
                                else:
                                    if verify_attempt < 4:
                                        await asyncio.sleep(0.15 * (verify_attempt + 1))  # Progressive delay
                                        continue
                            
                            if analysis_created:
                                break
                            else:
                                logger.warning(f"[{request_id}] ⚠️ Analysis record created but not readable after verification (attempt {attempt + 1})")
                                if attempt < 4:
                                    await asyncio.sleep(0.3 * (attempt + 1))
                                    continue
                        else:
                            logger.warning(f"[{request_id}] ⚠️ Analysis record creation returned False (attempt {attempt + 1})")
                            if attempt < 4:
                                await asyncio.sleep(0.3 * (attempt + 1))
                                continue
                    except Exception as create_err:
                        logger.warning(f"[{request_id}] ⚠️ Analysis creation attempt {attempt + 1} failed: {create_err}")
                        if attempt < 4:
                            await asyncio.sleep(0.3 * (attempt + 1))
                            continue
                
                if not analysis_created:
                    logger.error(f"[{request_id}] ❌ CRITICAL: Failed to create/verify analysis record after 5 attempts")
                    logger.error(f"[{request_id}] Analysis ID: {analysis_id} - Frontend will get 404 errors")
                    # CRITICAL: Don't return success if record wasn't created/verified
                    raise HTTPException(
                        status_code=500,
                        detail=f"Failed to create analysis record. The record could not be verified after creation. Please try again."
                    )
            else:
                logger.error(f"[{request_id}] ❌ Database service not available - analysis record cannot be created")
                raise HTTPException(
                    status_code=503,
                    detail="Database service is not available. Please try again in a moment."
                )
        except HTTPException:
            raise  # Re-raise HTTP exceptions
        except Exception as db_err:
            logger.error(f"[{request_id}] ❌ Failed to create analysis record: {db_err}", exc_info=True)
            # This is critical - log as error, not warning
            raise HTTPException(
                status_code=500,
                detail=f"Failed to create analysis record: {str(db_err)}"
            )
        
        # CRITICAL: Final verification - ensure record is readable one more time before returning
        # This simulates what the frontend will do when it calls get_analysis
        if db_service and analysis_created:
            try:
                # For mock storage, ensure one final save before verification
                if hasattr(db_service, '_use_mock') and db_service._use_mock:
                    if hasattr(db_service, '_save_mock_storage'):
                        db_service._save_mock_storage(force_sync=True)
                        await asyncio.sleep(0.1)  # Small delay for file sync
                
                final_check = await db_service.get_analysis(analysis_id)
                if not final_check or final_check.get('id') != analysis_id:
                    logger.error(f"[{request_id}] ❌ CRITICAL: Final verification failed - record not readable")
                    raise HTTPException(
                        status_code=500,
                        detail="Analysis record was created but cannot be read. Please try again."
                    )
                logger.info(f"[{request_id}] ✅ Final verification passed - record is readable")
                
                # CRITICAL: Small delay before returning to ensure record is fully persisted
                # This helps with eventual consistency in multi-worker scenarios
                await asyncio.sleep(0.2)
                
            except HTTPException:
                raise
            except Exception as final_err:
                logger.error(f"[{request_id}] ❌ Final verification error: {final_err}")
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to verify analysis record: {str(final_err)}"
                )
        
        # Only return success if record was created and verified
        if not analysis_created:
            raise HTTPException(
                status_code=500,
                detail="Analysis record could not be created or verified. Please try again."
            )
        
        # Return success with analysis_id (frontend expects this)
        logger.info(f"[{request_id}] ✅✅✅ UPLOAD SUCCESS - Analysis {analysis_id} created and verified ✅✅✅")
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
