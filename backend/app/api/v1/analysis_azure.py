"""
Analysis API endpoints - Microsoft Native Architecture
Uses Azure Computer Vision, Blob Storage, and SQL Database

Enhanced with:
- Strong type checking via Pydantic models
- Comprehensive error handling with custom exceptions
- Structured logging with context
- Input validation and sanitization
"""
from fastapi import APIRouter, UploadFile, File, HTTPException, BackgroundTasks, Request, Query, Path as PathParam
from fastapi.responses import JSONResponse
from typing import Optional
from loguru import logger
import tempfile
import os
from pathlib import Path
import uuid
import asyncio
from datetime import datetime
import traceback
import threading
import time

from app.services.azure_storage import AzureStorageService
from app.services.azure_vision import AzureVisionService
from app.services.gait_analysis import GaitAnalysisService
from app.core.database_azure_sql import AzureSQLService
from app.core.exceptions import (
    GaitAnalysisError, VideoProcessingError, PoseEstimationError,
    GaitMetricsError, ValidationError, StorageError, DatabaseError, 
    gait_error_to_http
)
from app.core.schemas import (
    VideoUploadRequest, AnalysisResponse, AnalysisDetailResponse,
    AnalysisListResponse, ErrorResponse, ViewType, AnalysisStatus
)

router = APIRouter()

# Initialize services with error handling
storage_service: Optional[AzureStorageService] = None
vision_service: Optional[AzureVisionService] = None
db_service: Optional[AzureSQLService] = None
_gait_analysis_service: Optional[GaitAnalysisService] = None

def initialize_services():
    """Initialize all services with proper error handling and logging"""
    global storage_service, vision_service, db_service
    
    try:
        storage_service = AzureStorageService()
        logger.info("✓ AzureStorageService initialized")
    except Exception as e:
        logger.error(f"Failed to initialize AzureStorageService: {e}", exc_info=True)
        storage_service = None
    
    try:
        vision_service = AzureVisionService()
        logger.info("✓ AzureVisionService initialized")
    except Exception as e:
        logger.error(f"Failed to initialize AzureVisionService: {e}", exc_info=True)
        vision_service = None
    
    try:
        db_service = AzureSQLService()
        logger.info("✓ AzureSQLService initialized")
    except Exception as e:
        logger.error(f"Failed to initialize AzureSQLService: {e}", exc_info=True)
        # Don't raise - allow app to start, database will be None and handled gracefully
        # This prevents the entire app from failing to start if database has issues
        db_service = None
        logger.warning("Database service unavailable - app will continue but database operations will fail")

# Initialize services at module load
# CRITICAL: Don't raise on failure - allow app to start even if services fail
# Services will be initialized lazily when needed
try:
    initialize_services()
except Exception as e:
    logger.critical(f"Critical service initialization failed: {e}", exc_info=True)
    # Don't raise - allow app to start, services will be None and handled gracefully
    # This prevents the entire app from failing to start if one service has issues
    logger.warning("App will continue to start, but some services may be unavailable")

def get_gait_analysis_service() -> Optional[GaitAnalysisService]:
    """Get or create gait analysis service instance with error handling"""
    global _gait_analysis_service
    if _gait_analysis_service is None:
        try:
            logger.info("🔧 Initializing GaitAnalysisService...")
            _gait_analysis_service = GaitAnalysisService()
            # CRITICAL: Service should always be created, even if MediaPipe fails
            # It will work in fallback mode
            if _gait_analysis_service:
                logger.info("✓ GaitAnalysisService initialized successfully (may be in fallback mode)")
            else:
                logger.error("❌ GaitAnalysisService initialization returned None - this should not happen")
                _gait_analysis_service = None
        except ImportError as e:
            logger.error(f"❌ Import error initializing GaitAnalysisService: {e}", exc_info=True)
            # Try to create service anyway - it might work in fallback mode
            try:
                logger.warning("⚠ Attempting to create GaitAnalysisService in fallback mode...")
                _gait_analysis_service = GaitAnalysisService()
                if _gait_analysis_service:
                    logger.info("✓ GaitAnalysisService created in fallback mode after import error")
            except Exception as e2:
                logger.error(f"❌ Failed to create GaitAnalysisService even in fallback mode: {e2}", exc_info=True)
                _gait_analysis_service = None
        except Exception as e:
            logger.error(f"❌ Failed to initialize GaitAnalysisService: {e}", exc_info=True)
            # Try to create service anyway - it might work in fallback mode
            try:
                logger.warning("⚠ Attempting to create GaitAnalysisService in fallback mode...")
                _gait_analysis_service = GaitAnalysisService()
                if _gait_analysis_service:
                    logger.info("✓ GaitAnalysisService created in fallback mode after error")
            except Exception as e2:
                logger.error(f"❌ Failed to create GaitAnalysisService even in fallback mode: {e2}", exc_info=True)
            _gait_analysis_service = None
    return _gait_analysis_service

# Validate db_service is initialized
if db_service is None:
    logger.critical("Database service not initialized - API will not function correctly")


