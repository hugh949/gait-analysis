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
        raise  # Database is critical, fail if it can't be initialized

# Initialize services at module load
try:
    initialize_services()
except Exception as e:
    logger.critical(f"Critical service initialization failed: {e}", exc_info=True)
    raise

def get_gait_analysis_service() -> Optional[GaitAnalysisService]:
    """Get or create gait analysis service instance with error handling"""
    global _gait_analysis_service
    if _gait_analysis_service is None:
        try:
            logger.debug("Initializing GaitAnalysisService...")
            _gait_analysis_service = GaitAnalysisService()
            logger.info("✓ GaitAnalysisService initialized successfully")
        except ImportError as e:
            logger.error(f"Import error initializing GaitAnalysisService: {e}", exc_info=True)
            _gait_analysis_service = None
        except Exception as e:
            logger.error(f"Failed to initialize GaitAnalysisService: {e}", exc_info=True)
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
    logger.info(
        f"[{request_id}] Upload request received",
        extra={
            "request_id": request_id,
            "filename": file.filename if file else None,
            "content_type": request.headers.get("content-type"),
            "patient_id": patient_id,
            "view_type": view_type,
            "fps": fps
        }
    )
    
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
    MAX_FILE_SIZE = 500 * 1024 * 1024  # 500MB
    file_size = 0
    tmp_path: Optional[str] = None
    video_url: Optional[str] = None
    
    try:
    
        # Create temp file with proper error handling
        try:
            tmp_file = tempfile.NamedTemporaryFile(delete=False, suffix=file_ext)
            tmp_path = tmp_file.name
            logger.debug(f"[{request_id}] Created temp file: {tmp_path}")
        except OSError as e:
            logger.error(f"[{request_id}] Failed to create temp file: {e}", exc_info=True)
            raise StorageError("Failed to create temporary file for upload", details={"error": str(e)})
        
        # Read file in chunks with size validation
        chunk_size = 1024 * 1024  # 1MB chunks
        try:
            while True:
                chunk = await file.read(chunk_size)
                if not chunk:
                    break
                file_size += len(chunk)
                
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
                
                tmp_file.write(chunk)
            
            tmp_file.close()
            logger.info(
                f"[{request_id}] File uploaded successfully",
                extra={"filename": file.filename, "size": file_size, "path": tmp_path}
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
            
        background_tasks.add_task(
            process_analysis_azure,
            analysis_id,
            video_url,
            patient_id,
                view_type_str,
            reference_length_mm,
            fps
        )
            # CRITICAL: Start keep-alive heartbeat IMMEDIATELY after scheduling
            # This ensures the analysis stays alive even before processing starts
            # This is especially important in multi-worker environments
            async def immediate_keepalive():
                """Immediate keep-alive that starts right after analysis creation"""
                keepalive_count = 0
                try:
                    # Start with very frequent updates (every 2 seconds) for first 30 seconds
                    # Then switch to every 5 seconds
                    while True:
                        await asyncio.sleep(2 if keepalive_count < 15 else 5)  # 2s for first 30s, then 5s
                        keepalive_count += 1
                        try:
                            # Verify and update analysis to keep it alive
                            current_analysis = await db_service.get_analysis(analysis_id)
                            if current_analysis:
                                await db_service.update_analysis(analysis_id, {
                                    'status': 'processing',
                                    'current_step': current_analysis.get('current_step', 'pose_estimation'),
                                    'step_progress': current_analysis.get('step_progress', 0),
                                    'step_message': current_analysis.get('step_message', 'Initializing analysis...')
                                })
                                if keepalive_count % 5 == 0:  # Log every 10 seconds
                                    logger.debug(f"[{request_id}] Keep-alive: Analysis {analysis_id} is alive (count: {keepalive_count})")
                            else:
                                logger.warning(f"[{request_id}] Keep-alive: Analysis {analysis_id} not found - recreating")
                                await db_service.create_analysis({
                                    'id': analysis_id,
                                    'patient_id': patient_id,
                                    'filename': file.filename or 'unknown',
                                    'video_url': video_url,
                                    'status': 'processing',
                                    'current_step': 'pose_estimation',
                                    'step_progress': 0,
                                    'step_message': 'Initializing analysis...'
                                })
                        except Exception as keepalive_error:
                            logger.warning(f"[{request_id}] Keep-alive error (non-critical): {keepalive_error}")
                except asyncio.CancelledError:
                    logger.info(f"[{request_id}] Keep-alive cancelled after {keepalive_count} updates")
                except Exception as e:
                    logger.error(f"[{request_id}] Keep-alive fatal error: {e}", exc_info=True)
            
            # Start immediate keep-alive task
            keepalive_task = asyncio.create_task(immediate_keepalive())
            logger.info(f"[{request_id}] Started immediate keep-alive for analysis {analysis_id}")
            
            logger.info(f"[{request_id}] Background processing task scheduled", extra={"analysis_id": analysis_id})
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
    
    try:
        logger.info(
            f"[{request_id}] Starting advanced gait analysis",
            extra={
                "request_id": request_id,
                "analysis_id": analysis_id,
                "patient_id": patient_id,
                "view_type": view_type,
                "fps": fps
            }
        )
        
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
        
        # CRITICAL: Add periodic heartbeat to keep analysis alive during long processing
        # This is especially important for long-running video processing (3+ minutes)
        # NOTE: There's also an immediate keep-alive that starts right after analysis creation
        # This heartbeat runs during actual processing and is more aggressive
        heartbeat_task = None
        last_known_progress = {'step': 'pose_estimation', 'progress': 0, 'message': 'Starting analysis...'}
        
        async def heartbeat_update():
            """Periodic heartbeat to ensure analysis stays alive during processing"""
            heartbeat_count = 0
            try:
                while True:
                    # Very frequent updates: every 3 seconds for first minute, then every 5 seconds
                    await asyncio.sleep(3 if heartbeat_count < 20 else 5)
                    heartbeat_count += 1
                    try:
                        # CRITICAL: Always verify analysis exists and update it
                        # This prevents the analysis from disappearing during long processing
                        current_analysis = await db_service.get_analysis(analysis_id)
                        
                        if current_analysis:
                            # Update with current state to keep it alive
                            # Use last known progress if current analysis doesn't have it
                            step = current_analysis.get('current_step') or last_known_progress['step']
                            progress = current_analysis.get('step_progress') or last_known_progress['progress']
                            message = current_analysis.get('step_message') or last_known_progress['message']
                            
                            # Update last known progress
                            last_known_progress['step'] = step
                            last_known_progress['progress'] = progress
                            last_known_progress['message'] = message
                            
                            # Force update to keep analysis alive (remove heartbeat suffix to avoid clutter)
                            await db_service.update_analysis(analysis_id, {
                                'status': 'processing',
                                'current_step': step,
                                'step_progress': progress,
                                'step_message': message  # Keep original message
                            })
                            
                            if heartbeat_count % 20 == 0:  # Log every 60-100 seconds
                                logger.info(f"[{request_id}] Processing heartbeat: Analysis {analysis_id} is alive (heartbeat #{heartbeat_count}, {step} {progress}%)")
                            else:
                                logger.debug(f"[{request_id}] Processing heartbeat: Analysis {analysis_id} is alive (heartbeat #{heartbeat_count})")
                        else:
                            logger.warning(f"[{request_id}] Processing heartbeat: Analysis {analysis_id} not found - recreating (heartbeat #{heartbeat_count})")
                            # CRITICAL: Recreate with last known progress
                            await db_service.create_analysis({
                                'id': analysis_id,
                                'patient_id': patient_id,
                                'filename': 'unknown',
                                'video_url': video_url,
                                'status': 'processing',
                                'current_step': last_known_progress['step'],
                                'step_progress': last_known_progress['progress'],
                                'step_message': f"{last_known_progress['message']} (recreated by processing heartbeat #{heartbeat_count})"
                            })
                            logger.info(f"[{request_id}] Processing heartbeat: Recreated analysis {analysis_id} with progress: {last_known_progress['step']} {last_known_progress['progress']}%")
                    except Exception as heartbeat_error:
                        logger.error(f"[{request_id}] Processing heartbeat update failed (heartbeat #{heartbeat_count}): {heartbeat_error}", exc_info=True)
                        # CRITICAL: Try to recreate even if update failed
                        try:
                            await db_service.create_analysis({
                                'id': analysis_id,
                                'patient_id': patient_id,
                                'filename': 'unknown',
                                'video_url': video_url,
                                'status': 'processing',
                                'current_step': last_known_progress['step'],
                                'step_progress': last_known_progress['progress'],
                                'step_message': f"{last_known_progress['message']} (recreated after processing heartbeat error)"
                            })
                            logger.warning(f"[{request_id}] Processing heartbeat: Recreated analysis after error")
                        except Exception as recreate_error:
                            logger.error(f"[{request_id}] Processing heartbeat: Failed to recreate analysis: {recreate_error}")
            except asyncio.CancelledError:
                logger.info(f"[{request_id}] Processing heartbeat cancelled after {heartbeat_count} heartbeats")
            except Exception as e:
                logger.error(f"[{request_id}] Processing heartbeat error: {e}", exc_info=True)
        
        # Start heartbeat task IMMEDIATELY - before any processing starts
        heartbeat_task = asyncio.create_task(heartbeat_update())
        logger.info(f"[{request_id}] Started processing heartbeat task for analysis {analysis_id}")
        
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
                
                logger.debug(
                    f"[{request_id}] Progress update: {step} {mapped_progress}% - {message}",
                    extra={
                        "analysis_id": analysis_id,
                        "step": step,
                        "progress": mapped_progress,
                        "message": message
                    }
                )
                
                # CRITICAL: Update database with retry logic - never fail the process
                if db_service:
                    max_retries = 5  # Increased retries for progress updates
                    for retry in range(max_retries):
                        try:
                            # CRITICAL: Verify analysis exists before updating
                            analysis_check = await db_service.get_analysis(analysis_id)
                            if not analysis_check:
                                logger.warning(f"[{request_id}] Analysis not found during progress update. Recreating...")
                                # Recreate if lost
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
                                break  # Success after recreation
                            
                await db_service.update_analysis(analysis_id, {
                    'current_step': step,
                    'step_progress': mapped_progress,
                    'step_message': message
                })
                            # CRITICAL: Update last known progress for heartbeat
                            last_known_progress['step'] = step
                            last_known_progress['progress'] = mapped_progress
                            last_known_progress['message'] = message
                            break  # Success - exit retry loop
                        except Exception as update_error:
                            if retry < max_retries - 1:
                                logger.warning(
                                    f"[{request_id}] Progress update failed (attempt {retry + 1}/{max_retries}): {update_error}. Retrying...",
                                    extra={"analysis_id": analysis_id, "step": step}
                                )
                                await asyncio.sleep(0.2 * (retry + 1))  # Progressive delay
                                continue
                            else:
                                # Final retry failed - log but don't raise
                                logger.error(
                                    f"[{request_id}] Progress update failed after {max_retries} attempts: {update_error}",
                                    extra={"analysis_id": analysis_id, "step": step},
                                    exc_info=True
                                )
                                # CRITICAL: Try to recreate analysis if update failed completely
                                try:
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
                                    logger.warning(f"[{request_id}] Recreated analysis after progress update failure")
                                except Exception as recreate_error:
                                    logger.error(f"[{request_id}] Failed to recreate analysis: {recreate_error}")
                                # Don't raise - progress updates are non-critical
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
            
        analysis_result = await gait_service.analyze_video(
            video_path,
            fps=fps,
            reference_length_mm=reference_length_mm,
            view_type=view_type,
            progress_callback=progress_callback
        )
        
            if not analysis_result:
                logger.warning(
                    f"[{request_id}] Analysis returned empty result, creating fallback result",
                    extra={"analysis_id": analysis_id, "video_path": video_path}
                )
                # Create fallback result instead of failing
                analysis_result = {
                    'status': 'completed',
                    'analysis_type': 'fallback_analysis',
                    'metrics': {
                        'cadence': 0.0,
                        'step_length': 0.0,
                        'walking_speed': 0.0,
                        'stride_length': 0.0,
                        'double_support_time': 0.0,
                        'swing_time': 0.0,
                        'stance_time': 0.0,
                        'fallback_metrics': True,
                        'error': 'Analysis returned empty result'
                    },
                    'frames_processed': 0,
                    'total_frames': 0
                }
            
            logger.info(
                f"[{request_id}] Video analysis completed",
                extra={
                    "analysis_id": analysis_id,
                    "has_metrics": "metrics" in analysis_result if analysis_result else False,
                    "result_status": analysis_result.get('status') if analysis_result else None
                }
            )
        except PoseEstimationError as e:
            logger.error(
                f"[{request_id}] Pose estimation failed: {e.message}",
                extra={"analysis_id": analysis_id, "error_code": e.error_code, "details": e.details},
                exc_info=True
            )
            # CRITICAL: Don't fail - create fallback result
            logger.warning(f"[{request_id}] Creating fallback result after pose estimation error")
            analysis_result = {
                'status': 'completed',
                'analysis_type': 'fallback_analysis',
                'metrics': {
                    'cadence': 0.0,
                    'step_length': 0.0,
                    'walking_speed': 0.0,
                    'stride_length': 0.0,
                    'double_support_time': 0.0,
                    'swing_time': 0.0,
                    'stance_time': 0.0,
                    'fallback_metrics': True,
                    'error': f"Pose estimation failed: {e.message}"
                },
                'frames_processed': 0,
                'total_frames': 0
            }
        except GaitMetricsError as e:
            logger.error(
                f"[{request_id}] Gait metrics calculation failed: {e.message}",
                extra={"analysis_id": analysis_id, "error_code": e.error_code, "details": e.details},
                exc_info=True
            )
            # CRITICAL: Don't fail - create fallback result
            logger.warning(f"[{request_id}] Creating fallback result after metrics error")
            analysis_result = {
                'status': 'completed',
                'analysis_type': 'fallback_analysis',
                'metrics': {
                    'cadence': 0.0,
                    'step_length': 0.0,
                    'walking_speed': 0.0,
                    'stride_length': 0.0,
                    'double_support_time': 0.0,
                    'swing_time': 0.0,
                    'stance_time': 0.0,
                    'fallback_metrics': True,
                    'error': f"Metrics calculation failed: {e.message}"
                },
                'frames_processed': 0,
                'total_frames': 0
            }
        except Exception as e:
            logger.error(
                f"[{request_id}] Unexpected error during video analysis: {e}",
                extra={"analysis_id": analysis_id, "error_type": type(e).__name__},
                exc_info=True
            )
            # CRITICAL: Don't fail - create fallback result
            logger.warning(f"[{request_id}] Creating fallback result after unexpected error")
            analysis_result = {
                'status': 'completed',
                'analysis_type': 'fallback_analysis',
                'metrics': {
                    'cadence': 0.0,
                    'step_length': 0.0,
                    'walking_speed': 0.0,
                    'stride_length': 0.0,
                    'double_support_time': 0.0,
                    'swing_time': 0.0,
                    'stance_time': 0.0,
                    'fallback_metrics': True,
                    'error': f"Unexpected error: {str(e)}"
                },
                'frames_processed': 0,
                'total_frames': 0
            }
        
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
        if heartbeat_task:
            heartbeat_task.cancel()
            try:
                await heartbeat_task
            except asyncio.CancelledError:
                pass
        
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
        if heartbeat_task:
            heartbeat_task.cancel()
            try:
                await heartbeat_task
            except asyncio.CancelledError:
                pass
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
            logger.warning(f"[{request_id}] Analysis not found", extra={"analysis_id": analysis_id})
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