@router.post(
    "/upload",
    response_model=AnalysisResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Validation error"},
        413: {"model": ErrorResponse, "description": "File too large"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
        503: {"model": ErrorResponse, "description": "Service unavailable"}
    }
)
async def upload_video(
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    patient_id: Optional[str] = Query(None, max_length=100, description="Patient identifier"),
    view_type: ViewType = Query(ViewType.FRONT, description="Camera view type"),
    reference_length_mm: Optional[float] = Query(None, gt=0, le=10000, description="Reference length in mm"),
    fps: float = Query(30.0, gt=0, le=120, description="Video frames per second")
) -> AnalysisResponse:
    """
    Upload video for gait analysis using Azure native services
    
    Flow:
    1. Validate and save uploaded file
    2. Store metadata in Azure SQL Database
    3. Process video using advanced gait analysis (background)
    4. Update results in SQL Database
    
    Args:
        file: Video file to upload (required)
        patient_id: Optional patient identifier
        view_type: Camera view type (front, side, back)
        reference_length_mm: Reference length for scale calibration
        fps: Video frames per second
        
    Returns:
        AnalysisResponse with analysis_id and status
        
    Raises:
        HTTPException: On validation errors or service failures
    """
    # Structured logging with request context
    request_id = str(uuid.uuid4())[:8]
    upload_request_start = time.time()
    
    # CRITICAL: Log upload start immediately to track if request reaches server
    logger.info(
        f"[{request_id}] ========== UPLOAD REQUEST RECEIVED ==========",
        extra={
            "request_id": request_id,
            "filename": file.filename if file else None,
            "content_type": request.headers.get("content-type"),
            "content_length": request.headers.get("content-length"),
            "patient_id": patient_id,
            "view_type": view_type,
            "fps": fps,
            "timestamp": datetime.utcnow().isoformat()
        }
    )
    
    # Log estimated file size from Content-Length header if available
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            estimated_size_mb = int(content_length) / (1024 * 1024)
            logger.info(f"[{request_id}] Estimated file size from Content-Length: {estimated_size_mb:.2f}MB")
            if estimated_size_mb > 50:
                logger.warning(f"[{request_id}] ⚠️ Large file detected ({estimated_size_mb:.2f}MB). Azure timeout is 230s. Upload may timeout.")
        except (ValueError, TypeError):
            pass
    
    # Validate database service is available
    if db_service is None:
        logger.error(f"[{request_id}] Database service not available")
        raise HTTPException(
            status_code=503,
            detail={
                "error": "SERVICE_UNAVAILABLE",
                "message": "Database service is not available",
                "details": {}
            }
        )
    
    # Validate file is provided
    if not file or not file.filename:
        logger.error(f"[{request_id}] No file provided in upload request")
        raise ValidationError("No file provided", field="file")
    
    # Validate file extension
    file_ext = Path(file.filename).suffix.lower()
    SUPPORTED_FORMATS = ['.mp4', '.avi', '.mov', '.mkv']
    if file_ext not in SUPPORTED_FORMATS:
        logger.error(
            f"[{request_id}] Unsupported file format: {file_ext}",
            extra={"filename": file.filename, "extension": file_ext}
        )
        raise ValidationError(
            f"Unsupported file format: {file_ext}. Supported formats: {', '.join(SUPPORTED_FORMATS)}",
            field="file",
            details={"extension": file_ext, "supported": SUPPORTED_FORMATS}
        )
    
    # Validate file size (max 500MB)
    # CRITICAL: Azure App Service has a 230-second (3.8 minute) request timeout
    # For files larger than ~50MB, upload may timeout
    # Consider implementing chunked uploads or direct blob storage uploads for larger files
    MAX_FILE_SIZE = 500 * 1024 * 1024  # 500MB
    MAX_RECOMMENDED_SIZE = 50 * 1024 * 1024  # 50MB - recommended max to avoid timeout
    file_size = 0
    tmp_path: Optional[str] = None
    video_url: Optional[str] = None
    
    try:
        # CRITICAL: Check file size early and warn if it might timeout
        # We can't check file.size directly for streaming uploads, but we can warn after first chunk
        upload_start_time = time.time()
        
        # Create temp file with proper error handling
        try:
            tmp_file = tempfile.NamedTemporaryFile(delete=False, suffix=file_ext)
            tmp_path = tmp_file.name
            logger.debug(f"[{request_id}] Created temp file: {tmp_path}")
        except OSError as e:
            logger.error(f"[{request_id}] Failed to create temp file: {e}", exc_info=True)
            raise StorageError("Failed to create temporary file for upload", details={"error": str(e)})
        
        # Read file in chunks with size validation
        # CRITICAL: Use smaller chunks for large files to prevent memory issues
        # This prevents worker crashes during large file uploads
        chunk_size = 256 * 1024  # 256KB chunks (further reduced to minimize memory pressure)
        chunk_count = 0
        last_log_time = time.time()
        try:
            while True:
                chunk = await file.read(chunk_size)
                if not chunk:
                    break
                file_size += len(chunk)
                chunk_count += 1
                
                # Write chunk immediately to reduce memory usage
                tmp_file.write(chunk)
                
                # Log progress more frequently for large files (every 5MB or every 5 seconds)
                current_time = time.time()
                if chunk_count % 20 == 0 or (current_time - last_log_time) >= 5.0:  # Every 20 chunks (~5MB) or every 5 seconds
                    elapsed = current_time - upload_start_time
                    upload_rate = (file_size / elapsed) / (1024 * 1024) if elapsed > 0 else 0  # MB/s
                    estimated_total_time = (file_size / upload_rate) if upload_rate > 0 else 0
                    logger.info(f"[{request_id}] Upload progress: {file_size / (1024*1024):.1f}MB read ({chunk_count} chunks, {elapsed:.1f}s elapsed, {upload_rate:.2f}MB/s, est. {estimated_total_time:.1f}s total)")
                    
                    # Warn if upload is taking too long (approaching 230s timeout)
                    if elapsed > 180:  # 3 minutes - getting close to 230s timeout
                        logger.warning(f"[{request_id}] ⚠️ Upload taking longer than expected ({elapsed:.1f}s). Azure timeout is 230s. File may timeout.")
                    
                    last_log_time = current_time
                
                # Check file size limit
                if file_size > MAX_FILE_SIZE:
                    tmp_file.close()
                    os.unlink(tmp_path)
                    logger.error(
                        f"[{request_id}] File too large: {file_size} bytes (max: {MAX_FILE_SIZE})",
                        extra={"file_size": file_size, "max_size": MAX_FILE_SIZE}
                    )
                    raise ValidationError(
                        f"File too large: {file_size / (1024*1024):.2f}MB. Maximum size: {MAX_FILE_SIZE / (1024*1024)}MB",
                        field="file",
                        details={"file_size": file_size, "max_size": MAX_FILE_SIZE}
                    )
                    
                    tmp_file.close()
                    upload_duration = time.time() - upload_start_time
                    upload_rate = (file_size / upload_duration) / (1024 * 1024) if upload_duration > 0 else 0  # MB/s
                    
                    logger.info(
                        f"[{request_id}] File uploaded successfully",
                        extra={
                            "filename": file.filename,
                            "size": file_size,
                            "size_mb": file_size / (1024*1024),
                            "path": tmp_path,
                            "upload_duration": upload_duration,
                            "upload_rate_mbps": upload_rate,
                            "chunks": chunk_count
                        }
                    )
                    
                    # CRITICAL: Warn if upload is approaching timeout
                    if upload_duration > 200:  # 200 seconds - very close to 230s timeout
                        logger.error(
                            f"[{request_id}] ⚠️ CRITICAL: Upload took {upload_duration:.1f}s (Azure timeout is 230s). "
                            f"File may have timed out. Size: {file_size / (1024*1024):.1f}MB"
                        )
                    elif upload_duration > 180:  # 3 minutes - getting close
                        logger.warning(
                            f"[{request_id}] ⚠️ Upload took {upload_duration:.1f}s (approaching 230s Azure timeout). "
                            f"File size: {file_size / (1024*1024):.1f}MB. "
                            f"Consider using smaller files (<50MB) to avoid timeout issues."
                        )
                    elif file_size > MAX_RECOMMENDED_SIZE:
                        logger.warning(
                            f"[{request_id}] ⚠️ Large file uploaded ({file_size / (1024*1024):.1f}MB). "
                            f"Upload took {upload_duration:.1f}s. "
                            f"Azure App Service has a 230-second request timeout. "
                            f"Consider using smaller files (<50MB) to avoid timeout issues."
                        )
        except ValidationError:
            raise  # Re-raise validation errors
        except Exception as e:
            tmp_file.close()
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except:
                    pass
            logger.error(f"[{request_id}] Error reading uploaded file: {e}", exc_info=True)
            raise VideoProcessingError("Failed to read uploaded file", details={"error": str(e)})
        
        # Validate file is not empty
        if file_size == 0:
            if tmp_path and os.path.exists(tmp_path):
                os.unlink(tmp_path)
            logger.error(f"[{request_id}] Empty file uploaded")
            raise ValidationError("Uploaded file is empty", field="file")
        
        # Generate analysis ID
        analysis_id = str(uuid.uuid4())
        logger.info(f"[{request_id}] Generated analysis ID: {analysis_id}")
        
        # Upload to Azure Blob Storage (or keep temp file in mock mode)
        try:
            if storage_service is None:
                logger.warning(f"[{request_id}] Storage service not available, using mock mode")
                video_url = tmp_path  # Use temp file directly in mock mode
            else:
        blob_name = f"{analysis_id}{file_ext}"
                logger.debug(f"[{request_id}] Uploading to blob storage: {blob_name}")
        video_url = await storage_service.upload_video(tmp_path, blob_name)
        
                # In mock mode, video_url will be "mock://..." - use temp file directly
                if video_url and video_url.startswith('mock://'):
            video_url = tmp_path
                    logger.info(f"[{request_id}] Mock mode: Using temp file directly")
                elif video_url:
            # Real storage - clean up temp file
                    try:
                        os.unlink(tmp_path)
                        tmp_path = None
                        logger.debug(f"[{request_id}] Cleaned up temp file after blob upload")
                    except OSError as e:
                        logger.warning(f"[{request_id}] Failed to clean up temp file: {e}")
        except Exception as e:
            logger.error(f"[{request_id}] Error uploading to storage: {e}", exc_info=True)
            if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except:
                pass
            raise StorageError("Failed to upload file to storage", details={"error": str(e)})
        
        # Store metadata in Azure SQL Database
        try:
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
        
            # Create analysis record - this will save to file and verify it's readable
            creation_success = await db_service.create_analysis(analysis_data)
            if not creation_success:
                logger.error(f"[{request_id}] Failed to create analysis record", extra={"analysis_id": analysis_id})
                raise DatabaseError("Failed to create analysis record", details={"analysis_id": analysis_id})
            
            logger.info(
                f"[{request_id}] Created analysis record",
                extra={"analysis_id": analysis_id, "patient_id": patient_id}
            )
            
            # CRITICAL: Verify the analysis is immediately readable before returning
            # This ensures the file is fully written and visible to other requests
            verification_attempts = 0
            max_verification_attempts = 5
            while verification_attempts < max_verification_attempts:
                try:
                    verification_analysis = await db_service.get_analysis(analysis_id)
                    if verification_analysis and verification_analysis.get('id') == analysis_id:
                        logger.info(f"[{request_id}] Verified analysis is immediately readable after creation")
                        break
                    else:
                        verification_attempts += 1
                        if verification_attempts < max_verification_attempts:
                            await asyncio.sleep(0.1)  # Wait 100ms and retry
                            continue
                        else:
                            logger.warning(f"[{request_id}] Analysis not immediately readable after creation, but continuing (file may sync shortly)")
                except Exception as e:
                    verification_attempts += 1
                    if verification_attempts < max_verification_attempts:
                        logger.debug(f"[{request_id}] Verification read failed (attempt {verification_attempts}), retrying: {e}")
                        await asyncio.sleep(0.1)
                        continue
                    else:
                        logger.warning(f"[{request_id}] Could not verify analysis after creation: {e}")
        except Exception as e:
            logger.error(f"[{request_id}] Error creating analysis record: {e}", exc_info=True)
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except:
                    pass
            raise DatabaseError("Failed to create analysis record", details={"error": str(e)})
        
        # Process in background
        try:
            # Convert ViewType enum to string if needed
            view_type_str = view_type.value if isinstance(view_type, ViewType) else str(view_type)
            
            # CRITICAL: Start keep-alive heartbeat IMMEDIATELY after scheduling
            # This ensures the analysis stays alive even before processing starts
            # This is especially important in multi-worker environments
            # NOTE: This task runs independently and will continue even after request completes
            async def immediate_keepalive():
                """Immediate keep-alive that starts right after analysis creation"""
                keepalive_count = 0
                logger.info(f"[{request_id}] 🔄 IMMEDIATE KEEP-ALIVE STARTED for analysis {analysis_id}")
                try:
                    # Start with very frequent updates (every 2 seconds) for first 30 seconds
                    # Then switch to every 5 seconds
                    while True:
                        sleep_time = 2 if keepalive_count < 15 else 5
                        await asyncio.sleep(sleep_time)
                        keepalive_count += 1
                        try:
                            # Verify and update analysis to keep it alive
                            logger.info(f"[{request_id}] 🔄 Keep-alive heartbeat #{keepalive_count} - checking analysis {analysis_id}")
                            current_analysis = await db_service.get_analysis(analysis_id)
                            if current_analysis:
                                logger.info(f"[{request_id}] 🔄 Keep-alive: Analysis {analysis_id} found - updating to keep alive (status: {current_analysis.get('status')}, step: {current_analysis.get('current_step')}, progress: {current_analysis.get('step_progress')}%)")
                                await db_service.update_analysis(analysis_id, {
                                    'status': 'processing',
                                    'current_step': current_analysis.get('current_step', 'pose_estimation'),
                                    'step_progress': current_analysis.get('step_progress', 0),
                                    'step_message': current_analysis.get('step_message', 'Initializing analysis...')
                                })
                                logger.info(f"[{request_id}] ✅ Keep-alive: Analysis {analysis_id} updated successfully (heartbeat #{keepalive_count})")
                            else:
                                logger.warning(f"[{request_id}] ⚠️ Keep-alive: Analysis {analysis_id} NOT FOUND - recreating (heartbeat #{keepalive_count})")
                                await db_service.create_analysis({
                                    'id': analysis_id,
                                    'patient_id': patient_id,
                                    'filename': file.filename or 'unknown',
                                    'video_url': video_url,
                                    'status': 'processing',
                                    'current_step': 'pose_estimation',
                                    'step_progress': 0,
                                    'step_message': f'Analysis recreated by keep-alive (heartbeat #{keepalive_count})'
                                })
                                logger.info(f"[{request_id}] ✅ Keep-alive: Recreated analysis {analysis_id} (heartbeat #{keepalive_count})")
                        except Exception as keepalive_error:
                            logger.error(f"[{request_id}] ❌ Keep-alive error on heartbeat #{keepalive_count}: {keepalive_error}", exc_info=True)
                except asyncio.CancelledError:
                    logger.warning(f"[{request_id}] 🛑 Keep-alive CANCELLED after {keepalive_count} heartbeats - this should not happen!")
                    # Try to restart keep-alive if cancelled (shouldn't happen, but safety)
                    try:
                        logger.warning(f"[{request_id}] ⚠️ Keep-alive was cancelled - analysis may become invisible")
                        # Don't restart - just log the issue
                    except:
                        pass
                except Exception as e:
                    logger.error(f"[{request_id}] ❌ Keep-alive fatal error after {keepalive_count} heartbeats: {e}", exc_info=True)
                    # Log the error but don't try to continue - let the outer loop handle it
                    # The outer while True loop will continue if this exception is caught
            
            # Start immediate keep-alive task
            # CRITICAL: Create task in the event loop - it will run independently
            # The task will continue even after the request handler returns
            keepalive_task = asyncio.create_task(immediate_keepalive())
            logger.info(f"[{request_id}] ✅ Started immediate keep-alive task for analysis {analysis_id} (task ID: {id(keepalive_task)})")
            logger.info(f"[{request_id}] ✅ Keep-alive task is running: {not keepalive_task.done()}")
            logger.info(f"[{request_id}] ✅ Keep-alive task will continue running after request completes")
            
            # Schedule the actual processing task
            # CRITICAL: Wrap the processing function to add diagnostic logging
            async def wrapped_process_analysis():
                """Wrapper to add diagnostic logging when background task executes"""
                logger.error(f"[{request_id}] 🔧🔧🔧 BACKGROUND TASK WRAPPER CALLED 🔧🔧🔧")
                logger.error(f"[{request_id}] 🔧 About to call process_analysis_azure for {analysis_id}")
                logger.error(f"[{request_id}] 🔧 Current time: {datetime.utcnow().isoformat()}")
                logger.error(f"[{request_id}] 🔧 Process ID: {os.getpid()}")
                logger.error(f"[{request_id}] 🔧 Thread: {threading.current_thread().ident}, {threading.current_thread().name}")
                try:
                    await process_analysis_azure(
            analysis_id,
            video_url,
            patient_id,
                        view_type_str,
            reference_length_mm,
            fps
        )
                    logger.error(f"[{request_id}] 🔧✅ Background task completed successfully")
                except Exception as wrapper_error:
                    logger.error(f"[{request_id}] 🔧❌ Background task failed: {type(wrapper_error).__name__}: {wrapper_error}", exc_info=True)
                    raise
            
            logger.error(f"[{request_id}] 🔧🔧🔧 SCHEDULING BACKGROUND TASK 🔧🔧🔧")
            logger.error(f"[{request_id}] 🔧 Analysis ID: {analysis_id}")
            logger.error(f"[{request_id}] 🔧 About to call background_tasks.add_task")
            logger.error(f"[{request_id}] 🔧 background_tasks object: {background_tasks}")
            logger.error(f"[{request_id}] 🔧 background_tasks type: {type(background_tasks)}")
            
            background_tasks.add_task(wrapped_process_analysis)
            
            logger.error(f"[{request_id}] 🔧✅ background_tasks.add_task() called successfully")
            logger.info(f"[{request_id}] ✅ Background processing task scheduled for analysis {analysis_id}", extra={"analysis_id": analysis_id})
            logger.info(f"[{request_id}] ✅ Upload complete - analysis {analysis_id} should be visible immediately")
            logger.info(f"[{request_id}] ✅ Both keep-alive and processing tasks are now running")
        except Exception as e:
            logger.error(f"[{request_id}] Error scheduling background task: {e}", exc_info=True)
            # Update analysis status to failed
            try:
                await db_service.update_analysis(analysis_id, {
                    'status': 'failed',
                    'step_message': f'Failed to schedule analysis: {str(e)}'
                })
            except:
                pass
            raise VideoProcessingError("Failed to schedule video analysis", details={"error": str(e)})
        
        upload_total_duration = time.time() - upload_request_start
        logger.info(
            f"[{request_id}] ========== UPLOAD REQUEST COMPLETE ==========",
            extra={
                "request_id": request_id,
                "analysis_id": analysis_id,
                "total_duration": upload_total_duration,
                "file_size_mb": file_size / (1024*1024) if file_size > 0 else 0,
                "timestamp": datetime.utcnow().isoformat()
            }
        )
        
        # CRITICAL: Warn if total request time is approaching timeout
        if upload_total_duration > 200:
            logger.error(f"[{request_id}] ⚠️ CRITICAL: Total upload request took {upload_total_duration:.1f}s (Azure timeout: 230s). Response may not reach client.")
        elif upload_total_duration > 180:
            logger.warning(f"[{request_id}] ⚠️ Upload request took {upload_total_duration:.1f}s (approaching 230s Azure timeout)")
        
        return AnalysisResponse(
            analysis_id=analysis_id,
            status=AnalysisStatus.PROCESSING,
            message="Video uploaded successfully. Analysis in progress.",
            patient_id=patient_id,
            created_at=datetime.utcnow()
        )
    
    except (ValidationError, VideoProcessingError, StorageError, DatabaseError) as e:
        # Convert custom exceptions to HTTP exceptions
        logger.error(
            f"[{request_id}] Upload failed: {e.error_code} - {e.message}",
            extra={"error_code": e.error_code, "details": e.details},
            exc_info=True
        )
        raise gait_error_to_http(e)
    except HTTPException:
        raise  # Re-raise HTTP exceptions
    except Exception as e:
        # Catch-all for unexpected errors
        logger.error(
            f"[{request_id}] Unexpected error uploading video: {e}",
            extra={"error_type": type(e).__name__},
            exc_info=True
        )
        raise HTTPException(
            status_code=500,
            detail={
                "error": "INTERNAL_SERVER_ERROR",
                "message": "An unexpected error occurred while processing the upload",
                "details": {"error_type": type(e).__name__}
            }
        )
    
    finally:
        # Clean up temp file only if it wasn't used for processing
        if tmp_path and os.path.exists(tmp_path) and video_url and not os.path.exists(video_url):
            # Only clean up if video_url is not the same as tmp_path (i.e., not mock mode)
            try:
                os.unlink(tmp_path)
                logger.debug(f"[{request_id}] Cleaned up unused temp file")
            except OSError as e:
                logger.warning(f"[{request_id}] Failed to clean up temp file in finally: {e}")


async def process_analysis_azure(
    analysis_id: str,
    video_url: str,
    patient_id: Optional[str],
    view_type: str,
    reference_length_mm: Optional[float],
    fps: float
) -> None:
    """
    Background task to process video analysis using advanced gait analysis
    
    Args:
        analysis_id: Unique analysis identifier
        video_url: URL or path to video file
        patient_id: Optional patient identifier
        view_type: Camera view type (front, side, back)
        reference_length_mm: Optional reference length for calibration
        fps: Video frames per second
        
    Raises:
        Various exceptions that are caught and logged
    """
    request_id = str(uuid.uuid4())[:8]
    video_path: Optional[str] = None
    
    # CRITICAL: Log immediately when function is called (before any try block)
    # This ensures we see if the background task actually starts
    import os
    import threading
    logger.error("=" * 80)
    logger.error(f"[{request_id}] ========== PROCESSING TASK FUNCTION CALLED ==========")
    logger.error(f"[{request_id}] Analysis ID: {analysis_id}")
    logger.error(f"[{request_id}] Video URL: {video_url}")
    logger.error(f"[{request_id}] Parameters: view_type={view_type}, fps={fps}, reference_length_mm={reference_length_mm}")
    logger.error(f"[{request_id}] Timestamp: {datetime.utcnow().isoformat()}")
    logger.error(f"[{request_id}] Process ID: {os.getpid()}")
    logger.error(f"[{request_id}] Thread ID: {threading.current_thread().ident}, Thread Name: {threading.current_thread().name}")
    logger.error(f"[{request_id}] db_service available: {db_service is not None}")
    logger.error(f"[{request_id}] db_service._use_mock: {db_service._use_mock if db_service else None}")
    logger.error("=" * 80)
    
    try:
        logger.info(
            f"[{request_id}] 🚀 PROCESSING TASK STARTED for analysis {analysis_id}",
            extra={
                "request_id": request_id,
                "analysis_id": analysis_id,
                "patient_id": patient_id,
                "view_type": view_type,
                "fps": fps
            }
        )
        logger.info(f"[{request_id}] 📋 Processing parameters: view_type={view_type}, fps={fps}, reference_length_mm={reference_length_mm}")
        
        # CRITICAL: Ensure analysis exists before starting processing
        # This prevents "Analysis not found" errors during processing
        analysis_exists = False
        for verify_attempt in range(5):
            try:
                existing_analysis = await db_service.get_analysis(analysis_id)
                if existing_analysis and existing_analysis.get('id') == analysis_id:
                    analysis_exists = True
                    logger.info(f"[{request_id}] Verified analysis exists before processing (attempt {verify_attempt + 1})")
                    break
            except Exception as e:
                logger.warning(f"[{request_id}] Error verifying analysis (attempt {verify_attempt + 1}): {e}")
                if verify_attempt < 4:
                    await asyncio.sleep(0.2 * (verify_attempt + 1))
                    continue
        
        if not analysis_exists:
            logger.error(f"[{request_id}] Analysis {analysis_id} not found before processing. Cannot proceed.")
            # Try to create a minimal analysis record to prevent complete failure
            try:
                await db_service.create_analysis({
                    'id': analysis_id,
                    'patient_id': patient_id,
                    'filename': 'unknown',
                    'video_url': video_url,
                    'status': 'processing',
                    'current_step': 'pose_estimation',
                    'step_progress': 0,
                    'step_message': 'Analysis record recreated - processing starting...'
                })
                logger.warning(f"[{request_id}] Recreated analysis record - proceeding with processing")
            except Exception as recreate_error:
                logger.error(f"[{request_id}] Failed to recreate analysis record: {recreate_error}")
                # Still continue - we'll try to update it during processing
        
        # Update progress: Starting - with retry logic
        for retry in range(5):
            try:
        await db_service.update_analysis(analysis_id, {
            'status': 'processing',
            'current_step': 'pose_estimation',
            'step_progress': 5,
            'step_message': 'Downloading video for analysis...'
        })
                break  # Success
            except Exception as e:
                if retry < 4:
                    logger.warning(f"[{request_id}] Failed to update analysis status (attempt {retry + 1}/5): {e}. Retrying...")
                    await asyncio.sleep(0.2 * (retry + 1))
                    continue
                else:
                    logger.error(
                        f"[{request_id}] Failed to update analysis status after 5 attempts: {e}",
                        extra={"analysis_id": analysis_id},
                        exc_info=True
                    )
                    # Continue anyway - not critical, but log the error
        
        # Get gait analysis service with error handling
        try:
        gait_service = get_gait_analysis_service()
        if not gait_service:
            error_msg = (
                "Gait analysis service is not available. "
                    "Required dependencies (OpenCV, MediaPipe) may not be installed."
                )
                logger.error(
                    f"[{request_id}] {error_msg}",
                    extra={"analysis_id": analysis_id}
                )
                raise VideoProcessingError(
                    error_msg,
                    details={"analysis_id": analysis_id, "service": "GaitAnalysisService"}
                )
        except VideoProcessingError:
            raise
        except Exception as e:
            logger.error(
                f"[{request_id}] Error getting gait analysis service: {e}",
                extra={"analysis_id": analysis_id},
                exc_info=True
            )
            raise VideoProcessingError(
                "Failed to initialize gait analysis service",
                details={"error": str(e), "analysis_id": analysis_id}
            )
        
        # Download video from blob storage to temporary file with comprehensive error handling
        try:
        if video_url.startswith('http') or video_url.startswith('https'):
            # Real blob storage URL - download it
                logger.debug(f"[{request_id}] Downloading video from URL: {video_url}")
            video_path = await gait_service.download_video_from_url(video_url)
        elif os.path.exists(video_url):
            # Local file path (used in mock mode or if file already exists)
            video_path = video_url
                logger.info(
                    f"[{request_id}] Using existing file",
                    extra={"video_path": video_path, "analysis_id": analysis_id}
                )
        elif video_url.startswith('mock://'):
            # Mock mode - this shouldn't happen if we fixed the upload, but handle it
                raise StorageError(
                    "Mock storage mode: Video file was not properly saved",
                    details={"video_url": video_url, "analysis_id": analysis_id}
                )
        else:
            # Try to get video from blob storage by blob name
                if storage_service is None:
                    raise StorageError(
                        "Storage service not available and video URL is not a local file",
                        details={"video_url": video_url, "analysis_id": analysis_id}
                    )
                
            blob_name = video_url.split('/')[-1] if '/' in video_url else video_url
                logger.debug(f"[{request_id}] Downloading blob: {blob_name}")
                
            import tempfile
            video_path = tempfile.NamedTemporaryFile(delete=False, suffix='.mp4').name
            blob_data = await storage_service.download_blob(blob_name)
                
                if not blob_data:
                    raise StorageError(
                        f"Could not download video blob: {blob_name}",
                        details={"blob_name": blob_name, "analysis_id": analysis_id}
                    )
                
                try:
                with open(video_path, 'wb') as f:
                    f.write(blob_data)
                        logger.debug(f"[{request_id}] Blob downloaded and saved: {video_path}")
                except OSError as e:
                    raise StorageError(
                        f"Failed to save downloaded blob to file: {e}",
                        details={"video_path": video_path, "analysis_id": analysis_id}
                    )
        except (StorageError, VideoProcessingError):
            raise  # Re-raise custom exceptions
        except Exception as e:
            logger.error(
                f"[{request_id}] Error downloading video: {e}",
                extra={"video_url": video_url, "analysis_id": analysis_id},
                exc_info=True
            )
            raise VideoProcessingError(
                "Failed to download video for processing",
                details={"error": str(e), "video_url": video_url, "analysis_id": analysis_id}
            )
        
        # Verify video file exists and is readable with detailed error messages
        if not os.path.exists(video_path):
            logger.error(
                f"[{request_id}] Video file not found",
                extra={"video_path": video_path, "analysis_id": analysis_id}
            )
            raise VideoProcessingError(
                f"Video file not found: {video_path}",
                details={"video_path": video_path, "analysis_id": analysis_id}
            )
        
        if not os.access(video_path, os.R_OK):
            logger.error(
                f"[{request_id}] Video file not readable",
                extra={"video_path": video_path, "analysis_id": analysis_id}
            )
            raise VideoProcessingError(
                f"Video file is not readable: {video_path}",
                details={"video_path": video_path, "analysis_id": analysis_id}
            )
        
        try:
        file_size = os.path.getsize(video_path)
        except OSError as e:
            logger.error(
                f"[{request_id}] Error getting file size: {e}",
                extra={"video_path": video_path, "analysis_id": analysis_id},
                exc_info=True
            )
            raise VideoProcessingError(
                f"Failed to get video file size: {e}",
                details={"video_path": video_path, "analysis_id": analysis_id}
            )
        
        logger.info(
            f"[{request_id}] Video file verified",
            extra={
                "video_path": video_path,
                "file_size": file_size,
                "file_size_mb": file_size / (1024*1024),
                "analysis_id": analysis_id
            }
        )
        
        if file_size == 0:
            logger.error(
                f"[{request_id}] Video file is empty",
                extra={"video_path": video_path, "analysis_id": analysis_id}
            )
            raise ValidationError(
                f"Video file is empty: {video_path}",
                field="video",
                details={"video_path": video_path, "analysis_id": analysis_id}
            )
        
        # CRITICAL: Use THREAD-BASED keep-alive that runs independently of async event loop
        # During CPU-intensive processing, async tasks are starved, so we need threads
        last_known_progress = {'step': 'pose_estimation', 'progress': 0, 'message': 'Starting analysis...'}
        heartbeat_stop_event = threading.Event()
        
        def thread_based_heartbeat():
            """Thread-based heartbeat that runs independently of async event loop
            CRITICAL: This thread MUST run continuously and cannot be blocked.
            It uses very frequent updates (every 0.05s) to ensure analysis is ALWAYS visible.
            """
            # CRITICAL: Wrap entire function in try-except to catch ANY errors, including startup errors
            try:
                heartbeat_count = 0
                thread_id = threading.current_thread().ident
                thread_name = threading.current_thread().name
                last_successful_update = time.time()
                
                # CRITICAL: Capture all variables from outer scope to ensure they're available
                # These are captured from the closure, but we verify they exist
                heartbeat_analysis_id = analysis_id
                heartbeat_request_id = request_id
                heartbeat_db_service = db_service
                heartbeat_patient_id = patient_id
                heartbeat_video_url = video_url
                heartbeat_last_progress = last_known_progress
                heartbeat_stop = heartbeat_stop_event
                
                logger.error(f"[{heartbeat_request_id}] 🔄🔄🔄 THREAD-BASED HEARTBEAT STARTED 🔄🔄🔄")
                logger.error(f"[{heartbeat_request_id}] 🔄 Analysis ID: {heartbeat_analysis_id}")
                logger.error(f"[{heartbeat_request_id}] 🔄 Thread ID: {thread_id}, Thread Name: {thread_name}")
                logger.error(f"[{heartbeat_request_id}] 🔄 Process ID: {os.getpid()}")
                logger.error(f"[{heartbeat_request_id}] 🔄 db_service available: {heartbeat_db_service is not None}")
                logger.error(f"[{heartbeat_request_id}] 🔄 db_service._use_mock: {heartbeat_db_service._use_mock if heartbeat_db_service else None}")
                logger.error(f"[{heartbeat_request_id}] 🔄 Analysis in memory: {heartbeat_analysis_id in heartbeat_db_service._mock_storage if heartbeat_db_service else False}")
                logger.error(f"[{heartbeat_request_id}] 🔄 Running with ULTRA-MAXIMUM-FREQUENCY updates (every 0.05s = 20 times/second)")
                
                # CRITICAL: Verify analysis exists before starting heartbeat loop
                if heartbeat_db_service and heartbeat_db_service._use_mock:
                    if heartbeat_analysis_id not in heartbeat_db_service._mock_storage:
                        logger.error(f"[{heartbeat_request_id}] ❌❌❌ CRITICAL: Analysis {heartbeat_analysis_id} NOT in memory when heartbeat starts! ❌❌❌")
                        logger.error(f"[{heartbeat_request_id}] ❌ Memory storage size: {len(heartbeat_db_service._mock_storage)}")
                        logger.error(f"[{heartbeat_request_id}] ❌ Memory analysis IDs: {list(heartbeat_db_service._mock_storage.keys())}")
                        # Try to reload from file
                        heartbeat_db_service._load_mock_storage()
                        if heartbeat_analysis_id in heartbeat_db_service._mock_storage:
                            logger.error(f"[{heartbeat_request_id}] ✅ Analysis found after reload from file")
                        else:
                            logger.error(f"[{heartbeat_request_id}] ❌ Analysis still not found after reload - will recreate in first heartbeat")
                    else:
                        logger.error(f"[{heartbeat_request_id}] ✅ Analysis {heartbeat_analysis_id} found in memory when heartbeat starts")
                
                while not heartbeat_stop.is_set():
                    # CRITICAL: ULTRA-FREQUENT updates during long processing
                    # Every 0.05 seconds (20 times per second) for MAXIMUM persistence
                    # This ensures the analysis is ALWAYS visible across workers during CPU-intensive processing
                    # Even if one update is slow, the next one will happen very soon
                    # STABILITY MODE: Increased frequency to 20Hz for maximum reliability
                    sleep_time = 0.05  # Always 0.05 seconds - ULTRA-MAXIMUM frequency (20 updates per second)
                    heartbeat_stop.wait(sleep_time)
                    if heartbeat_stop.is_set():
                        logger.info(f"[{heartbeat_request_id}] 🔄 THREAD HEARTBEAT: Stop event set, exiting loop (heartbeat count: {heartbeat_count})")
                        break
                    
                    heartbeat_count += 1
                    current_time = time.time()
                    time_since_last_success = current_time - last_successful_update
                    
                    # DIAGNOSTIC: Log EVERY heartbeat for maximum visibility
                    import os
                    import threading
                    process_id = os.getpid()
                    current_thread_id = threading.current_thread().ident
                    logger.error(f"[{heartbeat_request_id}] 🔄🔄🔄 HEARTBEAT #{heartbeat_count} DIAGNOSTIC 🔄🔄🔄")
                    logger.error(f"[{heartbeat_request_id}] 🔄 Process ID: {process_id}, Thread ID: {current_thread_id}")
                    logger.error(f"[{heartbeat_request_id}] 🔄 Time since last success: {time_since_last_success:.3f}s")
                    logger.error(f"[{heartbeat_request_id}] 🔄 Analysis ID: {heartbeat_analysis_id}")
                    logger.error(f"[{heartbeat_request_id}] 🔄 Last known progress: {heartbeat_last_progress}")
                    
                    try:
                        # CRITICAL: Use sync method to update analysis (works from threads)
                        # Check if analysis exists in memory first
                        if heartbeat_db_service and heartbeat_db_service._use_mock:
                            # DIAGNOSTIC: Log memory state before check
                            logger.error(f"[{heartbeat_request_id}] 🔄 HEARTBEAT #{heartbeat_count}: Checking analysis in memory...")
                            logger.error(f"[{heartbeat_request_id}] 🔄 Memory storage size: {len(heartbeat_db_service._mock_storage)}")
                            logger.error(f"[{heartbeat_request_id}] 🔄 Memory analysis IDs: {list(heartbeat_db_service._mock_storage.keys())}")
                            logger.error(f"[{heartbeat_request_id}] 🔄 Analysis in memory: {heartbeat_analysis_id in heartbeat_db_service._mock_storage}")
                            
                            # CRITICAL: Always ensure analysis exists - recreate if missing
                            if heartbeat_analysis_id not in heartbeat_db_service._mock_storage:
                                # Analysis not in memory - IMMEDIATELY recreate it
                                logger.warning(f"[{request_id}] ⚠️ THREAD HEARTBEAT #{heartbeat_count}: Analysis {analysis_id} NOT in memory - RECREATING IMMEDIATELY")
                                from datetime import datetime
                                db_service._mock_storage[analysis_id] = {
                                    'id': analysis_id,
                                    'patient_id': patient_id,
                                    'filename': 'unknown',
                                    'video_url': video_url,
                                    'status': 'processing',
                                    'current_step': last_known_progress['step'],
                                    'step_progress': last_known_progress['progress'],
                                    'step_message': f"{last_known_progress['message']} (recreated by heartbeat #{heartbeat_count})",
                                    'metrics': {},
                                    'created_at': datetime.now().isoformat(),
                                    'updated_at': datetime.now().isoformat()
                                }
                                # Force immediate save
                                try:
                                    db_service._save_mock_storage(force_sync=True)
                                    logger.info(f"[{request_id}] ✅ THREAD HEARTBEAT #{heartbeat_count}: Recreated and saved analysis {analysis_id}")
                                    last_successful_update = time.time()
                                except Exception as recreate_error:
                                    logger.error(f"[{request_id}] ❌ THREAD HEARTBEAT #{heartbeat_count}: Failed to save recreated analysis: {recreate_error}")
                            
                            # Analysis exists in memory - update it
                            step = heartbeat_last_progress['step']
                            progress = heartbeat_last_progress['progress']
                            message = heartbeat_last_progress['message']
                            
                            # Use sync update method (works from threads)
                            # OPTIMIZED: This now batches file writes, so it's much faster
                            start_time = time.time()
                            try:
                                update_success = heartbeat_db_service.update_analysis_sync(heartbeat_analysis_id, {
                                    'status': 'processing',
                                    'current_step': step,
                                    'step_progress': progress,
                                    'step_message': message
                                })
                                update_duration = time.time() - start_time
                                
                                if update_success:
                                    last_successful_update = time.time()
                                    # DIAGNOSTIC: Log EVERY successful update
                                    logger.error(f"[{request_id}] ✅✅✅ HEARTBEAT #{heartbeat_count} UPDATE SUCCESS ✅✅✅")
                                    logger.error(f"[{request_id}] ✅ Analysis {analysis_id} updated: {step} {progress}%")
                                    logger.error(f"[{request_id}] ✅ Update duration: {update_duration:.3f}s")
                                    logger.error(f"[{request_id}] ✅ Analysis still in memory: {analysis_id in db_service._mock_storage}")
                                    
                                    # Verify analysis still exists after update
                                    if analysis_id not in db_service._mock_storage:
                                        logger.error(f"[{request_id}] ❌❌❌ CRITICAL: Analysis disappeared IMMEDIATELY after successful update! ❌❌❌")
                                        logger.error(f"[{request_id}] ❌ Memory storage size: {len(db_service._mock_storage)}")
                                        logger.error(f"[{request_id}] ❌ Memory analysis IDs: {list(db_service._mock_storage.keys())}")
                                        # Recreate immediately
                                        from datetime import datetime
                                        db_service._mock_storage[analysis_id] = {
                                            'id': analysis_id,
                                            'patient_id': patient_id,
                                            'filename': 'unknown',
                                            'video_url': video_url,
                                            'status': 'processing',
                                            'current_step': step,
                                            'step_progress': progress,
                                            'step_message': f"{message} (recreated after disappearance)",
                                            'metrics': {},
                                            'created_at': datetime.now().isoformat(),
                                            'updated_at': datetime.now().isoformat()
                                        }
                                        db_service._save_mock_storage(force_sync=True)
                                        logger.error(f"[{request_id}] ✅ THREAD HEARTBEAT #{heartbeat_count}: Recreated analysis after disappearance")
                                else:
                                    logger.error(f"[{request_id}] ❌❌❌ HEARTBEAT #{heartbeat_count} UPDATE FAILED ❌❌❌")
                                    logger.error(f"[{request_id}] ❌ Update returned False")
                                    logger.error(f"[{request_id}] ❌ Analysis in memory: {analysis_id in db_service._mock_storage}")
                                    
                                    # CRITICAL: Verify analysis still exists after update
                                    if analysis_id not in db_service._mock_storage:
                                        logger.error(f"[{request_id}] ❌ THREAD HEARTBEAT #{heartbeat_count}: CRITICAL - Analysis disappeared after update! Recreating...")
                                        # Recreate immediately
                                        from datetime import datetime
                                        db_service._mock_storage[analysis_id] = {
                                            'id': analysis_id,
                                            'patient_id': patient_id,
                                            'filename': 'unknown',
                                            'video_url': video_url,
                                            'status': 'processing',
                                            'current_step': step,
                                            'step_progress': progress,
                                            'step_message': f"{message} (recreated after disappearance)",
                                            'metrics': {},
                                            'created_at': datetime.now().isoformat(),
                                            'updated_at': datetime.now().isoformat()
                                        }
                                        db_service._save_mock_storage(force_sync=True)
                                        logger.error(f"[{request_id}] ✅ THREAD HEARTBEAT #{heartbeat_count}: Recreated analysis after disappearance")
                                    elif heartbeat_count % 10 == 0:  # Log every 10 heartbeats
                                        logger.warning(f"[{request_id}] ⚠️ THREAD HEARTBEAT #{heartbeat_count}: Update returned False")
                                
                                if update_duration > 0.3:
                                    logger.warning(f"[{request_id}] ⚠️ THREAD HEARTBEAT #{heartbeat_count}: Slow update took {update_duration:.2f}s (may impact persistence)")
                            except Exception as update_error:
                                logger.error(f"[{request_id}] ❌ THREAD HEARTBEAT #{heartbeat_count}: Update exception: {type(update_error).__name__}: {update_error}", exc_info=True)
                                # Try to recreate if update failed
                                if analysis_id not in db_service._mock_storage:
                                    logger.error(f"[{request_id}] ❌ THREAD HEARTBEAT #{heartbeat_count}: Analysis missing after update error - recreating...")
                                    from datetime import datetime
                                    db_service._mock_storage[analysis_id] = {
                                        'id': analysis_id,
                                        'patient_id': patient_id,
                                        'filename': 'unknown',
                                        'video_url': video_url,
                                        'status': 'processing',
                                        'current_step': last_known_progress['step'],
                                        'step_progress': last_known_progress['progress'],
                                        'step_message': f"{last_known_progress['message']} (recreated after error)",
                                        'metrics': {},
                                        'created_at': datetime.now().isoformat(),
                                        'updated_at': datetime.now().isoformat()
                                    }
                                    try:
                                        db_service._save_mock_storage(force_sync=True)
                                        logger.info(f"[{request_id}] ✅ THREAD HEARTBEAT #{heartbeat_count}: Recreated analysis after error")
                                    except:
                                        pass
                        else:
                            if heartbeat_count % 50 == 0:  # Log every 50 heartbeats
                                logger.warning(f"[{request_id}] ⚠️ THREAD HEARTBEAT #{heartbeat_count}: db_service not available")
                                    except Exception as heartbeat_error:
                                logger.error(f"[{heartbeat_request_id}] ❌ THREAD HEARTBEAT #{heartbeat_count}: Fatal error: {type(heartbeat_error).__name__}: {heartbeat_error}", exc_info=True)
                                # Continue - don't let errors stop the heartbeat
                        else:
                            if heartbeat_count % 50 == 0:  # Log every 50 heartbeats
                                logger.warning(f"[{heartbeat_request_id}] ⚠️ THREAD HEARTBEAT #{heartbeat_count}: db_service not available")
                    except Exception as heartbeat_error:
                        logger.error(f"[{heartbeat_request_id}] ❌ THREAD HEARTBEAT #{heartbeat_count}: Fatal error: {type(heartbeat_error).__name__}: {heartbeat_error}", exc_info=True)
                        # Continue - don't let errors stop the heartbeat
            except Exception as e:
                # CRITICAL: Catch ANY exception, including NameError for missing variables
                logger.error(f"[{heartbeat_request_id if 'heartbeat_request_id' in locals() else 'UNKNOWN'}] ❌ THREAD HEARTBEAT: Fatal outer error: {type(e).__name__}: {e}", exc_info=True)
                logger.error(f"❌ THREAD HEARTBEAT: Full traceback:", exc_info=True)
                # Try to restart heartbeat logic (but this shouldn't happen)
                logger.error(f"❌ THREAD HEARTBEAT: Heartbeat thread is exiting - analysis may become invisible!")
        
        # Start thread-based heartbeat IMMEDIATELY - before any processing starts
        # CRITICAL: Use non-daemon thread so it can't be killed by Python shutdown
        # This ensures the heartbeat continues even during long processing
        logger.error(f"[{request_id}] 🔧🔧🔧 HEARTBEAT THREAD CREATION DIAGNOSTIC 🔧🔧🔧")
        logger.error(f"[{request_id}] 🔧 About to create heartbeat thread for analysis {analysis_id}")
        logger.error(f"[{request_id}] 🔧 Current thread: {threading.current_thread().ident}, {threading.current_thread().name}")
        logger.error(f"[{request_id}] 🔧 db_service available: {db_service is not None}")
        logger.error(f"[{request_id}] 🔧 db_service._use_mock: {db_service._use_mock if db_service else None}")
        logger.error(f"[{request_id}] 🔧 Analysis in memory: {analysis_id in db_service._mock_storage if db_service else False}")
        
        try:
            heartbeat_thread = threading.Thread(target=thread_based_heartbeat, daemon=False, name=f"heartbeat-{analysis_id[:8]}")
            logger.error(f"[{request_id}] 🔧 Heartbeat thread object created: {heartbeat_thread}")
            logger.error(f"[{request_id}] 🔧 Thread name: {heartbeat_thread.name}")
            
            heartbeat_thread.start()
            logger.error(f"[{request_id}] 🔧 Heartbeat thread.start() called")
            
            # CRITICAL: Wait a moment and verify thread actually started
            import time as time_module
            time_module.sleep(0.2)  # Wait 200ms for thread to start
            
            thread_is_alive = heartbeat_thread.is_alive()
            thread_ident = heartbeat_thread.ident
            logger.error(f"[{request_id}] 🔧🔧🔧 HEARTBEAT THREAD STARTUP VERIFICATION 🔧🔧🔧")
            logger.error(f"[{request_id}] 🔧 Thread is_alive: {thread_is_alive}")
            logger.error(f"[{request_id}] 🔧 Thread ident: {thread_ident}")
            logger.error(f"[{request_id}] 🔧 Thread name: {heartbeat_thread.name}")
            
            if not thread_is_alive:
                logger.error(f"[{request_id}] ❌❌❌ CRITICAL: Heartbeat thread is NOT ALIVE after start()! ❌❌❌")
                logger.error(f"[{request_id}] ❌ This means the thread crashed immediately or never started")
                logger.error(f"[{request_id}] ❌ Analysis {analysis_id} will become invisible during processing!")
            else:
                logger.error(f"[{request_id}] ✅ Heartbeat thread is ALIVE and running")
            
            logger.info(f"[{request_id}] ✅ Started NON-DAEMON thread-based heartbeat for analysis {analysis_id} (thread ID: {thread_ident}, name: {heartbeat_thread.name}, alive: {thread_is_alive})")
            logger.info(f"[{request_id}] ✅ Heartbeat thread will run with MAXIMUM-FREQUENCY updates (every 0.1s = 10 times/second) to ensure persistence")
        except Exception as thread_start_error:
            logger.error(f"[{request_id}] ❌❌❌ CRITICAL: Failed to start heartbeat thread! ❌❌❌")
            logger.error(f"[{request_id}] ❌ Error: {type(thread_start_error).__name__}: {thread_start_error}", exc_info=True)
            logger.error(f"[{request_id}] ❌ Analysis {analysis_id} will become invisible during processing!")
            heartbeat_thread = None
        
        # Progress callback that maps internal progress to UI steps with error handling
        async def progress_callback(progress_pct: int, message: str) -> None:
            """
            Map internal progress (0-100%) to UI steps with comprehensive error handling
            CRITICAL: This must never fail - progress updates are non-critical
            
            Args:
                progress_pct: Internal progress percentage (0-100)
                message: Progress message
            """
            # CRITICAL: Wrap everything in try-except to ensure this never fails
            try:
                logger.info(f"[{request_id}] 📊 PROGRESS CALLBACK: {progress_pct}% - {message}")
                # Validate progress percentage
                if not isinstance(progress_pct, int) or progress_pct < 0 or progress_pct > 100:
                    logger.warning(
                        f"[{request_id}] Invalid progress percentage: {progress_pct}",
                        extra={"analysis_id": analysis_id, "progress_pct": progress_pct}
                    )
                    progress_pct = max(0, min(100, int(progress_pct)))
                
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
                
                logger.info(
                    f"[{request_id}] 📊 PROGRESS: {step} {mapped_progress}% - {message}",
                    extra={
                        "analysis_id": analysis_id,
                        "step": step,
                        "progress": mapped_progress,
                        "message": message
                    }
                )
                
                # CRITICAL: Update database - use SYNC method for reliability during CPU-intensive processing
                # Progress callback may be called from sync context, so use sync update method
                logger.error(f"[{request_id}] 📊📊📊 PROGRESS CALLBACK CALLED 📊📊📊")
                logger.error(f"[{request_id}] 📊 Analysis ID: {analysis_id}")
                logger.error(f"[{request_id}] 📊 Step: {step}, Progress: {mapped_progress}%, Message: '{message}'")
                logger.error(f"[{request_id}] 📊 db_service available: {db_service is not None}")
                logger.error(f"[{request_id}] 📊 Starting database update for analysis {analysis_id}")
                
                if db_service:
                    # CRITICAL: Update last known progress FIRST (for thread heartbeat)
                    logger.debug(f"[{request_id}] 📊 PROGRESS CALLBACK: Updating last_known_progress dict")
                    last_known_progress['step'] = step
                    last_known_progress['progress'] = mapped_progress
                    last_known_progress['message'] = message
                    logger.debug(f"[{request_id}] 📊 PROGRESS CALLBACK: last_known_progress updated: {last_known_progress}")
                    
                    # CRITICAL: Use sync update method (works from both async and sync contexts)
                    # This ensures updates succeed even during CPU-intensive processing
                    try:
                        logger.info(f"[{request_id}] 📝 PROGRESS CALLBACK: Updating analysis {analysis_id} with progress: {step} {mapped_progress}%")
                        logger.debug(f"[{request_id}] 📝 PROGRESS CALLBACK: db_service._use_mock = {db_service._use_mock}")
                        
                        if db_service._use_mock:
                            # Use sync method for mock storage (works from threads and async)
                            logger.debug(f"[{request_id}] 📝 PROGRESS CALLBACK: Using update_analysis_sync (mock storage)")
                            logger.debug(f"[{request_id}] 📝 PROGRESS CALLBACK: Checking if analysis {analysis_id} exists in memory...")
                            analysis_in_memory = analysis_id in db_service._mock_storage
                            logger.debug(f"[{request_id}] 📝 PROGRESS CALLBACK: Analysis {analysis_id} in memory: {analysis_in_memory}")
                            if analysis_in_memory:
                                logger.debug(f"[{request_id}] 📝 PROGRESS CALLBACK: Current analysis state: status={db_service._mock_storage[analysis_id].get('status')}, step={db_service._mock_storage[analysis_id].get('current_step')}, progress={db_service._mock_storage[analysis_id].get('step_progress')}")
                            
                            update_success = db_service.update_analysis_sync(analysis_id, {
                    'current_step': step,
                    'step_progress': mapped_progress,
                    'step_message': message
                })
                            logger.debug(f"[{request_id}] 📝 PROGRESS CALLBACK: update_analysis_sync returned: {update_success}")
                        else:
                            # For real SQL, use async method
                            logger.debug(f"[{request_id}] 📝 PROGRESS CALLBACK: Using async update_analysis (real SQL)")
                            update_success = await db_service.update_analysis(analysis_id, {
                                'current_step': step,
                                'step_progress': mapped_progress,
                                'step_message': message
                            })
                            logger.debug(f"[{request_id}] 📝 PROGRESS CALLBACK: async update_analysis returned: {update_success}")
                        
                        if update_success:
                            logger.info(f"[{request_id}] ✅ PROGRESS CALLBACK: Successfully updated analysis {analysis_id} progress to {step} {mapped_progress}%")
                            # Verify update was saved
                            if db_service._use_mock:
                                if analysis_id in db_service._mock_storage:
                                    logger.debug(f"[{request_id}] ✅ PROGRESS CALLBACK: Verified - analysis {analysis_id} exists in memory after update")
                                    logger.debug(f"[{request_id}] ✅ PROGRESS CALLBACK: Verified state: status={db_service._mock_storage[analysis_id].get('status')}, step={db_service._mock_storage[analysis_id].get('current_step')}, progress={db_service._mock_storage[analysis_id].get('step_progress')}")
                                else:
                                    logger.error(f"[{request_id}] ❌ PROGRESS CALLBACK: CRITICAL - Analysis {analysis_id} NOT in memory after successful update!")
                        else:
                            # Update failed - recreate analysis immediately
                            logger.warning(f"[{request_id}] ⚠️ PROGRESS CALLBACK: Update returned False - recreating analysis {analysis_id}")
                            logger.debug(f"[{request_id}] ⚠️ PROGRESS CALLBACK: Recreating analysis with step={step}, progress={mapped_progress}%")
                            if db_service._use_mock:
                                # Recreate in memory and file
                                from datetime import datetime
                                logger.debug(f"[{request_id}] ⚠️ PROGRESS CALLBACK: Creating analysis dict for recreation...")
                                db_service._mock_storage[analysis_id] = {
                                    'id': analysis_id,
                                    'patient_id': patient_id,
                                    'filename': 'unknown',
                                    'video_url': video_url,
                                    'status': 'processing',
                                    'current_step': step,
                                    'step_progress': mapped_progress,
                                    'step_message': message,
                                    'metrics': {},
                                    'created_at': datetime.now().isoformat(),
                                    'updated_at': datetime.now().isoformat()
                                }
                                logger.debug(f"[{request_id}] ⚠️ PROGRESS CALLBACK: Analysis dict created, saving to file...")
                                db_service._save_mock_storage()
                                logger.info(f"[{request_id}] ✅ PROGRESS CALLBACK: Recreated analysis {analysis_id} in memory and file")
                                logger.debug(f"[{request_id}] ✅ PROGRESS CALLBACK: Verification - analysis in memory: {analysis_id in db_service._mock_storage}")
                            else:
                                logger.debug(f"[{request_id}] ⚠️ PROGRESS CALLBACK: Recreating analysis using async create_analysis (real SQL)")
                                await db_service.create_analysis({
                                    'id': analysis_id,
                                    'patient_id': patient_id,
                                    'filename': 'unknown',
                                    'video_url': video_url,
                                    'status': 'processing',
                                    'current_step': step,
                                    'step_progress': mapped_progress,
                                    'step_message': message
                                })
                    except Exception as update_error:
                        # CRITICAL: On any error, recreate analysis immediately
                        logger.error(
                            f"[{request_id}] ❌ PROGRESS CALLBACK: Progress update error: {type(update_error).__name__}: {update_error}. Recreating analysis...",
                            extra={"analysis_id": analysis_id, "step": step, "error_type": type(update_error).__name__, "error_message": str(update_error)},
                            exc_info=True
                        )
                        try:
                            if db_service._use_mock:
                                # Recreate in memory and file
                                from datetime import datetime
                                logger.debug(f"[{request_id}] ❌ PROGRESS CALLBACK: Recreating analysis in memory after error...")
                                db_service._mock_storage[analysis_id] = {
                                    'id': analysis_id,
                                    'patient_id': patient_id,
                                    'filename': 'unknown',
                                    'video_url': video_url,
                                    'status': 'processing',
                                    'current_step': step,
                                    'step_progress': mapped_progress,
                                    'step_message': message,
                                    'metrics': {},
                                    'created_at': datetime.now().isoformat(),
                                    'updated_at': datetime.now().isoformat()
                                }
                                logger.debug(f"[{request_id}] ❌ PROGRESS CALLBACK: Saving recreated analysis to file...")
                                db_service._save_mock_storage()
                                logger.warning(f"[{request_id}] ✅ PROGRESS CALLBACK: Recreated analysis after progress update error")
                                logger.debug(f"[{request_id}] ✅ PROGRESS CALLBACK: Verification - analysis in memory: {analysis_id in db_service._mock_storage}")
                            else:
                                logger.debug(f"[{request_id}] ❌ PROGRESS CALLBACK: Recreating analysis using async create_analysis after error")
                                await db_service.create_analysis({
                                    'id': analysis_id,
                                    'patient_id': patient_id,
                                    'filename': 'unknown',
                                    'video_url': video_url,
                                    'status': 'processing',
                                    'current_step': step,
                                    'step_progress': mapped_progress,
                                    'step_message': message
                                })
                        except Exception as recreate_error:
                            logger.error(f"[{request_id}] ❌ PROGRESS CALLBACK: Failed to recreate analysis: {type(recreate_error).__name__}: {recreate_error}", exc_info=True)
                            # Don't raise - progress updates are non-critical
                            # Analysis will be recreated by thread heartbeat
                else:
                    logger.warning(f"[{request_id}] ⚠️ PROGRESS CALLBACK: db_service is None - cannot update analysis")
            except Exception as e:
                # CRITICAL: Catch-all to ensure progress callback never fails the process
                logger.error(
                    f"[{request_id}] Unexpected error in progress callback: {e}",
                    extra={"analysis_id": analysis_id, "progress_pct": progress_pct},
                    exc_info=True
                )
                # Don't raise - progress updates must never stop processing
        
        # STEP 1-4: Analyze video using advanced gait analysis with comprehensive error handling
        # CRITICAL: Each step has fallback mechanisms to ensure processing continues
        analysis_result = None
        try:
            logger.info(
                f"[{request_id}] Starting video analysis (all 4 steps)",
                extra={
                    "analysis_id": analysis_id,
                    "video_path": video_path,
                    "fps": fps,
                    "view_type": view_type,
                    "reference_length_mm": reference_length_mm
                }
            )
            
            # Update progress: Starting pose estimation
            try:
                await db_service.update_analysis(analysis_id, {
                    'current_step': 'pose_estimation',
                    'step_progress': 10,
                    'step_message': 'Starting pose estimation...'
                })
                # Update last known progress for heartbeat
                last_known_progress['step'] = 'pose_estimation'
                last_known_progress['progress'] = 10
                last_known_progress['message'] = 'Starting pose estimation...'
            except Exception as e:
                logger.warning(f"[{request_id}] Failed to update progress at start: {e}")
            
            logger.info(f"[{request_id}] 🎬 STARTING VIDEO ANALYSIS: video_path={video_path}, fps={fps}, view_type={view_type}")
            logger.info(f"[{request_id}] 🎬 Analysis will call progress_callback during processing")
            # CRITICAL: Verify heartbeat thread is still running before starting video processing
            heartbeat_is_alive = heartbeat_thread.is_alive() if heartbeat_thread else False
            logger.error(f"[{request_id}] 🎬🎬🎬 VIDEO PROCESSING START DIAGNOSTIC 🎬🎬🎬")
            logger.error(f"[{request_id}] 🎬 About to start video analysis for {analysis_id}")
            logger.error(f"[{request_id}] 🎬 Heartbeat thread exists: {heartbeat_thread is not None}")
            logger.error(f"[{request_id}] 🎬 Heartbeat thread is_alive: {heartbeat_is_alive}")
            logger.error(f"[{request_id}] 🎬 Heartbeat thread ID: {heartbeat_thread.ident if heartbeat_thread else None}")
            logger.error(f"[{request_id}] 🎬 Analysis in memory: {analysis_id in db_service._mock_storage if db_service else False}")
            
            if not heartbeat_is_alive:
                logger.error(f"[{request_id}] ❌❌❌ CRITICAL: Heartbeat thread is NOT ALIVE before video processing! ❌❌❌")
                logger.error(f"[{request_id}] ❌ Analysis {analysis_id} will become invisible during processing!")
                logger.error(f"[{request_id}] ❌ Attempting to restart heartbeat thread...")
                try:
                    heartbeat_thread = threading.Thread(target=thread_based_heartbeat, daemon=False, name=f"heartbeat-{analysis_id[:8]}-restart")
                    heartbeat_thread.start()
                    time.sleep(0.2)
                    if heartbeat_thread.is_alive():
                        logger.error(f"[{request_id}] ✅ Heartbeat thread restarted successfully")
                    else:
                        logger.error(f"[{request_id}] ❌ Heartbeat thread restart failed")
                except Exception as restart_error:
                    logger.error(f"[{request_id}] ❌ Failed to restart heartbeat thread: {restart_error}", exc_info=True)
            
            logger.info(f"[{request_id}] 🎬 Heartbeat thread is running: {heartbeat_is_alive} (thread ID: {heartbeat_thread.ident if heartbeat_thread else None})")
        
            # CRITICAL: Add periodic heartbeat verification during video processing
            # This will help identify if heartbeat dies during processing
            async def periodic_heartbeat_check():
                """Periodically check if heartbeat is still alive during processing"""
                check_count = 0
                try:
                    while True:
                        await asyncio.sleep(5.0)  # Check every 5 seconds
                        check_count += 1
                        if heartbeat_thread:
                            is_alive = heartbeat_thread.is_alive()
                            logger.error(f"[{request_id}] 🔍 PERIODIC HEARTBEAT CHECK #{check_count}: Thread alive={is_alive}, Thread ID={heartbeat_thread.ident}")
                            if not is_alive:
                                logger.error(f"[{request_id}] ❌❌❌ CRITICAL: Heartbeat thread DIED during processing! ❌❌❌")
                                logger.error(f"[{request_id}] ❌ Check count: {check_count}, Analysis ID: {analysis_id}")
                                logger.error(f"[{request_id}] ❌ Analysis in memory: {analysis_id in db_service._mock_storage if db_service else False}")
                        else:
                            logger.error(f"[{request_id}] ❌ PERIODIC CHECK #{check_count}: Heartbeat thread is None!")
                except asyncio.CancelledError:
                    logger.error(f"[{request_id}] 🔍 Periodic heartbeat monitor cancelled")
            
            # Start periodic heartbeat monitoring
            heartbeat_monitor_task = asyncio.create_task(periodic_heartbeat_check())
            logger.error(f"[{request_id}] 🔍 Started periodic heartbeat monitor task")
            
            logger.error(f"[{request_id}] 🎬🎬🎬 CALLING analyze_video 🎬🎬🎬")
            logger.error(f"[{request_id}] 🎬 Video path: {video_path}")
            logger.error(f"[{request_id}] 🎬 FPS: {fps}, View type: {view_type}")
            logger.error(f"[{request_id}] 🎬 Progress callback available: {progress_callback is not None}")
            
        analysis_result = await gait_service.analyze_video(
            video_path,
            fps=fps,
            reference_length_mm=reference_length_mm,
            view_type=view_type,
            progress_callback=progress_callback
        )
        
            # Stop periodic monitoring
            heartbeat_monitor_task.cancel()
            try:
                await heartbeat_monitor_task
            except asyncio.CancelledError:
                pass
            logger.error(f"[{request_id}] 🔍 Stopped periodic heartbeat monitor")
            logger.info(f"[{request_id}] ✅ VIDEO ANALYSIS COMPLETE: Got result with keys: {list(analysis_result.keys()) if analysis_result else 'None'}")
            
            # CRITICAL: Validate that processing actually happened
            if not analysis_result:
                error_msg = "Video analysis returned None - no result generated"
                logger.error(f"[{request_id}] ❌ {error_msg}")
                raise VideoProcessingError(
                    error_msg,
                    details={"analysis_id": analysis_id, "video_path": video_path}
                )
            
            # CRITICAL: Validate that frames were actually processed
            frames_processed = analysis_result.get('frames_processed', 0)
            total_frames = analysis_result.get('total_frames', 0)
            
            logger.info(
                f"[{request_id}] Video analysis validation: {frames_processed}/{total_frames} frames processed",
                extra={
                    "analysis_id": analysis_id,
                    "frames_processed": frames_processed,
                    "total_frames": total_frames,
                    "has_metrics": "metrics" in analysis_result if analysis_result else False,
                    "result_status": analysis_result.get('status') if analysis_result else None
                }
            )
            
            if frames_processed == 0:
                error_msg = f"CRITICAL: Video processing completed but no frames were processed! Total frames: {total_frames}"
                logger.error(f"[{request_id}] ❌ {error_msg}")
                raise VideoProcessingError(
                    error_msg,
                    details={
                        "analysis_id": analysis_id,
                        "video_path": video_path,
                        "total_frames": total_frames,
                        "frames_processed": frames_processed
                    }
                )
            
            # Validate that metrics exist and are not fallback
            metrics = analysis_result.get('metrics', {})
            if not metrics or metrics.get('fallback_metrics', False):
                error_msg = "Video processing completed but metrics are missing or fallback"
                logger.error(f"[{request_id}] ❌ {error_msg}")
                raise VideoProcessingError(
                    error_msg,
                    details={
                        "analysis_id": analysis_id,
                        "has_metrics": bool(metrics),
                        "fallback_metrics": metrics.get('fallback_metrics', False) if metrics else None
                    }
                )
            
            logger.info(
                f"[{request_id}] ✅ Video analysis completed successfully: {frames_processed} frames processed, {len(metrics)} metrics calculated",
                extra={
                    "analysis_id": analysis_id,
                    "frames_processed": frames_processed,
                    "total_frames": total_frames,
                    "metrics_count": len(metrics),
                    "has_symmetry": "step_time_symmetry" in metrics or "step_length_symmetry" in metrics
                }
            )
        except PoseEstimationError as e:
            logger.error(
                f"[{request_id}] ❌ Pose estimation failed: {e.message}",
                extra={"analysis_id": analysis_id, "error_code": e.error_code, "details": e.details},
                exc_info=True
            )
            # CRITICAL: Don't create fallback - fail the analysis so user knows processing didn't work
            raise VideoProcessingError(
                f"Pose estimation failed: {e.message}",
                details={"analysis_id": analysis_id, "error_code": e.error_code, "details": e.details}
            )
        except GaitMetricsError as e:
            logger.error(
                f"[{request_id}] ❌ Gait metrics calculation failed: {e.message}",
                extra={"analysis_id": analysis_id, "error_code": e.error_code, "details": e.details},
                exc_info=True
            )
            # CRITICAL: Don't create fallback - fail the analysis so user knows processing didn't work
            raise VideoProcessingError(
                f"Gait metrics calculation failed: {e.message}",
                details={"analysis_id": analysis_id, "error_code": e.error_code, "details": e.details}
            )
        except Exception as e:
            logger.error(
                f"[{request_id}] ❌ Unexpected error during video analysis: {type(e).__name__}: {e}",
                extra={"analysis_id": analysis_id, "error_type": type(e).__name__},
                exc_info=True
            )
            # CRITICAL: Don't create fallback - fail the analysis so user knows processing didn't work
            raise VideoProcessingError(
                f"Unexpected error during video analysis: {str(e)}",
                details={"analysis_id": analysis_id, "error_type": type(e).__name__, "error": str(e)}
            )
        
        # STEP 3-4: Extract and format metrics with validation and fallback
        # CRITICAL: Ensure we always have metrics, even if extraction fails
        metrics = {}
        try:
            if not analysis_result:
                raise ValueError("Analysis result is None")
            
        raw_metrics = analysis_result.get('metrics', {})
        
            if not raw_metrics:
                logger.warning(
                    f"[{request_id}] Analysis result has no metrics, using fallback",
                    extra={"analysis_id": analysis_id, "analysis_result_keys": list(analysis_result.keys()) if analysis_result else []}
                )
                # Use fallback metrics instead of failing
                raw_metrics = {
                    'cadence': 0.0,
                    'step_length': 0.0,
                    'walking_speed': 0.0,
                    'stride_length': 0.0,
                    'double_support_time': 0.0,
                    'swing_time': 0.0,
                    'stance_time': 0.0,
                    'fallback_metrics': True
                }
            
            # Map to expected metric names with type validation
            def safe_get_metric(key: str, default: float = 0.0) -> float:
                """Safely extract metric value with type checking"""
                value = raw_metrics.get(key, default)
                try:
                    return float(value) if value is not None else default
                except (ValueError, TypeError):
                    logger.warning(
                        f"[{request_id}] Invalid metric value for {key}: {value}",
                        extra={"analysis_id": analysis_id, "metric_key": key, "value": value}
                    )
                    return default
            
        metrics = {
                'cadence': safe_get_metric('cadence', 0.0),
                'step_length': safe_get_metric('step_length', 0.0),  # in mm
                'walking_speed': safe_get_metric('walking_speed', 0.0),  # in mm/s
                'stride_length': safe_get_metric('stride_length', 0.0),  # in mm
                'double_support_time': safe_get_metric('double_support_time', 0.0),  # in seconds
                'swing_time': safe_get_metric('swing_time', 0.0),  # in seconds
                'stance_time': safe_get_metric('stance_time', 0.0),  # in seconds
            }
            
            # Add professional metrics if available
            if 'step_time_symmetry' in raw_metrics:
                metrics['step_time_symmetry'] = safe_get_metric('step_time_symmetry', 0.0)
            if 'step_length_symmetry' in raw_metrics:
                metrics['step_length_symmetry'] = safe_get_metric('step_length_symmetry', 0.0)
            if 'step_length_cv' in raw_metrics:
                metrics['step_length_cv'] = safe_get_metric('step_length_cv', 0.0)
            if 'step_time_cv' in raw_metrics:
                metrics['step_time_cv'] = safe_get_metric('step_time_cv', 0.0)
            if 'biomechanical_validation' in raw_metrics:
                metrics['biomechanical_validation'] = raw_metrics.get('biomechanical_validation', {})
            
            logger.info(
                f"[{request_id}] Metrics extracted and validated",
                extra={"analysis_id": analysis_id, "metric_count": len(metrics)}
            )
        except Exception as e:
            logger.error(
                f"[{request_id}] Error extracting metrics: {e}",
                extra={"analysis_id": analysis_id, "error_type": type(e).__name__},
                exc_info=True
            )
            # CRITICAL: Don't fail - use fallback metrics
            logger.warning(f"[{request_id}] Using fallback metrics due to extraction error")
            metrics = {
                'cadence': 0.0,
                'step_length': 0.0,
                'walking_speed': 0.0,
                'stride_length': 0.0,
                'double_support_time': 0.0,
                'swing_time': 0.0,
                'stance_time': 0.0,
                'fallback_metrics': True,
                'error': f"Metrics extraction failed: {str(e)}"
            }
        
        # STEP 4: Update progress: Report generation - with retry logic
        max_db_retries = 5
        for retry in range(max_db_retries):
            try:
        await db_service.update_analysis(analysis_id, {
            'current_step': 'report_generation',
            'step_progress': 95,
            'step_message': 'Generating analysis report...'
        })
                break  # Success
            except Exception as e:
                if retry < max_db_retries - 1:
                    logger.warning(
                        f"[{request_id}] Failed to update progress for report generation (attempt {retry + 1}/{max_db_retries}): {e}. Retrying...",
                        extra={"analysis_id": analysis_id}
                    )
                    await asyncio.sleep(0.2 * (retry + 1))
                    continue
                else:
                    logger.error(
                        f"[{request_id}] Failed to update progress for report generation after {max_db_retries} attempts: {e}",
                        extra={"analysis_id": analysis_id},
                        exc_info=True
                    )
                    # Continue anyway - not critical
        
        # CRITICAL: Stop heartbeat before final updates
        # But keep it running until we're sure the analysis is saved
        if heartbeat_stop_event:
            logger.info(f"[{request_id}] Stopping heartbeat thread before final update...")
            heartbeat_stop_event.set()
            if heartbeat_thread and heartbeat_thread.is_alive():
                try:
                    heartbeat_thread.join(timeout=3.0)  # Increased timeout
                    if heartbeat_thread.is_alive():
                        logger.warning(f"[{request_id}] Heartbeat thread did not stop within timeout")
                    else:
                        logger.info(f"[{request_id}] Heartbeat thread stopped successfully")
                except Exception as e:
                    logger.warning(f"[{request_id}] Error stopping heartbeat thread: {e}")
        
        # CRITICAL: Verify analysis exists before final update
        analysis_verified = False
        for verify_retry in range(10):
            try:
                final_check = await db_service.get_analysis(analysis_id)
                if final_check and final_check.get('id') == analysis_id:
                    analysis_verified = True
                    logger.info(f"[{request_id}] Verified analysis exists before final update (attempt {verify_retry + 1})")
                    break
            except Exception as verify_error:
                if verify_retry < 9:
                    logger.warning(f"[{request_id}] Analysis verification failed (attempt {verify_retry + 1}): {verify_error}. Retrying...")
                    await asyncio.sleep(0.2 * (verify_retry + 1))
                    continue
        
        if not analysis_verified:
            logger.error(f"[{request_id}] Analysis {analysis_id} not found before final update. Recreating...")
            # CRITICAL: Recreate analysis if lost
            try:
                await db_service.create_analysis({
                    'id': analysis_id,
                    'patient_id': patient_id,
                    'filename': 'unknown',
                    'video_url': video_url,
                    'status': 'processing',
                    'current_step': 'report_generation',
                    'step_progress': 95,
                    'step_message': 'Finalizing analysis...',
                    'metrics': metrics
                })
                logger.warning(f"[{request_id}] Recreated analysis record before final update")
            except Exception as recreate_error:
                logger.error(f"[{request_id}] Failed to recreate analysis: {recreate_error}")
        
        # STEP 4: Final update: Mark as completed with metrics - CRITICAL with retry logic
        # This is the most important update - must succeed
        completion_success = False
        max_db_retries = 10  # Increased retries for critical final update
        for retry in range(max_db_retries):
            try:
        await db_service.update_analysis(analysis_id, {
            'status': 'completed',
            'current_step': 'report_generation',
            'step_progress': 100,
            'step_message': 'Analysis complete!',
            'metrics': metrics
        })
                completion_success = True
                logger.info(
                    f"[{request_id}] Analysis completed successfully",
                    extra={
                        "analysis_id": analysis_id,
                        "patient_id": patient_id,
                        "metrics_count": len(metrics),
                        "has_symmetry": "step_time_symmetry" in metrics or "step_length_symmetry" in metrics,
                        "fallback_metrics": metrics.get('fallback_metrics', False)
                    }
                )
                
                # Log key metrics for monitoring
                logger.info(
                    f"[{request_id}] Key metrics",
                    extra={
                        "analysis_id": analysis_id,
                        "cadence": metrics.get('cadence'),
                        "walking_speed": metrics.get('walking_speed'),
                        "step_length": metrics.get('step_length')
                    }
                )
                break  # Success - exit retry loop
            except Exception as e:
                if retry < max_db_retries - 1:
                    logger.warning(
                        f"[{request_id}] Failed to mark analysis as completed (attempt {retry + 1}/{max_db_retries}): {e}. Retrying...",
                        extra={"analysis_id": analysis_id},
                        exc_info=True
                    )
                    await asyncio.sleep(0.3 * (retry + 1))  # Progressive delay
                    continue
                else:
                    logger.error(
                        f"[{request_id}] CRITICAL: Failed to mark analysis as completed after {max_db_retries} attempts: {e}",
                        extra={"analysis_id": analysis_id},
                        exc_info=True
                    )
                    # CRITICAL: Even if database update fails, the analysis is complete
                    # Log this as a warning but don't fail - metrics are in memory
                    logger.warning(
                        f"[{request_id}] Analysis processing completed but database update failed. Metrics are available in memory.",
                        extra={"analysis_id": analysis_id, "metrics": metrics}
                    )
        
        if not completion_success:
            # Last resort: try one more time with a longer delay
            try:
                await asyncio.sleep(1.0)
                await db_service.update_analysis(analysis_id, {
                    'status': 'completed',
                    'current_step': 'report_generation',
                    'step_progress': 100,
                    'step_message': 'Analysis complete! (final retry)',
                    'metrics': metrics
                })
                logger.info(f"[{request_id}] Analysis completion update succeeded on final retry")
            except Exception as final_error:
                logger.critical(
                    f"[{request_id}] CRITICAL: All attempts to mark analysis as completed failed. Analysis is complete but status may not be updated.",
                    extra={"analysis_id": analysis_id, "error": str(final_error)},
                    exc_info=True
                )
                # Don't raise - processing is complete, just status update failed
    
    except asyncio.TimeoutError as e:
        error_msg = (
            "Analysis timed out after 60 minutes. "
            "Video may be extremely long or processing is taking longer than expected."
        )
        logger.error(
            f"[{request_id}] Timeout processing analysis",
            extra={
                "analysis_id": analysis_id,
                "error_type": "TimeoutError",
                "timeout_seconds": 3600
            },
            exc_info=True
        )
        try:
        await db_service.update_analysis(analysis_id, {
            'status': 'failed',
            'step_message': error_msg
        })
        except Exception as db_err:
            logger.error(f"[{request_id}] Failed to update analysis status after timeout: {db_err}")
    
    except (VideoProcessingError, PoseEstimationError, GaitMetricsError, ValidationError, StorageError, DatabaseError) as e:
        # Handle custom exceptions
        logger.error(
            f"[{request_id}] Analysis failed: {e.error_code} - {e.message}",
            extra={
                "analysis_id": analysis_id,
                "error_code": e.error_code,
                "error_details": e.details,
                "error_type": type(e).__name__
            },
            exc_info=True
        )
        try:
            if db_service:
                await db_service.update_analysis(analysis_id, {
                    'status': 'failed',
                    'step_message': f"{e.error_code}: {e.message}"
                })
        except Exception as db_err:
            logger.error(
                f"[{request_id}] Failed to update analysis status after error: {db_err}",
                extra={"analysis_id": analysis_id, "original_error": e.error_code},
                exc_info=True
            )
    
    except Exception as e:
        # Catch-all for unexpected errors
        error_msg = f"Analysis failed: {str(e)}"
        logger.error(
            f"[{request_id}] Unexpected error processing analysis",
            extra={
                "analysis_id": analysis_id,
                "error_type": type(e).__name__,
                "error_message": str(e)
            },
            exc_info=True
        )
        try:
        await db_service.update_analysis(analysis_id, {
            'status': 'failed',
            'step_message': error_msg
        })
        except Exception as db_err:
            logger.error(f"[{request_id}] Failed to update analysis status: {db_err}")
    
    finally:
        # CRITICAL: Stop heartbeat in finally block
        if heartbeat_stop_event:
            heartbeat_stop_event.set()
            if heartbeat_thread and heartbeat_thread.is_alive():
                try:
                    heartbeat_thread.join(timeout=2.0)
                except Exception as e:
                    logger.warning(f"[{request_id}] Error stopping heartbeat: {e}")
        
        # CRITICAL: Ensure analysis is always saved, even if processing failed
        # This prevents "Analysis not found" errors
        try:
            final_analysis = await db_service.get_analysis(analysis_id)
            if not final_analysis:
                logger.error(f"[{request_id}] Analysis {analysis_id} not found in finally block. Attempting to recreate...")
                # Try to recreate with whatever state we have
                try:
                    await db_service.create_analysis({
                        'id': analysis_id,
                        'patient_id': patient_id,
                        'filename': 'unknown',
                        'video_url': video_url,
                        'status': 'failed',
                        'current_step': 'pose_estimation',
                        'step_progress': 0,
                        'step_message': 'Analysis record was lost - recreated in finally block'
                    })
                    logger.warning(f"[{request_id}] Recreated analysis record in finally block")
                except Exception as recreate_error:
                    logger.error(f"[{request_id}] Failed to recreate analysis in finally: {recreate_error}")
        except Exception as final_check_error:
            logger.error(f"[{request_id}] Error checking analysis in finally: {final_check_error}")
        
        # Clean up temporary video file with proper error handling
        if video_path and os.path.exists(video_path) and video_path != video_url:
            try:
                os.unlink(video_path)
                logger.info(
                    f"[{request_id}] Cleaned up temporary video",
                    extra={"video_path": video_path, "analysis_id": analysis_id}
                )
            except OSError as e:
                logger.warning(
                    f"[{request_id}] Failed to clean up temp file: {e}",
                    extra={"video_path": video_path, "analysis_id": analysis_id}
                )
            except Exception as e:
                logger.error(
                    f"[{request_id}] Unexpected error cleaning up temp file: {e}",
                    extra={"video_path": video_path, "analysis_id": analysis_id},
                    exc_info=True
                )


@router.get(
    "/list",
    response_model=AnalysisListResponse,
    responses={
        500: {"model": ErrorResponse, "description": "Internal server error"},
        503: {"model": ErrorResponse, "description": "Service unavailable"}
    }
)
async def list_analyses(
    limit: int = Query(50, ge=1, le=1000, description="Maximum number of analyses to return")
) -> AnalysisListResponse:
    """
    List all analyses, ordered by most recent first
    
    Args:
        limit: Maximum number of analyses to return (1-1000)
        
    Returns:
        AnalysisListResponse with list of analyses
        
    Raises:
        HTTPException: On database errors
    """
    request_id = str(uuid.uuid4())[:8]
    logger.info(f"[{request_id}] List analyses request", extra={"limit": limit})
    
    if db_service is None:
        logger.error(f"[{request_id}] Database service not available")
        raise HTTPException(
            status_code=503,
            detail={
                "error": "SERVICE_UNAVAILABLE",
                "message": "Database service is not available",
                "details": {}
            }
        )
    
    try:
        analyses = await db_service.list_analyses(limit=limit)
        logger.info(f"[{request_id}] Retrieved {len(analyses)} analyses", extra={"count": len(analyses)})
        
        return AnalysisListResponse(
            analyses=[AnalysisDetailResponse(**a) for a in analyses],
            total=len(analyses),
            limit=limit
        )
    except Exception as e:
        logger.error(
            f"[{request_id}] Error listing analyses: {e}",
            extra={"error_type": type(e).__name__},
            exc_info=True
        )
        raise DatabaseError("Failed to retrieve analyses list", details={"error": str(e)})


@router.get(
    "/{analysis_id}",
    response_model=AnalysisDetailResponse,
    responses={
        404: {"model": ErrorResponse, "description": "Analysis not found"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
        503: {"model": ErrorResponse, "description": "Service unavailable"}
    }
)
async def get_analysis(
    analysis_id: str = PathParam(..., description="Analysis identifier", pattern="^[a-f0-9-]{36}$")
) -> AnalysisDetailResponse:
    """
    Get analysis status and results by ID
    
    Args:
        analysis_id: UUID of the analysis to retrieve
        
    Returns:
        AnalysisDetailResponse with full analysis details
        
    Raises:
        HTTPException: 404 if not found, 500/503 on errors
    """
    request_id = str(uuid.uuid4())[:8]
    logger.info(f"[{request_id}] Get analysis request", extra={"analysis_id": analysis_id})
    
    # Validate UUID format
    try:
        uuid.UUID(analysis_id)
    except ValueError:
        logger.warning(f"[{request_id}] Invalid UUID format: {analysis_id}")
        raise ValidationError(
            f"Invalid analysis ID format: {analysis_id}",
            field="analysis_id",
            details={"provided": analysis_id, "expected_format": "UUID"}
        )
    
    if db_service is None:
        logger.error(f"[{request_id}] Database service not available")
        raise HTTPException(
            status_code=503,
            detail={
                "error": "SERVICE_UNAVAILABLE",
                "message": "Database service is not available",
                "details": {}
            }
        )
    
    try:
        analysis = await db_service.get_analysis(analysis_id)
        
        if not analysis:
            logger.warning(f"[{request_id}] ⚠️ Analysis not found in database", extra={"analysis_id": analysis_id})
            # Don't recreate - return 404 so frontend knows analysis doesn't exist
            # The defensive recreation was causing stuck states
            raise HTTPException(
                status_code=404,
                detail={
                    "error": "NOT_FOUND",
                    "message": f"Analysis with ID {analysis_id} not found",
                    "details": {"analysis_id": analysis_id}
                }
            )
        
        logger.info(f"[{request_id}] Analysis retrieved successfully", extra={"analysis_id": analysis_id, "status": analysis.get("status")})
        return AnalysisDetailResponse(**analysis)
    
    except HTTPException:
        raise  # Re-raise HTTP exceptions
    except ValidationError as e:
        raise gait_error_to_http(e)
    except Exception as e:
        logger.error(
            f"[{request_id}] Error getting analysis: {e}",
            extra={"analysis_id": analysis_id, "error_type": type(e).__name__},
            exc_info=True
        )
        raise DatabaseError(
            f"Failed to retrieve analysis {analysis_id}",
            details={"error": str(e), "analysis_id": analysis_id}
        )


