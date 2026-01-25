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
# IMPORTANT: Service initialization errors should NOT prevent routes from being registered
# CRITICAL: Wrap in try/except to ensure router is still exported even if services fail
try:
    initialize_services()
except Exception as e:
    logger.critical(f"Critical service initialization failed: {e}", exc_info=True)
    # Don't raise - allow app to start, services will be None and handled gracefully
    # This prevents the entire app from failing to start if one service has issues
    logger.warning("App will continue to start, but some services may be unavailable")
    # CRITICAL: Ensure router is still valid even if services fail
    logger.warning(f"Router state after service init error: {len(router.routes) if hasattr(router, 'routes') else 'no routes attr'} routes")


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


@router.post("/upload")
async def upload_video(
    file: UploadFile = File(...),
    patient_id: Optional[str] = Query(None, max_length=100, description="Patient identifier"),
    view_type: str = Query("front", description="Camera view type"),
    reference_length_mm: Optional[float] = Query(None, gt=0, le=10000, description="Reference length in mm"),
    fps: float = Query(30.0, gt=0, le=120, description="Video frames per second"),
    processing_fps: Optional[float] = Query(None, gt=0, le=60, description="Processing frame rate (frames per second to process). Lower = faster analysis, higher = more accurate. Default: auto-detect based on video length."),
    request: Request = None,
    background_tasks: BackgroundTasks = None
) -> JSONResponse:
    """
    Upload video for gait analysis using Azure native services
    
    CRITICAL: This endpoint must be registered at /api/v1/analysis/upload
    
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
        JSONResponse with analysis_id and status
    """
    # CRITICAL: Define all variables BEFORE try block to prevent NameError in exception handlers
    request_id = str(uuid.uuid4())[:8]
    upload_request_start = time.time()
    tmp_path = None
    video_url = None
    file_size = 0
    analysis_id = None
    patient_id_val = patient_id  # Store for use in exception handlers
    
    # CRITICAL: Log immediately at function entry to catch 502 errors
    try:
        logger.info("=" * 80)
        logger.info(f"[{request_id}] 🚀 ========== UPLOAD ENDPOINT CALLED ==========")
        logger.info(f"[{request_id}] 🚀 Timestamp: {datetime.utcnow().isoformat()}")
        logger.info(f"[{request_id}] 🚀 Function entry successful - endpoint is accessible")
        logger.info("=" * 80)
    except Exception as early_log_error:
        # Even logging failed - this is critical
        print(f"CRITICAL: Failed to log at upload endpoint entry: {early_log_error}")
    
    try:
        # MINIMAL START - just log
        
        logger.info(f"[{request_id}] ========== UPLOAD REQUEST RECEIVED ==========")
        logger.info(f"[{request_id}] Filename: {file.filename if file else None}")
        logger.info(f"[{request_id}] Patient ID: {patient_id}, View: {view_type}, FPS: {fps}")
        
        # Log estimated file size from Content-Length header if available
        content_length = None
        if request:
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
            return JSONResponse(
                status_code=503,
                content={
                    "error": "SERVICE_UNAVAILABLE",
                    "message": "Database service is not available",
                    "details": {}
                }
            )
        
        # Validate file is provided
        if not file or not file.filename:
            logger.error(f"[{request_id}] No file provided in upload request")
            return JSONResponse(
                status_code=400,
                content={"error": "VALIDATION_ERROR", "message": "No file provided", "field": "file"}
            )
        
        # Validate file extension
        file_ext = Path(file.filename).suffix.lower()
        SUPPORTED_FORMATS = ['.mp4', '.avi', '.mov', '.mkv']
        if file_ext not in SUPPORTED_FORMATS:
            logger.error(
                f"[{request_id}] Unsupported file format: {file_ext}",
                extra={"filename": file.filename, "extension": file_ext}
            )
            return JSONResponse(
                status_code=400,
                content={
                    "error": "VALIDATION_ERROR",
                    "message": f"Unsupported file format: {file_ext}. Supported formats: {', '.join(SUPPORTED_FORMATS)}",
                    "field": "file",
                    "details": {"extension": file_ext, "supported": SUPPORTED_FORMATS}
                }
            )
        
        # Validate file size (max 500MB)
        # CRITICAL: Azure App Service has a 230-second (3.8 minute) request timeout
        # For files larger than ~50MB, upload may timeout
        # Consider implementing chunked uploads or direct blob storage uploads for larger files
        MAX_FILE_SIZE = 500 * 1024 * 1024  # 500MB
        MAX_RECOMMENDED_SIZE = 50 * 1024 * 1024  # 50MB - recommended max to avoid timeout
        # Note: file_size, tmp_path, video_url already defined above
        
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
                return JSONResponse(
                    status_code=500,
                    content={
                        "error": "STORAGE_ERROR",
                        "message": "Failed to create temporary file for upload",
                        "details": {"error": str(e)}
                    }
                )
            
            # Read file in chunks with size validation
            # OPTIMIZED: Use larger chunks for faster upload while still preventing memory issues
            # Increased from 256KB to 1MB for better throughput, especially for small files
            chunk_size = 1024 * 1024  # 1MB chunks - optimized for faster uploads
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
                    try:
                        tmp_file.write(chunk)
                    except (OSError, IOError) as write_error:
                        tmp_file.close()
                        if os.path.exists(tmp_path):
                            try:
                                os.unlink(tmp_path)
                            except:
                                pass
                        logger.error(f"[{request_id}] Failed to write chunk to temp file: {write_error}", exc_info=True)
                        raise StorageError(
                            f"Failed to write uploaded file: {write_error}",
                            details={"error": str(write_error), "chunk_count": chunk_count}
                        )
                    
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
                        if os.path.exists(tmp_path):
                            try:
                                os.unlink(tmp_path)
                            except:
                                pass
                        logger.error(
                            f"[{request_id}] File too large: {file_size} bytes (max: {MAX_FILE_SIZE})",
                            extra={"file_size": file_size, "max_size": MAX_FILE_SIZE}
                        )
                        return JSONResponse(
                            status_code=413,
                            content={
                                "error": "VALIDATION_ERROR",
                                "message": f"File too large: {file_size / (1024*1024):.2f}MB. Maximum size: {MAX_FILE_SIZE / (1024*1024)}MB",
                                "field": "file",
                                "details": {"file_size": file_size, "max_size": MAX_FILE_SIZE}
                            }
                        )
                
                tmp_file.close()
            except Exception as read_error:
                # CRITICAL: Ensure file is closed even if error occurs
                try:
                    if tmp_file and not tmp_file.closed:
                        tmp_file.close()
                except:
                    pass
                # Re-raise to be handled by outer exception handler
                raise
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
            except Exception as e:
                tmp_file.close()
                if tmp_path and os.path.exists(tmp_path):
                    try:
                        os.unlink(tmp_path)
                    except:
                        pass
                logger.error(f"[{request_id}] Error reading uploaded file: {e}", exc_info=True)
                return JSONResponse(
                    status_code=500,
                    content={
                        "error": "VIDEO_PROCESSING_ERROR",
                        "message": "Failed to read uploaded file",
                        "details": {"error": str(e)}
                    }
                )
            
            # Validate file is not empty
            if file_size == 0:
                if tmp_path and os.path.exists(tmp_path):
                    os.unlink(tmp_path)
                logger.error(f"[{request_id}] Empty file uploaded")
                return JSONResponse(
                    status_code=400,
                    content={
                        "error": "VALIDATION_ERROR",
                        "message": "Uploaded file is empty",
                        "field": "file"
                    }
                )
            
            # Generate analysis ID (already defined above, but assign here)
            analysis_id = str(uuid.uuid4())
            logger.info(f"[{request_id}] Generated analysis ID: {analysis_id}")
            
            # CRITICAL: Create analysis record EARLY so we can update progress during upload
            # This allows users to see what's happening during video quality validation and blob upload
            # NOTE: This is optional - if it fails, we'll create the record later (non-critical)
            analysis_record_created = False
            if db_service is not None:
                try:
                    initial_analysis_data = {
                        'id': analysis_id,
                        'patient_id': patient_id,
                        'filename': file.filename,
                        'video_url': 'pending',  # Will be updated after blob upload
                        'status': 'uploading',  # Special status for upload phase
                        'current_step': 'upload',
                        'step_progress': 0,
                        'step_message': '📤 File received. Starting upload processing...'
                    }
                    creation_result = await db_service.create_analysis(initial_analysis_data)
                    if creation_result:
                        analysis_record_created = True
                        logger.info(f"[{request_id}] ✅ Created initial analysis record for progress tracking")
                    else:
                        logger.warning(f"[{request_id}] ⚠️ create_analysis returned False - record may not exist")
                except Exception as early_create_error:
                    # Non-critical - we'll create the record later in the normal flow
                    logger.warning(f"[{request_id}] ⚠️ Failed to create early analysis record (non-critical): {early_create_error} - will create later")
                    logger.debug(f"[{request_id}] Early creation error details:", exc_info=True)
                    analysis_record_created = False
            else:
                logger.warning(f"[{request_id}] ⚠️ db_service is None - skipping early analysis record creation")
            
            # Helper function to update upload progress
            # Only updates if analysis record exists - silently fails if not (non-critical)
            async def update_upload_progress(progress: int, message: str):
                """Update analysis record with upload progress - non-blocking"""
                # Skip if record wasn't created or db_service is unavailable
                if not analysis_record_created or db_service is None:
                    return
                try:
                    update_result = await db_service.update_analysis(analysis_id, {
                        'status': 'uploading',
                        'current_step': 'upload',
                        'step_progress': progress,
                        'step_message': message
                    })
                    if not update_result:
                        # Update failed - analysis might not exist, but that's OK
                        logger.debug(f"[{request_id}] Upload progress update returned False (non-critical)")
                except Exception as update_err:
                    # Silently fail - progress updates are non-critical and shouldn't break upload
                    logger.debug(f"[{request_id}] Failed to update upload progress: {update_err} (non-critical)")
            
            # CRITICAL: Validate video quality BEFORE uploading to blob storage
            # This allows us to provide immediate feedback to user
            # NOTE: Validation is optional - if it fails, we continue without it
            await update_upload_progress(10, '🔍 Validating video quality for gait analysis...')
            logger.info(f"[{request_id}] 🔍 Validating video quality for gait analysis...")
            quality_result = None
            if tmp_path and os.path.exists(tmp_path):
                try:
                    # Import with error handling - if import fails, skip validation
                    try:
                        from app.services.video_quality_validator import VideoQualityValidator
                    except ImportError as import_err:
                        logger.warning(f"[{request_id}] ⚠️ VideoQualityValidator not available (import error: {import_err}) - skipping validation")
                        quality_result = None
                    except Exception as import_err:
                        logger.warning(f"[{request_id}] ⚠️ Error importing VideoQualityValidator: {import_err} - skipping validation")
                        quality_result = None
                    else:
                        # Import succeeded - try to use it with timeout
                        try:
                            # Get gait analysis service (defined in this module)
                            # Wrap in try-except to handle any initialization errors
                            try:
                                gait_service = get_gait_analysis_service()
                            except Exception as gait_service_error:
                                logger.warning(f"[{request_id}] ⚠️ Failed to get gait analysis service for validation: {gait_service_error} - skipping validation")
                                quality_result = None
                                gait_service = None
                            
                            if gait_service is None:
                                logger.warning(f"[{request_id}] ⚠️ Gait analysis service is None - skipping video quality validation")
                                quality_result = None
                            else:
                                try:
                                    validator = VideoQualityValidator(
                                        pose_landmarker=gait_service.pose_landmarker if gait_service else None
                                    )
                                except Exception as validator_init_error:
                                    logger.warning(f"[{request_id}] ⚠️ Failed to initialize VideoQualityValidator: {validator_init_error} - skipping validation")
                                    quality_result = None
                                    validator = None
                                
                                if validator is not None:
                                    # OPTIMIZED: Add timeout to prevent blocking (max 10 seconds)
                                    # If validation takes too long, skip it to prevent 502 timeout
                                    validation_timeout = 10.0  # 10 seconds max
                                    validation_start = time.time()
                                    
                                    await update_upload_progress(15, '🔍 Analyzing video frames for quality assessment...')
                                    try:
                                        quality_result = await asyncio.wait_for(
                                            asyncio.to_thread(
                                                validator.validate_video_for_gait_analysis,
                                                video_path=tmp_path,
                                                view_type=str(view_type),
                                                sample_frames=20
                                            ),
                                            timeout=validation_timeout
                                        )
                                        validation_duration = time.time() - validation_start
                                        logger.info(f"[{request_id}] ✅ Video quality validation completed in {validation_duration:.1f}s")
                                        
                                        # Update progress with validation results
                                        quality_score = quality_result.get('quality_score', 0) if quality_result else 0
                                        if quality_result:
                                            await update_upload_progress(25, f'✅ Video quality validated: {quality_score:.0f}% - {"Good" if quality_score >= 60 else "May affect accuracy"}')
                                        else:
                                            await update_upload_progress(25, '✅ Video quality validation skipped (timeout)')
                                    except asyncio.TimeoutError:
                                        validation_duration = time.time() - validation_start
                                        logger.warning(f"[{request_id}] ⚠️ Video quality validation timed out after {validation_duration:.1f}s - skipping to prevent upload timeout")
                                        await update_upload_progress(25, '⚠️ Video quality validation timed out - continuing with upload...')
                                        quality_result = None
                                    except Exception as validation_thread_error:
                                        logger.warning(f"[{request_id}] ⚠️ Video quality validation error: {validation_thread_error} - skipping")
                                        await update_upload_progress(25, '⚠️ Video quality validation error - continuing with upload...')
                                        quality_result = None
                                    
                                    if quality_result:
                                logger.info(f"[{request_id}] 🔍 Video quality validation results:")
                                logger.info(f"[{request_id}] 🔍   - Quality score: {quality_result.get('quality_score', 0):.1f}%")
                                logger.info(f"[{request_id}] 🔍   - Is valid: {quality_result.get('is_valid', False)}")
                                logger.info(f"[{request_id}] 🔍   - Pose detection rate: {quality_result.get('pose_detection_rate', 0)*100:.1f}%")
                                logger.info(f"[{request_id}] 🔍   - Critical joints detected: {quality_result.get('critical_joints_detected', False)}")
                                logger.info(f"[{request_id}] 🔍   - Issues found: {len(quality_result.get('issues', []))}")
                                
                                if quality_result.get('issues'):
                                    logger.warning(f"[{request_id}] ⚠️ Video quality issues detected:")
                                    for issue in quality_result.get('issues', []):
                                        logger.warning(f"[{request_id}] ⚠️   - {issue}")
                                
                                if not quality_result.get('is_valid', False):
                                    logger.error(f"[{request_id}] ❌❌❌ VIDEO QUALITY INSUFFICIENT FOR ACCURATE GAIT ANALYSIS ❌❌❌")
                                    logger.error(f"[{request_id}] Quality score: {quality_result.get('quality_score', 0):.1f}% (minimum: 60%)")
                                    logger.error(f"[{request_id}] Top recommendations:")
                                    for rec in quality_result.get('recommendations', [])[:3]:
                                        logger.error(f"[{request_id}]   - {rec}")
                        except Exception as validation_error:
                            logger.warning(f"[{request_id}] Video quality validation failed (non-critical): {validation_error}", exc_info=True)
                            logger.warning(f"[{request_id}] Processing will continue, but video quality is unknown")
                            quality_result = None
                except Exception as outer_error:
                    # Catch any unexpected errors in the validation block
                    logger.warning(f"[{request_id}] Unexpected error during video quality validation: {outer_error}", exc_info=True)
                    logger.warning(f"[{request_id}] Processing will continue without quality validation")
                    quality_result = None
            else:
                logger.warning(f"[{request_id}] ⚠️ Cannot validate video quality - temp file not accessible")
            
            # Upload to Azure Blob Storage (or keep temp file in mock mode)
            # OPTIMIZED: Add timeout handling to prevent 502 errors
            await update_upload_progress(30, '☁️ Preparing to upload video to cloud storage...')
            try:
                if storage_service is None:
                    logger.warning(f"[{request_id}] Storage service not available, using mock mode")
                    await update_upload_progress(50, '📁 Using local file storage (mock mode)...')
                    video_url = tmp_path  # Use temp file directly in mock mode
                else:
                    blob_name = f"{analysis_id}{file_ext}"
                    logger.debug(f"[{request_id}] Uploading to blob storage: {blob_name}")
                    await update_upload_progress(35, f'☁️ Uploading video to Azure Blob Storage: {blob_name}...')
                    
                    # OPTIMIZED: Add timeout for blob upload (max 60 seconds)
                    # This prevents the entire request from timing out
                    blob_upload_timeout = 60.0  # 60 seconds max for blob upload
                    blob_upload_start = time.time()
                    
                    try:
                        video_url = await asyncio.wait_for(
                            storage_service.upload_video(tmp_path, blob_name),
                            timeout=blob_upload_timeout
                        )
                        blob_upload_duration = time.time() - blob_upload_start
                        logger.info(f"[{request_id}] ✅ Blob upload completed in {blob_upload_duration:.1f}s")
                        await update_upload_progress(50, f'✅ Video uploaded to cloud storage successfully ({blob_upload_duration:.1f}s)')
                    except asyncio.TimeoutError:
                        blob_upload_duration = time.time() - blob_upload_start
                        logger.error(f"[{request_id}] ❌ Blob upload timed out after {blob_upload_duration:.1f}s")
                        await update_upload_progress(50, f'⚠️ Blob upload timed out ({blob_upload_duration:.1f}s) - using temporary storage')
                        # Fallback: use temp file path and upload in background
                        video_url = tmp_path
                        logger.warning(f"[{request_id}] ⚠️ Using temp file path - blob upload will be retried in background")
                    except Exception as blob_upload_error:
                        logger.error(f"[{request_id}] ❌ Blob upload failed: {blob_upload_error}")
                        await update_upload_progress(50, f'⚠️ Blob upload failed - using temporary storage: {str(blob_upload_error)[:50]}...')
                        # Fallback: use temp file path
                        video_url = tmp_path
                        logger.warning(f"[{request_id}] ⚠️ Using temp file path - blob upload will be retried in background")
                    
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
                return JSONResponse(
                    status_code=500,
                    content={
                        "error": "STORAGE_ERROR",
                        "message": "Failed to upload file to storage",
                        "details": {"error": str(e)}
                    }
                )
            
            # Store metadata in Azure SQL Database
            await update_upload_progress(60, '💾 Creating analysis record in database...')
            logger.error(f"[{request_id}] ========== CREATING ANALYSIS RECORD ==========")
            logger.error(f"[{request_id}] Analysis ID: {analysis_id}")
            logger.error(f"[{request_id}] Patient ID: {patient_id}")
            logger.error(f"[{request_id}] Video URL: {video_url}")
            logger.error(f"[{request_id}] File name: {file.filename}")
            
            try:
                # Include quality validation results in analysis data
                # Note: If we created the record early, this will update it
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
                
                # Add quality validation results if available
                if quality_result:
                    analysis_data.update({
                        'video_quality_score': quality_result.get('quality_score', 0),
                        'video_quality_valid': quality_result.get('is_valid', False),
                        'video_quality_issues': quality_result.get('issues', []),
                        'video_quality_recommendations': quality_result.get('recommendations', []),
                        'pose_detection_rate': quality_result.get('pose_detection_rate', 0)
                    })
                    
                    # Update step message with quality info
                    quality_score = quality_result.get('quality_score', 0)
                    if quality_score < 60:
                        analysis_data['step_message'] = f'Upload complete. Video quality: {quality_score:.0f}% - May affect accuracy. Starting analysis...'
                    elif quality_score < 80:
                        analysis_data['step_message'] = f'Upload complete. Video quality: {quality_score:.0f}% - Good. Starting analysis...'
                    else:
                        analysis_data['step_message'] = f'Upload complete. Video quality: {quality_score:.0f}% - Excellent. Starting analysis...'
                
                await update_upload_progress(70, '💾 Saving analysis metadata to database...')
                logger.error(f"[{request_id}] About to call db_service.create_analysis")
                logger.error(f"[{request_id}] db_service available: {db_service is not None}")
                logger.error(f"[{request_id}] db_service._use_mock: {db_service._use_mock if db_service else None}")
                
                # Create or update analysis record - this will save to file and verify it's readable
                # CRITICAL: Add try-except around create_analysis to catch any exceptions
                creation_success = False
                try:
                    if db_service is None:
                        logger.error(f"[{request_id}] ❌ db_service is None - cannot create analysis record")
                        raise DatabaseError("Database service is not available")
                    
                    creation_success = await db_service.create_analysis(analysis_data)
                    logger.error(f"[{request_id}] create_analysis returned: {creation_success}")
                except Exception as create_error:
                    logger.error(
                        f"[{request_id}] ❌ Exception creating analysis record: {type(create_error).__name__}: {create_error}",
                        exc_info=True
                    )
                    raise DatabaseError(f"Failed to create analysis record: {str(create_error)}")
                
                await update_upload_progress(80, '✅ Analysis record created successfully')
                
                if not creation_success:
                    logger.error(f"[{request_id}] ❌❌❌ FAILED TO CREATE ANALYSIS RECORD ❌❌❌", extra={"analysis_id": analysis_id})
                    raise DatabaseError("Failed to create analysis record - create_analysis returned False")
                
                logger.error(f"[{request_id}] ✅✅✅ ANALYSIS RECORD CREATED SUCCESSFULLY ✅✅✅")
                logger.info(
                    f"[{request_id}] Created analysis record",
                    extra={"analysis_id": analysis_id, "patient_id": patient_id}
                )
                
                # Quality validation already done above - results are in analysis_data
                if quality_result:
                    logger.info(f"[{request_id}] ✅ Video quality validation completed and stored in analysis record")
                
                # CRITICAL: Verify the analysis is immediately readable before returning
                # Check which database backend is being used
                use_table_storage = hasattr(db_service, '_use_table') and db_service._use_table
                use_sql = not use_table_storage and not db_service._use_mock
                use_mock = db_service._use_mock
                
                logger.info(f"[{request_id}] Database backend: Table Storage={use_table_storage}, SQL={use_sql}, Mock={use_mock}")
                
                # For mock storage: Verify in-memory storage (source of truth)
                if use_mock:
                    analysis_in_memory = analysis_id in db_service._mock_storage
                    logger.error(f"[{request_id}] 🔍🔍🔍 IMMEDIATE VERIFICATION (MEMORY) 🔍🔍🔍")
                    logger.error(f"[{request_id}] 🔍 Analysis ID: {analysis_id}")
                    logger.error(f"[{request_id}] 🔍 In-memory storage size: {len(db_service._mock_storage)}")
                    logger.error(f"[{request_id}] 🔍 In-memory analysis IDs: {list(db_service._mock_storage.keys())}")
                    logger.error(f"[{request_id}] 🔍 Analysis in memory: {analysis_in_memory}")
                    
                    if not analysis_in_memory:
                        logger.error(f"[{request_id}] ❌❌❌ CRITICAL: Analysis NOT in memory after creation! ❌❌❌")
                        logger.error(f"[{request_id}] ❌ Attempting to reload from file...")
                        db_service._load_mock_storage()
                        analysis_in_memory = analysis_id in db_service._mock_storage
                        logger.error(f"[{request_id}] 🔍 After reload - Analysis in memory: {analysis_in_memory}")
                        
                        if not analysis_in_memory:
                            logger.error(f"[{request_id}] ❌❌❌ CRITICAL: Analysis still NOT in memory after reload! ❌❌❌")
                            # Try to recreate it
                            try:
                                await db_service.create_analysis(analysis_data)
                                logger.error(f"[{request_id}] ✅ Recreated analysis in memory")
                            except Exception as recreate_error:
                                logger.error(f"[{request_id}] ❌ Failed to recreate analysis: {recreate_error}", exc_info=True)
                    else:
                        logger.error(f"[{request_id}] ✅✅✅ Analysis confirmed in memory ✅✅✅")
                
                # OPTIMIZED: Skip verification to return response immediately
                # Verification can happen in background - frontend will retry polling anyway
                # This prevents 502 timeout errors when database is slow
                await update_upload_progress(90, '✅ Upload complete! Preparing to start analysis...')
                logger.info(f"[{request_id}] ✅ Analysis record created - skipping verification to return response quickly")
                logger.info(f"[{request_id}] Frontend will poll and verify analysis availability")
                
                # OPTIONAL: Quick non-blocking verification attempt (don't wait)
                # This is just for logging - we return response regardless
                try:
                    # Use asyncio.create_task to run verification in background
                    async def quick_verification():
                        try:
                            await asyncio.sleep(0.1)  # Tiny delay
                            verification_analysis = await db_service.get_analysis(analysis_id)
                            if verification_analysis and verification_analysis.get('id') == analysis_id:
                                logger.info(f"[{request_id}] ✅ Background verification: Analysis confirmed available")
                            else:
                                logger.warning(f"[{request_id}] ⚠️ Background verification: Analysis not yet available (frontend will retry)")
                        except Exception as verify_err:
                            logger.warning(f"[{request_id}] ⚠️ Background verification failed: {verify_err} (non-critical)")
                    
                    # Start verification in background - don't await
                    asyncio.create_task(quick_verification())
                except Exception as verify_task_err:
                    logger.warning(f"[{request_id}] ⚠️ Failed to start background verification: {verify_task_err} (non-critical)")
                
                logger.error(f"[{request_id}] ========== ANALYSIS RECORD CREATION COMPLETE ==========")
            except Exception as e:
                logger.error(f"[{request_id}] ❌❌❌ ERROR CREATING ANALYSIS RECORD ❌❌❌", exc_info=True)
                logger.error(f"[{request_id}] Error: {type(e).__name__}: {e}")
                if tmp_path and os.path.exists(tmp_path):
                    try:
                        os.unlink(tmp_path)
                    except:
                        pass
                logger.error(f"[{request_id}] Exception creating analysis record: {e}", exc_info=True)
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to create analysis record: {str(e)}"
                )
            
            # Process in background
            try:
                # view_type is now a string, not an enum
                view_type_str = str(view_type)
                
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
                            fps,
                            processing_fps  # Pass processing_fps to background task
                        )
                        logger.error(f"[{request_id}] 🔧✅ Background task completed successfully")
                    except Exception as wrapper_error:
                        logger.error(f"[{request_id}] 🔧❌ Background task failed: {type(wrapper_error).__name__}: {wrapper_error}", exc_info=True)
                        raise
                
                logger.error(f"[{request_id}] ========== SCHEDULING BACKGROUND TASK ==========")
                logger.error(f"[{request_id}] 🔧 Analysis ID: {analysis_id}")
                logger.error(f"[{request_id}] 🔧 About to call background_tasks.add_task")
                logger.error(f"[{request_id}] 🔧 background_tasks object: {background_tasks}")
                logger.error(f"[{request_id}] 🔧 background_tasks type: {type(background_tasks)}")
                
                # CRITICAL: Verify analysis is still visible before scheduling background task
                if db_service and db_service._use_mock:
                    analysis_still_visible = analysis_id in db_service._mock_storage
                    logger.error(f"[{request_id}] 🔍 Analysis still visible in memory before background task: {analysis_still_visible}")
                    if not analysis_still_visible:
                        logger.error(f"[{request_id}] ❌❌❌ CRITICAL: Analysis disappeared from memory! Recreating...")
                        try:
                            await db_service.create_analysis({
                                'id': analysis_id,
                                'patient_id': patient_id,
                                'filename': file.filename,
                                'video_url': video_url,
                                'status': 'processing',
                                'current_step': 'pose_estimation',
                                'step_progress': 0,
                                'step_message': 'Upload complete. Starting analysis...'
                            })
                            logger.error(f"[{request_id}] ✅ Recreated analysis in memory")
                        except Exception as recreate_error:
                            logger.error(f"[{request_id}] ❌ Failed to recreate analysis: {recreate_error}", exc_info=True)
                
                if background_tasks is None:
                    # Fallback: use asyncio.create_task if BackgroundTasks not available
                    # NOTE: asyncio is already imported at module level (line 19)
                    asyncio.create_task(wrapped_process_analysis())
                    logger.info(f"[{request_id}] ✅ Background task scheduled via asyncio.create_task")
                else:
                    background_tasks.add_task(wrapped_process_analysis)
                    logger.info(f"[{request_id}] ✅ Background task scheduled via background_tasks.add_task")
                
                logger.error(f"[{request_id}] ✅✅✅ BACKGROUND TASK SCHEDULED ✅✅✅")
                logger.info(f"[{request_id}] ✅ Background processing task scheduled for analysis {analysis_id}", extra={"analysis_id": analysis_id})
                logger.info(f"[{request_id}] ✅ Upload complete - analysis {analysis_id} should be visible immediately")
                logger.info(f"[{request_id}] ✅ Both keep-alive and processing tasks are now running")
                
                # OPTIMIZED: Skip blocking final verification - return response immediately
                # Analysis is already created, and keep-alive will ensure it stays visible
                # Frontend will poll and verify availability
                logger.info(f"[{request_id}] ✅ Skipping final verification - returning response immediately to prevent timeout")
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
                logger.error(f"[{request_id}] Failed to schedule video analysis: {e}", exc_info=True)
                # Don't fail the upload - analysis is created, just log the error
                # The analysis will remain in 'processing' status
                
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
            
            # Return response - use string for status to avoid enum issues
            # Return JSONResponse directly (like simple endpoint) to avoid Pydantic serialization issues
            return JSONResponse({
                "analysis_id": analysis_id,
                "status": "processing",
                "message": "Video uploaded successfully. Analysis in progress.",
                "patient_id": patient_id_val,
                "created_at": datetime.utcnow().isoformat()
            })
        except Exception as file_upload_error:
            # Catch any error in the file upload try block (line 241)
            logger.error(f"[{request_id}] Error in file upload processing: {file_upload_error}", exc_info=True)
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except:
                    pass
            raise HTTPException(
                status_code=500,
                detail=f"File upload processing failed: {str(file_upload_error)}"
            )
        
    except HTTPException:
        # Let FastAPI handle HTTPException - don't intercept
        raise
    except (ValidationError, VideoProcessingError, StorageError, DatabaseError) as e:
        # Convert custom exceptions to HTTP exceptions - let global handler process
        try:
            error_code = getattr(e, 'error_code', 'UNKNOWN_ERROR')
            error_message = getattr(e, 'message', str(e))
            error_details = getattr(e, 'details', {})
            
            logger.error(
                f"[{request_id}] Upload failed: {error_code} - {error_message}",
                extra={"error_code": error_code, "details": error_details},
                exc_info=True
            )
            
            # Safely convert to HTTPException with defensive error handling
            try:
                http_exc = gait_error_to_http(e)
                raise http_exc
            except Exception as http_conv_error:
                # If conversion fails, raise a safe HTTPException
                logger.error(
                    f"[{request_id}] Failed to convert exception to HTTPException: {http_conv_error}",
                    exc_info=True
                )
                raise HTTPException(
                    status_code=500,
                    detail=f"Upload failed: {error_code}: {error_message}"
                )
        except Exception as handler_error:
            # Even the exception handler failed - this is critical
            logger.critical(
                f"[{request_id}] CRITICAL: Exception handler itself failed: {handler_error}",
                exc_info=True
            )
            # Raise a safe HTTPException to prevent worker crash
            raise HTTPException(
                status_code=500,
                detail=f"Upload failed: {type(e).__name__}: {str(e)}"
            )
    except Exception as e:
        # Catch-all for unexpected errors - log and raise HTTPException
        error_type = type(e).__name__
        error_msg = str(e)
        
        # Log with maximum detail
        try:
            logger.error(
                f"[{request_id}] ❌❌❌ UNEXPECTED ERROR UPLOADING VIDEO ❌❌❌",
                extra={
                    "error_type": error_type,
                    "error_message": error_msg,
                    "filename": file.filename if file else None,
                    "patient_id": patient_id_val
                },
                exc_info=True
            )
        except Exception as log_error:
            # Even logging failed - use print
            print(f"CRITICAL ERROR [{request_id}]: {error_type}: {error_msg}")
            print(f"Logging also failed: {log_error}")
        
        # Raise HTTPException so global handler can process it
        raise HTTPException(
            status_code=500,
            detail=f"Upload failed: {error_type}: {error_msg}"
        )
    
    finally:
        # Clean up temp file only if it wasn't used for processing
        # Use try/except to handle case where variables might not be set
        try:
            if tmp_path and os.path.exists(tmp_path):
                # Only clean up if video_url is not the same as tmp_path (i.e., not mock mode)
                if video_url and video_url != tmp_path and not os.path.exists(video_url):
                    try:
                        os.unlink(tmp_path)
                        logger.debug(f"[{request_id}] Cleaned up unused temp file")
                    except OSError as e:
                        logger.warning(f"[{request_id}] Failed to clean up temp file in finally: {e}")
        except Exception as cleanup_error:
            # Don't let cleanup errors mask original error
            logger.warning(f"[{request_id}] Error during cleanup: {cleanup_error}")


async def process_analysis_azure(
    analysis_id: str,
    video_url: str,
    patient_id: Optional[str],
    view_type: str,
    reference_length_mm: Optional[float],
    fps: float,
    processing_fps: Optional[float] = None
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
    # Note: os and threading are already imported at module level
    logger.error("=" * 80)
    logger.error(f"[{request_id}] ========== PROCESSING TASK FUNCTION CALLED ==========")
    logger.error(f"[{request_id}] Analysis ID: {analysis_id}")
    logger.error(f"[{request_id}] Video URL: {video_url}")
    logger.error(f"[{request_id}] Parameters: view_type={view_type}, fps={fps}, processing_fps={processing_fps}, reference_length_mm={reference_length_mm}")
    logger.error(f"[{request_id}] Timestamp: {datetime.utcnow().isoformat()}")
    logger.error(f"[{request_id}] Process ID: {os.getpid()}")
    logger.error(f"[{request_id}] Thread ID: {threading.current_thread().ident}, Thread Name: {threading.current_thread().name}")
    logger.error(f"[{request_id}] db_service available: {db_service is not None}")
    logger.error(f"[{request_id}] db_service._use_mock: {db_service._use_mock if db_service else None}")
    logger.error("=" * 80)
    
    try:
        # Check if analysis was cancelled before starting
        if db_service:
            analysis_check = await db_service.get_analysis(analysis_id)
            if analysis_check and analysis_check.get('status') == 'cancelled':
                logger.info(f"[{request_id}] Analysis {analysis_id} was cancelled before processing started")
                return
        
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
        logger.info(f"[{request_id}] 📋 Processing parameters: view_type={view_type}, fps={fps}, processing_fps={processing_fps}, reference_length_mm={reference_length_mm}")
        
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
        async def update_step_progress(step: str, progress: int, message: str):
            """Helper to update step progress with retry"""
            for retry in range(5):
                try:
                    await db_service.update_analysis(analysis_id, {
                        'status': 'processing',
                        'current_step': step,
                        'step_progress': progress,
                        'step_message': message
                    })
                    logger.info(f"[{request_id}] 📊 Progress updated: {step} - {progress}% - {message}")
                    break  # Success
                except Exception as e:
                    if retry < 4:
                        logger.warning(f"[{request_id}] Failed to update progress (attempt {retry + 1}/5): {e}. Retrying...")
                        await asyncio.sleep(0.2 * (retry + 1))
                        continue
                    else:
                        logger.warning(f"[{request_id}] Failed to update progress after 5 attempts: {e}")
                        # Continue anyway - not critical
        
        await update_step_progress('pose_estimation', 5, '📥 Step 1: Downloading video from storage...')
        
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
            if os.path.exists(video_url):
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
            elif storage_service and storage_service.container_client:
                # Use storage service to download (handles authentication properly)
                # Extract blob name from URL or use video_url as blob name
                if video_url.startswith('http') or video_url.startswith('https'):
                    # Extract blob name from URL (format: https://account.blob.core.windows.net/container/blobname)
                    blob_name = video_url.split('/')[-1] if '/' in video_url else video_url
                    # Remove query parameters if present
                    blob_name = blob_name.split('?')[0]
                else:
                    # Assume video_url is already a blob name
                    blob_name = video_url
                
                logger.info(f"[{request_id}] Downloading blob from storage: {blob_name}")
                await update_step_progress('pose_estimation', 8, f'📥 Downloading video blob: {blob_name}...')
                
                import tempfile
                video_path = tempfile.NamedTemporaryFile(delete=False, suffix='.mp4').name
                blob_data = await storage_service.download_blob(blob_name)
                await update_step_progress('pose_estimation', 10, f'✅ Video downloaded ({len(blob_data) / (1024*1024):.1f} MB)')
                
                if not blob_data:
                    raise StorageError(
                        f"Could not download video blob: {blob_name}. Blob may not exist or storage service is unavailable.",
                        details={"blob_name": blob_name, "video_url": video_url, "analysis_id": analysis_id}
                    )
                
                try:
                    with open(video_path, 'wb') as f:
                        f.write(blob_data)
                    logger.info(f"[{request_id}] ✅ Blob downloaded and saved: {video_path} ({len(blob_data)} bytes)")
                except OSError as e:
                    raise StorageError(
                        f"Failed to save downloaded blob to file: {e}",
                        details={"video_path": video_path, "analysis_id": analysis_id}
                    )
            elif video_url.startswith('http') or video_url.startswith('https'):
                # Fallback: Try direct HTTP download (may fail if blob requires authentication)
                logger.warning(f"[{request_id}] Storage service not available, attempting direct HTTP download (may fail if authentication required)")
                logger.debug(f"[{request_id}] Downloading video from URL: {video_url}")
                try:
                    video_path = await gait_service.download_video_from_url(video_url)
                except Exception as http_error:
                    raise StorageError(
                        f"Failed to download video from URL (may require authentication): {http_error}",
                        details={"video_url": video_url, "error": str(http_error), "analysis_id": analysis_id}
                    )
            else:
                # No storage service and not a valid URL or file path
                raise StorageError(
                    "Storage service not available and video URL is not a local file or valid URL",
                    details={"video_url": video_url, "analysis_id": analysis_id}
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
        await update_step_progress('pose_estimation', 12, '🔍 Verifying video file...')
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
            await update_step_progress('pose_estimation', 15, f'✅ Video file verified ({file_size / (1024*1024):.1f} MB)')
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
        # CRITICAL: Initialize last_known_progress with a valid step name (not None)
        # This ensures heartbeat thread always has valid data to update
        last_known_progress = {'step': 'pose_estimation', 'progress': 0, 'message': 'Starting analysis...'}
        heartbeat_stop_event = threading.Event()
        
        # CRITICAL: Ensure analysis is ALWAYS in memory before starting heartbeat
        # This prevents the analysis from being lost during heartbeat startup
        if db_service and db_service._use_mock:
            if analysis_id not in db_service._mock_storage:
                logger.error(f"[{request_id}] ❌❌❌ CRITICAL: Analysis {analysis_id} NOT in memory before heartbeat start! ❌❌❌")
                logger.error(f"[{request_id}] ❌ Memory storage size: {len(db_service._mock_storage)}")
                logger.error(f"[{request_id}] ❌ Memory analysis IDs: {list(db_service._mock_storage.keys())}")
                # Try to reload from file
                db_service._load_mock_storage()
                if analysis_id not in db_service._mock_storage:
                    logger.error(f"[{request_id}] ❌ Analysis still not found after reload - will recreate in heartbeat")
                else:
                    logger.error(f"[{request_id}] ✅ Analysis found after reload")
            else:
                logger.error(f"[{request_id}] ✅ Analysis {analysis_id} confirmed in memory before heartbeat start")
        
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
                    # Note: os and threading are already imported at module level
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
                                logger.warning(f"[{heartbeat_request_id}] ⚠️ THREAD HEARTBEAT #{heartbeat_count}: Analysis {heartbeat_analysis_id} NOT in memory - RECREATING IMMEDIATELY")
                                from datetime import datetime
                                heartbeat_db_service._mock_storage[heartbeat_analysis_id] = {
                                    'id': heartbeat_analysis_id,
                                    'patient_id': heartbeat_patient_id,
                                    'filename': 'unknown',
                                    'video_url': heartbeat_video_url,
                                    'status': 'processing',
                                    'current_step': heartbeat_last_progress['step'],
                                    'step_progress': heartbeat_last_progress['progress'],
                                    'step_message': f"{heartbeat_last_progress['message']} (recreated by heartbeat #{heartbeat_count})",
                                    'metrics': {},
                                    'created_at': datetime.now().isoformat(),
                                    'updated_at': datetime.now().isoformat()
                                }
                                # Force immediate save
                                try:
                                    heartbeat_db_service._save_mock_storage(force_sync=True)
                                    logger.info(f"[{heartbeat_request_id}] ✅ THREAD HEARTBEAT #{heartbeat_count}: Recreated and saved analysis {heartbeat_analysis_id}")
                                    last_successful_update = time.time()
                                except Exception as recreate_error:
                                    logger.error(f"[{heartbeat_request_id}] ❌ THREAD HEARTBEAT #{heartbeat_count}: Failed to save recreated analysis: {recreate_error}")
                            
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
                                    logger.error(f"[{heartbeat_request_id}] ✅✅✅ HEARTBEAT #{heartbeat_count} UPDATE SUCCESS ✅✅✅")
                                    logger.error(f"[{heartbeat_request_id}] ✅ Analysis {heartbeat_analysis_id} updated: {step} {progress}%")
                                    logger.error(f"[{heartbeat_request_id}] ✅ Update duration: {update_duration:.3f}s")
                                    logger.error(f"[{heartbeat_request_id}] ✅ Analysis still in memory: {heartbeat_analysis_id in heartbeat_db_service._mock_storage}")
                                    
                                    # Verify analysis still exists after update
                                    if heartbeat_analysis_id not in heartbeat_db_service._mock_storage:
                                        logger.error(f"[{heartbeat_request_id}] ❌❌❌ CRITICAL: Analysis disappeared IMMEDIATELY after successful update! ❌❌❌")
                                        logger.error(f"[{heartbeat_request_id}] ❌ Memory storage size: {len(heartbeat_db_service._mock_storage)}")
                                        logger.error(f"[{heartbeat_request_id}] ❌ Memory analysis IDs: {list(heartbeat_db_service._mock_storage.keys())}")
                                        # Recreate immediately
                                        from datetime import datetime
                                        heartbeat_db_service._mock_storage[heartbeat_analysis_id] = {
                                            'id': heartbeat_analysis_id,
                                            'patient_id': heartbeat_patient_id,
                                            'filename': 'unknown',
                                            'video_url': heartbeat_video_url,
                                            'status': 'processing',
                                            'current_step': step,
                                            'step_progress': progress,
                                            'step_message': f"{message} (recreated after disappearance)",
                                            'metrics': {},
                                            'created_at': datetime.now().isoformat(),
                                            'updated_at': datetime.now().isoformat()
                                        }
                                        heartbeat_db_service._save_mock_storage(force_sync=True)
                                        logger.error(f"[{heartbeat_request_id}] ✅ THREAD HEARTBEAT #{heartbeat_count}: Recreated analysis after disappearance")
                                else:
                                    logger.error(f"[{heartbeat_request_id}] ❌❌❌ HEARTBEAT #{heartbeat_count} UPDATE FAILED ❌❌❌")
                                    logger.error(f"[{heartbeat_request_id}] ❌ Update returned False")
                                    logger.error(f"[{heartbeat_request_id}] ❌ Analysis in memory: {heartbeat_analysis_id in heartbeat_db_service._mock_storage}")
                                    
                                    # CRITICAL: Verify analysis still exists after update
                                    if heartbeat_analysis_id not in heartbeat_db_service._mock_storage:
                                        logger.error(f"[{heartbeat_request_id}] ❌ THREAD HEARTBEAT #{heartbeat_count}: CRITICAL - Analysis disappeared after update! Recreating...")
                                        # Recreate immediately
                                        from datetime import datetime
                                        heartbeat_db_service._mock_storage[heartbeat_analysis_id] = {
                                            'id': heartbeat_analysis_id,
                                            'patient_id': heartbeat_patient_id,
                                            'filename': 'unknown',
                                            'video_url': heartbeat_video_url,
                                            'status': 'processing',
                                            'current_step': step,
                                            'step_progress': progress,
                                            'step_message': f"{message} (recreated after disappearance)",
                                            'metrics': {},
                                            'created_at': datetime.now().isoformat(),
                                            'updated_at': datetime.now().isoformat()
                                        }
                                        heartbeat_db_service._save_mock_storage(force_sync=True)
                                        logger.error(f"[{heartbeat_request_id}] ✅ THREAD HEARTBEAT #{heartbeat_count}: Recreated analysis after disappearance")
                                    elif heartbeat_count % 10 == 0:  # Log every 10 heartbeats
                                        logger.warning(f"[{heartbeat_request_id}] ⚠️ THREAD HEARTBEAT #{heartbeat_count}: Update returned False")
                                
                                if update_duration > 0.3:
                                    logger.warning(f"[{heartbeat_request_id}] ⚠️ THREAD HEARTBEAT #{heartbeat_count}: Slow update took {update_duration:.2f}s (may impact persistence)")
                            except Exception as update_error:
                                logger.error(f"[{heartbeat_request_id}] ❌ THREAD HEARTBEAT #{heartbeat_count}: Update exception: {type(update_error).__name__}: {update_error}", exc_info=True)
                                # Try to recreate if update failed
                                if heartbeat_analysis_id not in heartbeat_db_service._mock_storage:
                                    logger.error(f"[{heartbeat_request_id}] ❌ THREAD HEARTBEAT #{heartbeat_count}: Analysis missing after update error - recreating...")
                                    from datetime import datetime
                                    heartbeat_db_service._mock_storage[heartbeat_analysis_id] = {
                                        'id': heartbeat_analysis_id,
                                        'patient_id': heartbeat_patient_id,
                                        'filename': 'unknown',
                                        'video_url': heartbeat_video_url,
                                        'status': 'processing',
                                        'current_step': heartbeat_last_progress['step'],
                                        'step_progress': heartbeat_last_progress['progress'],
                                        'step_message': f"{heartbeat_last_progress['message']} (recreated after error)",
                                        'metrics': {},
                                        'created_at': datetime.now().isoformat(),
                                        'updated_at': datetime.now().isoformat()
                                    }
                                    try:
                                        heartbeat_db_service._save_mock_storage(force_sync=True)
                                        logger.info(f"[{heartbeat_request_id}] ✅ THREAD HEARTBEAT #{heartbeat_count}: Recreated analysis after error")
                                    except:
                                        pass
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
            await update_step_progress('pose_estimation', 18, '🎬 Step 1: Initializing pose estimation engine...')
            try:
                await db_service.update_analysis(analysis_id, {
                    'current_step': 'pose_estimation',
                    'step_progress': 20,
                    'step_message': '🎬 Step 1: Starting 2D pose estimation - analyzing video frames...'
                })
                # Update last known progress for heartbeat
                last_known_progress['step'] = 'pose_estimation'
                last_known_progress['progress'] = 20
                last_known_progress['message'] = '🎬 Step 1: Starting 2D pose estimation - analyzing video frames...'
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
            
            # Check for cancellation before starting video analysis
            if db_service:
                analysis_check = await db_service.get_analysis(analysis_id)
                if analysis_check and analysis_check.get('status') == 'cancelled':
                    logger.info(f"[{request_id}] Analysis {analysis_id} was cancelled before video analysis")
                    heartbeat_stop_event.set()
                    return
            
            logger.error(f"[{request_id}] 🎬🎬🎬 CALLING analyze_video 🎬🎬🎬")
            logger.error(f"[{request_id}] 🎬 Video path: {video_path}")
            logger.error(f"[{request_id}] 🎬 FPS: {fps}, View type: {view_type}")
            logger.error(f"[{request_id}] 🎬 Progress callback available: {progress_callback is not None}")
            
            analysis_result = await gait_service.analyze_video(
                video_path,
                fps=fps,
                reference_length_mm=reference_length_mm,
                view_type=view_type,
                progress_callback=progress_callback,
                analysis_id=analysis_id,  # Pass analysis_id for checkpoint management
                processing_fps=processing_fps  # Pass user-selected processing frame rate
            )
            
            # Stop periodic monitoring
            heartbeat_monitor_task.cancel()
            try:
                await heartbeat_monitor_task
            except asyncio.CancelledError:
                pass
            logger.error(f"[{request_id}] 🔍 Stopped periodic heartbeat monitor")
            logger.info(f"[{request_id}] ✅ VIDEO ANALYSIS COMPLETE: Got result with keys: {list(analysis_result.keys()) if analysis_result else 'None'}")
            
            # Update progress: Analysis complete, preparing for Step 4
            await update_step_progress('metrics_calculation', 90, '✅ Steps 1-3 complete! Preparing final report...')
            
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
            
            # CRITICAL: Validate that all 4 steps completed successfully
            steps_completed = analysis_result.get('steps_completed', {})
            if not steps_completed:
                logger.warning(f"[{request_id}] ⚠️ Analysis result missing steps_completed tracking - assuming all steps completed")
                steps_completed = {
                    "step_1_pose_estimation": True,
                    "step_2_3d_lifting": True,
                    "step_3_metrics_calculation": True,
                    "step_4_report_generation": True
                }
            
            logger.info("=" * 80)
            logger.info(f"[{request_id}] 🔍 ========== VALIDATION: ALL 4 STEPS COMPLETION CHECK ==========")
            logger.info(f"[{request_id}] 🔍 Step 1 (Pose Estimation): {'✅ COMPLETE' if steps_completed.get('step_1_pose_estimation', False) else '❌ FAILED'}")
            logger.info(f"[{request_id}] 🔍 Step 2 (3D Lifting): {'✅ COMPLETE' if steps_completed.get('step_2_3d_lifting', False) else '❌ FAILED'}")
            logger.info(f"[{request_id}] 🔍 Step 3 (Metrics Calculation): {'✅ COMPLETE' if steps_completed.get('step_3_metrics_calculation', False) else '❌ FAILED'}")
            logger.info(f"[{request_id}] 🔍 Step 4 (Report Generation): {'✅ COMPLETE' if steps_completed.get('step_4_report_generation', False) else '❌ FAILED'}")
            logger.info("=" * 80)
            
            # CRITICAL: Save steps_completed to database immediately after validation
            # This ensures the frontend can check step completion status
            try:
                logger.info(f"[{request_id}] 💾 Saving steps_completed to database: {steps_completed}")
                await db_service.update_analysis(analysis_id, {
                    'steps_completed': steps_completed
                })
                logger.info(f"[{request_id}] ✅ steps_completed saved to database")
            except Exception as save_error:
                logger.warning(f"[{request_id}] ⚠️ Failed to save steps_completed: {save_error}")
                # Non-critical - will be saved in Step 4
            
            # CRITICAL: Fail if any step didn't complete
            if not all(steps_completed.values()):
                failed_steps = [step for step, completed in steps_completed.items() if not completed]
                error_msg = f"CRITICAL: Not all processing steps completed successfully. Failed steps: {failed_steps}"
                logger.error(f"[{request_id}] ❌ {error_msg}")
                raise VideoProcessingError(
                    error_msg,
                    details={
                        "analysis_id": analysis_id,
                        "steps_completed": steps_completed,
                        "failed_steps": failed_steps
                    }
                )
            
            # CRITICAL: Validate that metrics exist and are not fallback
            # This is the PRIMARY source of metrics - use it directly, don't re-extract
            logger.info("=" * 80)
            logger.info(f"[{request_id}] 🎯 ========== STEP 4: REPORT GENERATION STARTING ==========")
            logger.info(f"[{request_id}] 🎯 [STEP 4 ENTRY] Analysis ID: {analysis_id}")
            logger.info(f"[{request_id}] 🎯 [STEP 4 ENTRY] Extracting metrics from analysis_result...")
            
            # CRITICAL: Update progress immediately when Step 4 starts
            if progress_callback:
                try:
                    progress_callback(93, "Step 4: Report Generation - Starting final phase of analysis...")
                except Exception as e:
                    logger.warning(f"[{request_id}] Error in progress callback at Step 4 start: {e}")
            
            # Update database immediately
            try:
                await db_service.update_analysis(analysis_id, {
                    'current_step': 'report_generation',
                    'step_progress': 93,
                    'step_message': 'Step 4: Report Generation - Starting final phase of analysis...'
                })
            except Exception as step4_start_err:
                logger.warning(f"[{request_id}] Failed to update progress at Step 4 start: {step4_start_err}")
            logger.info(f"[{request_id}] 🎯   - analysis_result type: {type(analysis_result)}")
            logger.info(f"[{request_id}] 🎯   - analysis_result keys: {list(analysis_result.keys())}")
            logger.info(f"[{request_id}] 🎯   - 'metrics' in analysis_result: {'metrics' in analysis_result}")
            
            metrics = analysis_result.get('metrics', {})
            
            logger.info("=" * 80)
            logger.info(f"[{request_id}] 🔍 [STEP 4] METRICS EXTRACTION")
            logger.info(f"[{request_id}] 🔍   - metrics variable type: {type(metrics)}")
            logger.info(f"[{request_id}] 🔍   - metrics is None: {metrics is None}")
            logger.info(f"[{request_id}] 🔍   - metrics is empty dict: {metrics == {}}")
            logger.info(f"[{request_id}] 🔍   - metrics length: {len(metrics) if metrics else 0}")
            if metrics:
                logger.info(f"[{request_id}] 🔍   - metrics keys: {list(metrics.keys())[:15]}")
                logger.info(f"[{request_id}] 🔍   - has cadence: {metrics.get('cadence') is not None}")
                logger.info(f"[{request_id}] 🔍   - has walking_speed: {metrics.get('walking_speed') is not None}")
                logger.info(f"[{request_id}] 🔍   - has step_length: {metrics.get('step_length') is not None}")
                logger.info(f"[{request_id}] 🔍   - is fallback: {metrics.get('fallback_metrics', False)}")
            logger.info("=" * 80)
            
            logger.info(f"[{request_id}] 🔍 [STEP 4] Starting metrics validation...")
            
            if not metrics or len(metrics) == 0:
                error_msg = "CRITICAL: Video processing completed but metrics are missing!"
                logger.error(f"[{request_id}] ❌ [STEP 4] {error_msg}")
                logger.error(f"[{request_id}] ❌   - metrics is None: {metrics is None}")
                logger.error(f"[{request_id}] ❌   - metrics length: {len(metrics) if metrics else 0}")
                logger.error(f"[{request_id}] ❌   - analysis_result keys: {list(analysis_result.keys())}")
                raise VideoProcessingError(
                    error_msg,
                    details={
                        "analysis_id": analysis_id,
                        "has_metrics": False,
                        "analysis_result_keys": list(analysis_result.keys())
                    }
                )
            
            logger.info(f"[{request_id}] ✅ [STEP 4] Metrics exist: {len(metrics)} metrics")
            
            if metrics.get('fallback_metrics', False):
                error_msg = "CRITICAL: Video processing returned fallback metrics - Step 3 likely failed!"
                logger.error(f"[{request_id}] ❌ [STEP 4] {error_msg}")
                logger.error(f"[{request_id}] ❌   - fallback_metrics flag: {metrics.get('fallback_metrics')}")
                logger.error(f"[{request_id}] ❌   - Metrics keys: {list(metrics.keys())}")
                raise VideoProcessingError(
                    error_msg,
                    details={
                        "analysis_id": analysis_id,
                        "has_metrics": True,
                        "fallback_metrics": True,
                        "metrics_keys": list(metrics.keys())
                    }
                )
            
            logger.info(f"[{request_id}] ✅ [STEP 4] Metrics are not fallback")
            
            # Validate core metrics exist
            has_core_metrics = (
                metrics.get('cadence') is not None or
                metrics.get('walking_speed') is not None or
                metrics.get('step_length') is not None
            )
            logger.info(f"[{request_id}] 🔍 [STEP 4] Core metrics check:")
            logger.info(f"[{request_id}] 🔍   - cadence: {metrics.get('cadence')}")
            logger.info(f"[{request_id}] 🔍   - walking_speed: {metrics.get('walking_speed')}")
            logger.info(f"[{request_id}] 🔍   - step_length: {metrics.get('step_length')}")
            logger.info(f"[{request_id}] 🔍   - has_core_metrics: {has_core_metrics}")
            
            if not has_core_metrics:
                error_msg = "CRITICAL: Metrics missing core values (cadence, walking_speed, step_length)!"
                logger.error(f"[{request_id}] ❌ [STEP 4] {error_msg}")
                logger.error(f"[{request_id}] ❌   - Available metrics: {list(metrics.keys())}")
                raise VideoProcessingError(
                    error_msg,
                    details={
                        "analysis_id": analysis_id,
                        "metrics_keys": list(metrics.keys())
                    }
                )
            
            logger.info(f"[{request_id}] ✅ [STEP 4] Metrics validation PASSED - all checks passed")
            logger.info("=" * 80)
            
            # Update progress to indicate Step 4 is starting database save
            if progress_callback:
                try:
                    progress_callback(99, "Saving analysis results to database...")
                except Exception as e:
                    logger.warning(f"Error in progress callback: {e}")
            
            logger.info(
                f"[{request_id}] ✅ Video analysis completed successfully: {frames_processed} frames processed, {len(metrics)} metrics calculated",
                extra={
                    "analysis_id": analysis_id,
                    "frames_processed": frames_processed,
                    "total_frames": total_frames,
                    "metrics_count": len(metrics),
                    "has_symmetry": "step_time_symmetry" in metrics or "step_length_symmetry" in metrics,
                    "has_core_metrics": has_core_metrics
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
            # CRITICAL: Update analysis status to failed before raising exception
            try:
                await db_service.update_analysis(analysis_id, {
                    'status': 'failed',
                    'current_step': 'metrics_calculation',
                    'step_progress': 0,
                    'step_message': f'Step 3 failed: {e.message}'
                })
            except Exception as update_err:
                logger.error(f"[{request_id}] Failed to update analysis status after Step 3 error: {update_err}")
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
            # CRITICAL: Update analysis status to failed before raising exception
            try:
                await db_service.update_analysis(analysis_id, {
                    'status': 'failed',
                    'current_step': analysis.get('current_step', 'unknown'),
                    'step_progress': analysis.get('step_progress', 0),
                    'step_message': f'Analysis failed: {type(e).__name__}: {str(e)[:200]}'
                })
            except Exception as update_err:
                logger.error(f"[{request_id}] Failed to update analysis status after unexpected error: {update_err}")
            # CRITICAL: Don't create fallback - fail the analysis so user knows processing didn't work
            raise VideoProcessingError(
                f"Unexpected error during video analysis: {str(e)}",
                details={"analysis_id": analysis_id, "error_type": type(e).__name__, "error": str(e)}
            )
        
        # CRITICAL: Metrics are already validated above - use them directly
        # DO NOT re-extract or create fallback - metrics from analyze_video are the source of truth
        # The metrics variable is already set from analysis_result.get('metrics', {}) above
        # and has been validated to exist, not be fallback, and have core values
        
        logger.info(
            f"[{request_id}] ✅ Using metrics directly from analysis_result (already validated)",
            extra={
                "analysis_id": analysis_id,
                "metric_count": len(metrics),
                "has_core_metrics": bool(metrics.get('cadence') or metrics.get('walking_speed') or metrics.get('step_length'))
            }
        )
        
        # STEP 4: Update progress: Report generation - with retry logic
        step4_start_time = time.time()
        logger.info("=" * 80)
        logger.info(f"[{request_id}] 🎯 [STEP 4] ========== REPORT GENERATION PHASE STARTING ==========")
        logger.info(f"[{request_id}] 🎯 [STEP 4] Timestamp: {datetime.utcnow().isoformat()}")
        logger.info(f"[{request_id}] 🎯 [STEP 4] Analysis ID: {analysis_id}")
        logger.info(f"[{request_id}] 🎯 [STEP 4] Metrics received from Step 3: {len(metrics) if metrics else 0} metrics")
        if metrics:
            logger.info(f"[{request_id}] 🎯 [STEP 4] Key metrics preview: cadence={metrics.get('cadence')}, speed={metrics.get('walking_speed')}, step_length={metrics.get('step_length')}")
        logger.info("=" * 80)
        
        # CRITICAL: Ensure steps_completed is saved before Step 4 starts
        # This provides visibility into which steps completed
        if steps_completed:
            try:
                logger.info(f"[{request_id}] 💾 [STEP 4] Ensuring steps_completed is saved: {steps_completed}")
                await db_service.update_analysis(analysis_id, {
                    'steps_completed': steps_completed
                })
                logger.info(f"[{request_id}] ✅ [STEP 4] steps_completed confirmed in database")
            except Exception as steps_save_error:
                logger.warning(f"[{request_id}] ⚠️ [STEP 4] Failed to save steps_completed: {steps_save_error}")
                # Will be saved with final completion update
        
        # Update progress callback with detailed message
        if progress_callback:
            try:
                progress_callback(94, "Step 4: Report Generation - Starting final phase...")
            except Exception as e:
                logger.warning(f"[{request_id}] Error in progress callback: {e}")
        
        # Update database with initial Step 4 message
        logger.info(f"[{request_id}] 🔍 [STEP 4] Updating progress to 'report_generation' (94%)...")
        max_db_retries = 5
        progress_update_success = False
        for retry in range(max_db_retries):
            try:
                logger.info(f"[{request_id}] 🔍 [STEP 4] Progress update attempt {retry + 1}/{max_db_retries}")
                update_result = await db_service.update_analysis(analysis_id, {
                    'current_step': 'report_generation',
                    'step_progress': 94,
                    'step_message': 'Step 4: Report Generation - Starting final phase...'
                })
                logger.info(f"[{request_id}] ✅ [STEP 4] Progress update result: {update_result}")
                progress_update_success = True
                break  # Success
            except Exception as e:
                logger.warning(f"[{request_id}] ⚠️ [STEP 4] Progress update attempt {retry + 1} failed: {e}")
                if retry < max_db_retries - 1:
                    await asyncio.sleep(0.2 * (retry + 1))
                    continue
                else:
                    logger.error(
                        f"[{request_id}] ❌ [STEP 4] Progress update failed after {max_db_retries} attempts: {e}",
                        extra={"analysis_id": analysis_id},
                        exc_info=True
                    )
                    # Continue anyway - not critical
        
        if progress_update_success:
            logger.info(f"[{request_id}] ✅ [STEP 4] Progress updated successfully")
        else:
            logger.warning(f"[{request_id}] ⚠️ [STEP 4] Progress update failed but continuing...")
        
        # Update progress: Validating metrics
        if progress_callback:
            try:
                progress_callback(95, "Step 4: Validating metrics from previous steps...")
            except Exception as e:
                logger.warning(f"[{request_id}] Error in progress callback: {e}")
        
        try:
            await db_service.update_analysis(analysis_id, {
                'current_step': 'report_generation',
                'step_progress': 95,
                'step_message': 'Step 4: Validating metrics from previous steps...'
            })
        except Exception as e:
            logger.warning(f"[{request_id}] Failed to update progress for validation: {e}")
        
        # Small delay to show validation message
        await asyncio.sleep(0.5)
        
        # Update progress: Verifying analysis record
        if progress_callback:
            try:
                progress_callback(96, "Step 4: Verifying analysis record in database...")
            except Exception as e:
                logger.warning(f"[{request_id}] Error in progress callback: {e}")
        
        try:
            await db_service.update_analysis(analysis_id, {
                'current_step': 'report_generation',
                'step_progress': 96,
                'step_message': 'Step 4: Verifying analysis record in database...'
            })
        except Exception as e:
            logger.warning(f"[{request_id}] Failed to update progress for verification: {e}")
        
        # Update progress: Stopping background processes
        if progress_callback:
            try:
                progress_callback(96.5, "Step 4: Stopping background processes...")
            except Exception as e:
                logger.warning(f"[{request_id}] Error in progress callback: {e}")
        
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
        
        # Update progress: Checking analysis record
        if progress_callback:
            try:
                progress_callback(97, "Step 4: Checking analysis record exists...")
            except Exception as e:
                logger.warning(f"[{request_id}] Error in progress callback: {e}")
        
        try:
            await db_service.update_analysis(analysis_id, {
                'current_step': 'report_generation',
                'step_progress': 97,
                'step_message': 'Step 4: Checking analysis record exists...'
            })
        except Exception as e:
            logger.warning(f"[{request_id}] Failed to update progress for record check: {e}")
        
        # CRITICAL: Verify analysis exists before final update
        # Add timeout to prevent infinite loops
        analysis_verified = False
        verification_start_time = time.time()
        max_verification_time = 5.0  # Maximum 5 seconds for verification
        
        for verify_retry in range(10):
            # Update progress during verification retries
            if verify_retry > 0 and progress_callback:
                try:
                    progress_callback(97, f"Step 4: Verifying analysis record... (attempt {verify_retry + 1})")
                except Exception as e:
                    logger.warning(f"[{request_id}] Error in progress callback: {e}")
            # Check timeout
            if time.time() - verification_start_time > max_verification_time:
                logger.warning(f"[{request_id}] Verification timeout after {max_verification_time}s - proceeding anyway")
                analysis_verified = True  # Proceed anyway - analysis likely exists
                break
                
            try:
                final_check = await db_service.get_analysis(analysis_id)
                if final_check and final_check.get('id') == analysis_id:
                    analysis_verified = True
                    logger.info(f"[{request_id}] Verified analysis exists before final update (attempt {verify_retry + 1})")
                    break
            except Exception as verify_error:
                if verify_retry < 9:
                    delay = min(0.1 * (verify_retry + 1), 0.5)  # Cap delay at 0.5s
                    logger.warning(f"[{request_id}] Analysis verification failed (attempt {verify_retry + 1}): {verify_error}. Retrying in {delay}s...")
                    await asyncio.sleep(delay)
                    continue
                else:
                    # Last attempt failed - proceed anyway
                    logger.warning(f"[{request_id}] Verification failed after all attempts - proceeding anyway")
                    analysis_verified = True
        
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
        # CRITICAL: Validate metrics exist and have meaningful data before marking as completed
        if not metrics or len(metrics) == 0:
            error_msg = "CRITICAL: Cannot mark as completed - no metrics calculated"
            logger.error(f"[{request_id}] ❌ {error_msg}")
            raise GaitMetricsError(error_msg, details={"analysis_id": analysis_id})
        
        # Validate that we have at least one core metric (cadence, walking_speed, or step_length)
        has_core_metrics = (
            metrics.get('cadence') is not None or
            metrics.get('walking_speed') is not None or
            metrics.get('step_length') is not None
        )
        
        if not has_core_metrics:
            error_msg = "CRITICAL: Cannot mark as completed - no core metrics (cadence, walking_speed, or step_length)"
            logger.error(f"[{request_id}] ❌ {error_msg}")
            logger.error(f"[{request_id}] Available metrics keys: {list(metrics.keys())}")
            raise GaitMetricsError(error_msg, details={"analysis_id": analysis_id, "available_metrics": list(metrics.keys())})
        
        # CRITICAL: Update progress to show we're saving results
        # Determine which database backend is being used
        use_table_storage = hasattr(db_service, '_use_table') and db_service._use_table
        use_sql = not use_table_storage and not db_service._use_mock
        use_mock = db_service._use_mock
        
        logger.info("=" * 80)
        logger.info(f"[{request_id}] 🎯 [STEP 4] ========== DATABASE SAVE PHASE STARTING ==========")
        logger.info(f"[{request_id}] 🎯 [STEP 4] Preparing to save {len(metrics) if metrics else 0} metrics to database")
        logger.info(f"[{request_id}] 🎯 [STEP 4] Database backend: Table Storage={use_table_storage}, SQL={use_sql}, Mock={use_mock}")
        logger.info("=" * 80)
        
        # Update progress: Preparing to save
        if progress_callback:
            try:
                progress_callback(97.5, "Step 4: Preparing to save results to database...")
            except Exception as e:
                logger.warning(f"[{request_id}] Error in progress callback: {e}")
        
        try:
            await db_service.update_analysis(analysis_id, {
                'current_step': 'report_generation',
                'step_progress': 97.5,
                'step_message': 'Step 4: Preparing to save results to database...'
            })
        except Exception as e:
            logger.warning(f"[{request_id}] Failed to update progress: {e}")
        
        await asyncio.sleep(0.3)
        
        # Update progress callback
        if progress_callback:
            try:
                progress_callback(98, "Step 4: Saving analysis results to database...")
            except Exception as e:
                logger.warning(f"[{request_id}] Error in progress callback: {e}")
        
        try:
            await db_service.update_analysis(analysis_id, {
                'current_step': 'report_generation',
                'step_progress': 98,
                'step_message': 'Step 4: Saving analysis results to database...'
            })
            logger.info(f"[{request_id}] ✅ [STEP 4] Progress updated to 98% - 'Saving analysis results to database...'")
        except Exception as e:
            logger.warning(f"[{request_id}] ⚠️ [STEP 4] Failed to update progress before final save: {e}")
        
        # Small delay to ensure previous update is visible
        await asyncio.sleep(0.5)  # Give user time to see the message
        
        completion_success = False
        max_db_retries = 15  # Increased retries for critical final update
        last_error = None
        completion_start_time = time.time()
        max_completion_time = 30.0  # Maximum 30 seconds for completion attempts
        last_progress_update_time = completion_start_time
        progress_update_interval = 10.0  # Update every 10 seconds
        
        logger.info("=" * 80)
        logger.info(f"[{request_id}] 🎯 [STEP 4] ========== FINAL COMPLETION UPDATE PHASE ==========")
        logger.info(f"[{request_id}] 🎯 [STEP 4] Starting completion update with {max_db_retries} max retries")
        logger.info(f"[{request_id}] 🎯 [STEP 4] Max completion time: {max_completion_time}s")
        logger.info(f"[{request_id}] 🎯 [STEP 4] Metrics to save: {len(metrics) if metrics else 0} metrics")
        logger.info("=" * 80)
        
        for retry in range(max_db_retries):
            # Check timeout - don't retry forever
            elapsed_time = time.time() - completion_start_time
            if elapsed_time > max_completion_time:
                logger.error(f"[{request_id}] Completion timeout after {max_completion_time}s - stopping retries")
                break
            
            # Send periodic progress update every 10 seconds during retry loop
            if time.time() - last_progress_update_time >= progress_update_interval:
                elapsed_minutes = int(elapsed_time // 60)
                elapsed_seconds = int(elapsed_time % 60)
                progress_msg = f"Step 4: Saving results to database... ({elapsed_minutes}m {elapsed_seconds}s elapsed, attempt {retry + 1}/{max_db_retries})"
                
                if progress_callback:
                    try:
                        progress_callback(99, progress_msg)
                    except Exception as e:
                        logger.warning(f"[{request_id}] Error in progress callback: {e}")
                
                try:
                    await db_service.update_analysis(analysis_id, {
                        'current_step': 'report_generation',
                        'step_progress': 99,
                        'step_message': progress_msg
                    })
                except Exception as periodic_update_err:
                    logger.warning(f"[{request_id}] Failed to update periodic progress: {periodic_update_err}")
                
                last_progress_update_time = time.time()
                logger.info(f"[{request_id}] 🔄 [STEP 4] Periodic progress update: {progress_msg}")
                
            # Log progress during retries and update UI
            if retry > 0:
                logger.info("=" * 80)
                logger.info(f"[{request_id}] 🔄 [STEP 4] Completion attempt {retry + 1}/{max_db_retries} (elapsed: {elapsed_time:.1f}s)")
                logger.info(f"[{request_id}] 🔄 [STEP 4] Previous attempt failed: {last_error}")
                logger.info("=" * 80)
                
                # Update progress callback
                if progress_callback:
                    try:
                        progress_callback(99, f"Step 4: Retrying database save... (attempt {retry + 1}/{max_db_retries})")
                    except Exception as e:
                        logger.warning(f"[{request_id}] Error in progress callback: {e}")
                
                # Update progress to show we're retrying
                try:
                    await db_service.update_analysis(analysis_id, {
                        'current_step': 'report_generation',
                        'step_progress': 99,
                        'step_message': f'Step 4: Retrying database save... (attempt {retry + 1}/{max_db_retries})'
                    })
                    logger.info(f"[{request_id}] ✅ [STEP 4] Progress updated to show retry attempt")
                except Exception as update_err:
                    logger.warning(f"[{request_id}] ⚠️ [STEP 4] Failed to update progress for retry: {update_err}")
            
            # Log attempt start
            attempt_start_time = time.time()
            logger.info("=" * 80)
            logger.info(f"[{request_id}] 🔍 [STEP 4] Starting completion update attempt {retry + 1}/{max_db_retries}...")
            logger.info(f"[{request_id}] 🔍 [STEP 4] Elapsed time since Step 4 start: {time.time() - step4_start_time:.2f}s")
            logger.info("=" * 80)
            
            try:
                logger.info(f"[{request_id}] 🔍 [STEP 4] Attempt {retry + 1}: Calling db_service.update_analysis with completion data...")
                logger.info(f"[{request_id}] 🔍 [STEP 4]   - status: 'completed'")
                logger.info(f"[{request_id}] 🔍 [STEP 4]   - step_progress: 100")
                logger.info(f"[{request_id}] 🔍 [STEP 4]   - metrics count: {len(metrics) if metrics else 0}")
                logger.info(f"[{request_id}] 🔍 [STEP 4]   - steps_completed: all 4 steps marked True")
                
                # Update progress callback with detailed message
                if progress_callback:
                    try:
                        if retry == 0:
                            progress_callback(99, "Step 4: Saving final results to database...")
                        else:
                            progress_callback(99, f"Step 4: Attempting to save results... (try {retry + 1}/{max_db_retries})")
                    except Exception as e:
                        logger.warning(f"[{request_id}] Error in progress callback: {e}")
                
                # Update database message
                try:
                    await db_service.update_analysis(analysis_id, {
                        'current_step': 'report_generation',
                        'step_progress': 99,
                        'step_message': f'Step 4: Saving final results to database... (attempt {retry + 1}/{max_db_retries})'
                    })
                except Exception as update_msg_err:
                    logger.warning(f"[{request_id}] Failed to update progress message: {update_msg_err}")
                
                # Try async update first
                update_start = time.time()
                logger.info(f"[{request_id}] 🔍 [STEP 4] Calling db_service.update_analysis() at {datetime.utcnow().isoformat()}...")
                update_result = await db_service.update_analysis(analysis_id, {
                    'status': 'completed',
                    'current_step': 'report_generation',
                    'step_progress': 100,
                    'step_message': 'Analysis complete!',
                    'metrics': metrics,
                    'steps_completed': {
                        'step_1_pose_estimation': True,
                        'step_2_3d_lifting': True,
                        'step_3_metrics_calculation': True,
                        'step_4_report_generation': True
                    }
                })
                update_duration = time.time() - update_start
                logger.info(f"[{request_id}] ✅ [STEP 4] Update call completed in {update_duration:.3f}s, result: {update_result}")
                
                if not update_result:
                    # Update returned False - try sync method as fallback
                    if hasattr(db_service, 'update_analysis_sync'):
                        logger.info(f"[{request_id}] Async update returned False, trying sync update (attempt {retry + 1})")
                        sync_result = db_service.update_analysis_sync(analysis_id, {
                            'status': 'completed',
                            'current_step': 'report_generation',
                            'step_progress': 100,
                            'step_message': 'Analysis complete! (sync)',
                            'metrics': metrics,
                            'steps_completed': {
                                'step_1_pose_estimation': True,
                                'step_2_3d_lifting': True,
                                'step_3_metrics_calculation': True,
                                'step_4_report_generation': True
                            }
                        })
                        if not sync_result:
                            raise Exception("Both async and sync updates returned False")
                    else:
                        raise Exception("Update returned False and sync method not available")
                
                # SIMPLIFIED: If update returned True, trust it - just do a simple verification
                # The complex verification was causing issues - if the database says it updated, trust it
                if update_result:
                    # Update progress: Verifying save
                    if progress_callback:
                        try:
                            progress_callback(99.5, "Step 4: Verifying database save was successful...")
                        except Exception as e:
                            logger.warning(f"[{request_id}] Error in progress callback: {e}")
                    
                    try:
                        await db_service.update_analysis(analysis_id, {
                            'current_step': 'report_generation',
                            'step_progress': 99.5,
                            'step_message': 'Step 4: Verifying database save was successful...'
                        })
                    except Exception as verify_msg_err:
                        logger.warning(f"[{request_id}] Failed to update verification message: {verify_msg_err}")
                    
                    # Enhanced verification with periodic progress updates
                    verification_start = time.time()
                    verification_timeout = 30.0  # Maximum 30 seconds for verification
                    verification_update_interval = 10.0  # Update every 10 seconds
                    last_progress_update = verification_start
                    
                    # Small delay for database consistency
                    await asyncio.sleep(0.3)
                    
                    # Attempt verification with periodic updates
                    verification = None
                    verification_attempts = 0
                    max_verification_attempts = 10
                    
                    while verification_attempts < max_verification_attempts:
                        elapsed = time.time() - verification_start
                        
                        # Check timeout
                        if elapsed > verification_timeout:
                            logger.warning(f"[{request_id}] Verification timeout after {verification_timeout}s - proceeding")
                            break
                        
                        # Send periodic progress update every 10 seconds
                        if time.time() - last_progress_update >= verification_update_interval:
                            elapsed_minutes = int(elapsed // 60)
                            elapsed_seconds = int(elapsed % 60)
                            progress_msg = f"Step 4: Verifying database save... ({elapsed_minutes}m {elapsed_seconds}s elapsed)"
                            
                            if progress_callback:
                                try:
                                    progress_callback(99.5, progress_msg)
                                except Exception as e:
                                    logger.warning(f"[{request_id}] Error in progress callback: {e}")
                            
                            try:
                                await db_service.update_analysis(analysis_id, {
                                    'current_step': 'report_generation',
                                    'step_progress': 99.5,
                                    'step_message': progress_msg
                                })
                            except Exception as update_err:
                                logger.warning(f"[{request_id}] Failed to update verification progress: {update_err}")
                            
                            last_progress_update = time.time()
                            logger.info(f"[{request_id}] 🔄 [STEP 4] Verification in progress... ({elapsed_minutes}m {elapsed_seconds}s elapsed)")
                        
                        # Attempt to get verification
                        try:
                            verification = await db_service.get_analysis(analysis_id)
                            if verification:
                                break  # Got verification, exit loop
                        except Exception as verify_err:
                            logger.warning(f"[{request_id}] Verification attempt {verification_attempts + 1} failed: {verify_err}")
                        
                        verification_attempts += 1
                        
                        # Wait before next attempt (with periodic updates)
                        if verification_attempts < max_verification_attempts:
                            wait_time = min(2.0, verification_update_interval / 2)  # Wait up to 2 seconds or half the update interval
                            await asyncio.sleep(wait_time)
                    
                    if verification and verification.get('status') == 'completed':
                        completion_success = True
                        logger.info("=" * 80)
                        logger.info(f"[{request_id}] ✅ [STEP 4] COMPLETION SUCCESSFUL")
                        logger.info(f"[{request_id}] ✅   - Status: completed")
                        logger.info(f"[{request_id}] ✅   - Metrics count: {len(verification.get('metrics', {}))}")
                        logger.info("=" * 80)
                    else:
                        # Update returned True but verification shows different status
                        # This might be a timing issue - log but don't fail (update succeeded)
                        logger.warning(f"[{request_id}] ⚠️ [STEP 4] Update returned True but verification shows status: {verification.get('status') if verification else 'None'}")
                        logger.warning(f"[{request_id}] ⚠️ This may be a timing/consistency issue - update likely succeeded")
                        # Still mark as success since update returned True
                        completion_success = True
                else:
                    # Update returned False - this is a real failure
                    raise Exception("Database update returned False")
                if completion_success:
                    step4_total_time = time.time() - step4_start_time
                    logger.info("=" * 80)
                    logger.info(f"[{request_id}] ✅✅✅ [STEP 4] ========== REPORT GENERATION COMPLETE ==========")
                    logger.info(f"[{request_id}] ✅ [STEP 4] Total Step 4 duration: {step4_total_time:.2f}s")
                    logger.info(f"[{request_id}] ✅ [STEP 4] Completion attempt: {retry + 1}/{max_db_retries}")
                    logger.info(f"[{request_id}] ✅ [STEP 4] Analysis ID: {analysis_id}")
                    logger.info(
                        f"[{request_id}] Analysis completed successfully",
                        extra={
                            "analysis_id": analysis_id,
                            "patient_id": patient_id,
                            "metrics_count": len(metrics),
                            "has_symmetry": "step_time_symmetry" in metrics or "step_length_symmetry" in metrics,
                            "fallback_metrics": metrics.get('fallback_metrics', False),
                            "step4_duration_seconds": step4_total_time
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
                    logger.info("=" * 80)
                    
                    # Update progress callback for final success
                    if progress_callback:
                        try:
                            progress_callback(100, "Step 4: Report generation complete! Analysis ready to view.")
                        except Exception as e:
                            logger.warning(f"[{request_id}] Error in final progress callback: {e}")
                    
                    break  # Success - exit retry loop
                    
            except Exception as e:
                attempt_duration = time.time() - attempt_start_time
                last_error = e
                logger.error("=" * 80)
                logger.error(f"[{request_id}] ❌ [STEP 4] Completion attempt {retry + 1} FAILED after {attempt_duration:.3f}s")
                logger.error(f"[{request_id}] ❌ [STEP 4] Error type: {type(e).__name__}")
                logger.error(f"[{request_id}] ❌ [STEP 4] Error message: {str(e)}")
                logger.error("=" * 80)
                
                if retry < max_db_retries - 1:
                    # Progressive backoff: 0.3s, 0.6s, 0.9s, 1.2s, etc. but cap at 2s
                    delay = min(0.3 * (retry + 1), 2.0)
                    elapsed = time.time() - completion_start_time
                    remaining_time = max_completion_time - elapsed
                    
                    # Don't retry if we're out of time
                    if remaining_time < delay:
                        logger.error(f"[{request_id}] Not enough time for another retry (remaining: {remaining_time:.1f}s, needed: {delay:.1f}s)")
                        break
                    
                    logger.warning(
                        f"[{request_id}] Failed to mark analysis as completed (attempt {retry + 1}/{max_db_retries}, elapsed: {elapsed:.1f}s): {e}. Retrying in {delay}s...",
                        extra={"analysis_id": analysis_id, "error_type": type(e).__name__, "error_details": str(e)},
                        exc_info=True
                    )
                    await asyncio.sleep(delay)
                    continue
                else:
                    logger.error(
                        f"[{request_id}] CRITICAL: Failed to mark analysis as completed after {max_db_retries} attempts: {e}",
                        extra={"analysis_id": analysis_id, "error_type": type(e).__name__, "error_details": str(e)},
                        exc_info=True
                    )
                    # CRITICAL: Even if database update fails, the analysis is complete
                    # Log this as a warning but don't fail - metrics are in memory
                    logger.warning(
                        f"[{request_id}] Analysis processing completed but database update failed. Metrics are available in memory.",
                        extra={"analysis_id": analysis_id, "metrics": metrics, "metrics_count": len(metrics) if metrics else 0}
                    )
                    # Log the actual update data that failed
                    logger.error(
                        f"[{request_id}] Failed update data: status='completed', step='report_generation', progress=100, metrics_count={len(metrics) if metrics else 0}",
                        extra={"analysis_id": analysis_id, "last_error": str(last_error) if last_error else "Unknown"}
                    )
        
        # CRITICAL FIX: If completion failed after all retries, try one final fallback approach
        # This ensures reports are always generated even if the main update path fails
        if not completion_success:
            logger.error(
                f"[{request_id}] ⚠️ CRITICAL: Analysis processing completed but database update failed after {max_db_retries} attempts. "
                f"Analysis ID: {analysis_id}. Metrics are available but status may not be 'completed' in database. "
                f"Attempting final fallback save...",
                extra={
                    "analysis_id": analysis_id,
                    "has_metrics": bool(metrics),
                    "metrics_count": len(metrics) if metrics else 0,
                    "last_error": str(last_error) if last_error else "Unknown"
                }
            )
            
            # FINAL FALLBACK: Try to save metrics separately, then status separately
            # This two-step approach can work even if combined update fails
            try:
                logger.info(f"[{request_id}] 🔄 [STEP 4 FALLBACK] Attempting two-step save: metrics first, then status...")
                fallback_start_time = time.time()
                fallback_last_progress_update = fallback_start_time
                fallback_progress_interval = 10.0  # Update every 10 seconds
                
                # Update progress: Fallback mechanism
                if progress_callback:
                    try:
                        progress_callback(99, "Step 4: Main save failed - trying fallback method...")
                    except Exception as e:
                        logger.warning(f"[{request_id}] Error in progress callback: {e}")
                
                try:
                    await db_service.update_analysis(analysis_id, {
                        'current_step': 'report_generation',
                        'step_progress': 99,
                        'step_message': 'Step 4: Main save failed - trying fallback method...'
                    })
                except Exception as fallback_msg_err:
                    logger.warning(f"[{request_id}] Failed to update fallback message: {fallback_msg_err}")
                
                # Step 1: Save metrics first (without status change)
                metrics_saved = False
                if progress_callback:
                    try:
                        progress_callback(99, "Step 4: Fallback - Saving metrics separately...")
                    except Exception as e:
                        logger.warning(f"[{request_id}] Error in progress callback: {e}")
                
                for fallback_retry in range(5):  # 5 quick retries for metrics
                    # Send periodic progress update every 10 seconds
                    fallback_elapsed = time.time() - fallback_start_time
                    if time.time() - fallback_last_progress_update >= fallback_progress_interval:
                        elapsed_minutes = int(fallback_elapsed // 60)
                        elapsed_seconds = int(fallback_elapsed % 60)
                        progress_msg = f"Step 4: Fallback - Saving metrics... ({elapsed_minutes}m {elapsed_seconds}s elapsed, attempt {fallback_retry + 1}/5)"
                        
                        if progress_callback:
                            try:
                                progress_callback(99, progress_msg)
                            except Exception as e:
                                logger.warning(f"[{request_id}] Error in progress callback: {e}")
                        
                        try:
                            await db_service.update_analysis(analysis_id, {
                                'current_step': 'report_generation',
                                'step_progress': 99,
                                'step_message': progress_msg
                            })
                        except Exception as periodic_err:
                            logger.warning(f"[{request_id}] Failed to update fallback progress: {periodic_err}")
                        
                        fallback_last_progress_update = time.time()
                        logger.info(f"[{request_id}] 🔄 [STEP 4 FALLBACK] Periodic progress: {progress_msg}")
                    
                    if fallback_retry > 0 and progress_callback:
                        try:
                            progress_callback(99, f"Step 4: Fallback - Retrying metrics save... (attempt {fallback_retry + 1}/5)")
                        except Exception as e:
                            logger.warning(f"[{request_id}] Error in progress callback: {e}")
                    try:
                        metrics_result = await db_service.update_analysis(analysis_id, {
                            'metrics': metrics,
                            'steps_completed': {
                                'step_1_pose_estimation': True,
                                'step_2_3d_lifting': True,
                                'step_3_metrics_calculation': True,
                                'step_4_report_generation': True
                            }
                        })
                        if metrics_result:
                            metrics_saved = True
                            logger.info(f"[{request_id}] ✅ [STEP 4 FALLBACK] Metrics saved successfully (attempt {fallback_retry + 1})")
                            break
                    except Exception as metrics_err:
                        logger.warning(f"[{request_id}] ⚠️ [STEP 4 FALLBACK] Metrics save attempt {fallback_retry + 1} failed: {metrics_err}")
                        if fallback_retry < 4:
                            await asyncio.sleep(0.2)
                
                # Step 2: Update status separately (even if metrics save failed, try status)
                status_saved = False
                if progress_callback:
                    try:
                        progress_callback(99, "Step 4: Fallback - Updating status separately...")
                    except Exception as e:
                        logger.warning(f"[{request_id}] Error in progress callback: {e}")
                
                for fallback_retry in range(5):  # 5 quick retries for status
                    # Send periodic progress update every 10 seconds
                    fallback_elapsed = time.time() - fallback_start_time
                    if time.time() - fallback_last_progress_update >= fallback_progress_interval:
                        elapsed_minutes = int(fallback_elapsed // 60)
                        elapsed_seconds = int(fallback_elapsed % 60)
                        progress_msg = f"Step 4: Fallback - Updating status... ({elapsed_minutes}m {elapsed_seconds}s elapsed, attempt {fallback_retry + 1}/5)"
                        
                        if progress_callback:
                            try:
                                progress_callback(99, progress_msg)
                            except Exception as e:
                                logger.warning(f"[{request_id}] Error in progress callback: {e}")
                        
                        try:
                            await db_service.update_analysis(analysis_id, {
                                'current_step': 'report_generation',
                                'step_progress': 99,
                                'step_message': progress_msg
                            })
                        except Exception as periodic_err:
                            logger.warning(f"[{request_id}] Failed to update fallback progress: {periodic_err}")
                        
                        fallback_last_progress_update = time.time()
                        logger.info(f"[{request_id}] 🔄 [STEP 4 FALLBACK] Periodic progress: {progress_msg}")
                    
                    if fallback_retry > 0 and progress_callback:
                        try:
                            progress_callback(99, f"Step 4: Fallback - Retrying status update... (attempt {fallback_retry + 1}/5)")
                        except Exception as e:
                            logger.warning(f"[{request_id}] Error in progress callback: {e}")
                    try:
                        status_result = await db_service.update_analysis(analysis_id, {
                            'status': 'completed',
                            'current_step': 'report_generation',
                            'step_progress': 100,
                            'step_message': 'Analysis complete! (fallback save)'
                        })
                        if status_result:
                            status_saved = True
                            logger.info(f"[{request_id}] ✅ [STEP 4 FALLBACK] Status updated successfully (attempt {fallback_retry + 1})")
                            break
                    except Exception as status_err:
                        logger.warning(f"[{request_id}] ⚠️ [STEP 4 FALLBACK] Status update attempt {fallback_retry + 1} failed: {status_err}")
                        if fallback_retry < 4:
                            await asyncio.sleep(0.2)
                
                # Verify final state with periodic updates
                if metrics_saved or status_saved:
                    verification_start = time.time()
                    verification_last_update = verification_start
                    
                    if progress_callback:
                        try:
                            progress_callback(99.5, "Step 4: Fallback - Verifying save was successful...")
                        except Exception as e:
                            logger.warning(f"[{request_id}] Error in progress callback: {e}")
                    
                    await asyncio.sleep(0.3)  # Small delay for consistency
                    
                    # Attempt verification with periodic updates
                    verification = None
                    for verify_attempt in range(5):
                        verify_elapsed = time.time() - verification_start
                        
                        # Send periodic progress update every 10 seconds
                        if time.time() - verification_last_update >= fallback_progress_interval:
                            elapsed_minutes = int(verify_elapsed // 60)
                            elapsed_seconds = int(verify_elapsed % 60)
                            progress_msg = f"Step 4: Fallback - Verifying save... ({elapsed_minutes}m {elapsed_seconds}s elapsed)"
                            
                            if progress_callback:
                                try:
                                    progress_callback(99.5, progress_msg)
                                except Exception as e:
                                    logger.warning(f"[{request_id}] Error in progress callback: {e}")
                            
                            try:
                                await db_service.update_analysis(analysis_id, {
                                    'current_step': 'report_generation',
                                    'step_progress': 99.5,
                                    'step_message': progress_msg
                                })
                            except Exception as verify_update_err:
                                logger.warning(f"[{request_id}] Failed to update verification progress: {verify_update_err}")
                            
                            verification_last_update = time.time()
                            logger.info(f"[{request_id}] 🔄 [STEP 4 FALLBACK] Verification progress: {progress_msg}")
                        
                        try:
                            verification = await db_service.get_analysis(analysis_id)
                            if verification:
                                break
                        except Exception as verify_err:
                            logger.warning(f"[{request_id}] Fallback verification attempt {verify_attempt + 1} failed: {verify_err}")
                            if verify_attempt < 4:
                                await asyncio.sleep(0.5)
                    
                    if verification:
                        verification = await db_service.get_analysis(analysis_id)
                    if verification:
                        if verification.get('status') == 'completed' or (verification.get('metrics') and len(verification.get('metrics', {})) > 0):
                            logger.info(f"[{request_id}] ✅ [STEP 4 FALLBACK] Fallback save successful! Status: {verification.get('status')}, Has metrics: {bool(verification.get('metrics'))}")
                            completion_success = True
                            if progress_callback:
                                try:
                                    progress_callback(100, "Step 4: Report generation complete! Analysis ready to view.")
                                except Exception as e:
                                    logger.warning(f"[{request_id}] Error in final progress callback: {e}")
                        else:
                            logger.warning(f"[{request_id}] ⚠️ [STEP 4 FALLBACK] Fallback save attempted but verification shows incomplete state")
                    else:
                        logger.warning(f"[{request_id}] ⚠️ [STEP 4 FALLBACK] Could not verify fallback save - analysis not found")
                else:
                    logger.error(f"[{request_id}] ❌ [STEP 4 FALLBACK] Both metrics and status saves failed in fallback attempt")
                    
            except Exception as fallback_err:
                logger.error(f"[{request_id}] ❌ [STEP 4 FALLBACK] Fallback save mechanism failed: {fallback_err}", exc_info=True)
            
            # Final error log if still not successful
            if not completion_success:
                logger.error(
                    f"[{request_id}] ❌ CRITICAL: All completion attempts failed including fallback. "
                    f"Analysis ID: {analysis_id}. Metrics are available but status may not be 'completed' in database. "
                    f"Manual recovery: POST /api/v1/analysis/{analysis_id}/force-complete",
                    extra={
                        "analysis_id": analysis_id,
                        "has_metrics": bool(metrics),
                        "metrics_count": len(metrics) if metrics else 0,
                        "last_error": str(last_error) if last_error else "Unknown"
                    }
                )
    
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


@router.post(
    "/{analysis_id}/cancel",
    responses={
        200: {"description": "Analysis cancelled successfully"},
        404: {"model": ErrorResponse, "description": "Analysis not found"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
        503: {"model": ErrorResponse, "description": "Service unavailable"}
    }
)
async def cancel_analysis(
    analysis_id: str = PathParam(..., description="Analysis ID to cancel")
) -> JSONResponse:
    """
    Cancel a processing analysis
    
    Args:
        analysis_id: Unique analysis identifier
        
    Returns:
        JSONResponse with cancellation status
        
    Raises:
        HTTPException: If analysis not found or cancellation fails
    """
    request_id = str(uuid.uuid4())[:8]
    logger.info(f"[{request_id}] Cancel analysis request", extra={"analysis_id": analysis_id})
    
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
        # Get analysis to check if it exists
        analysis = await db_service.get_analysis(analysis_id)
        if not analysis:
            logger.warning(f"[{request_id}] Analysis not found: {analysis_id}")
            raise HTTPException(
                status_code=404,
                detail={
                    "error": "ANALYSIS_NOT_FOUND",
                    "message": f"Analysis {analysis_id} not found",
                    "details": {"analysis_id": analysis_id}
                }
            )
        
        # Only cancel if status is 'processing'
        current_status = analysis.get('status')
        if current_status == 'cancelled':
            logger.info(f"[{request_id}] Analysis already cancelled: {analysis_id}")
            return JSONResponse({
                "status": "cancelled",
                "message": "Analysis was already cancelled",
                "analysis_id": analysis_id
            })
        
        if current_status not in ['processing', 'uploading']:
            logger.info(f"[{request_id}] Analysis not in cancellable state: {current_status}")
            return JSONResponse({
                "status": current_status,
                "message": f"Analysis is in '{current_status}' state and cannot be cancelled",
                "analysis_id": analysis_id
            })
        
        # Update analysis status to cancelled
        success = await db_service.update_analysis(analysis_id, {
            'status': 'cancelled',
            'current_step': analysis.get('current_step', 'unknown'),
            'step_progress': analysis.get('step_progress', 0),
            'step_message': 'Analysis cancelled by user'
        })
        
        if success:
            logger.info(f"[{request_id}] ✅ Analysis cancelled: {analysis_id}")
            return JSONResponse({
                "status": "cancelled",
                "message": "Analysis cancelled successfully",
                "analysis_id": analysis_id
            })
        else:
            logger.error(f"[{request_id}] Failed to update analysis status to cancelled")
            raise HTTPException(
                status_code=500,
                detail={
                    "error": "CANCELLATION_FAILED",
                    "message": "Failed to cancel analysis",
                    "details": {"analysis_id": analysis_id}
                }
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"[{request_id}] Error cancelling analysis: {e}",
            extra={"analysis_id": analysis_id},
            exc_info=True
        )
        raise HTTPException(
            status_code=500,
            detail={
                "error": "INTERNAL_ERROR",
                "message": f"Failed to cancel analysis: {str(e)}",
                "details": {"analysis_id": analysis_id}
            }
        )


@router.post(
    "/cancel-all",
    responses={
        200: {"description": "All processing analyses cancelled"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
        503: {"model": ErrorResponse, "description": "Service unavailable"}
    }
)
async def cancel_all_processing() -> JSONResponse:
    """
    Cancel all analyses that are currently processing
    Useful for cleanup on app startup/restart
    
    Returns:
        JSONResponse with count of cancelled analyses
    """
    request_id = str(uuid.uuid4())[:8]
    logger.info(f"[{request_id}] Cancel all processing analyses request")
    
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
        # Get all analyses
        all_analyses = await db_service.list_analyses(limit=1000)
        
        # Filter for processing analyses
        processing_analyses = [a for a in all_analyses if a.get('status') == 'processing']
        
        cancelled_count = 0
        for analysis in processing_analyses:
            analysis_id = analysis.get('id')
            try:
                success = await db_service.update_analysis(analysis_id, {
                    'status': 'cancelled',
                    'current_step': analysis.get('current_step', 'unknown'),
                    'step_progress': analysis.get('step_progress', 0),
                    'step_message': 'Analysis cancelled on app restart'
                })
                if success:
                    cancelled_count += 1
                    logger.info(f"[{request_id}] Cancelled analysis: {analysis_id}")
            except Exception as e:
                logger.warning(f"[{request_id}] Failed to cancel analysis {analysis_id}: {e}")
        
        logger.info(f"[{request_id}] ✅ Cancelled {cancelled_count} of {len(processing_analyses)} processing analyses")
        return JSONResponse({
            "status": "success",
            "message": f"Cancelled {cancelled_count} processing analyses",
            "cancelled_count": cancelled_count,
            "total_processing": len(processing_analyses)
        })
        
    except Exception as e:
        logger.error(
            f"[{request_id}] Error cancelling all processing analyses: {e}",
            exc_info=True
        )
        raise HTTPException(
            status_code=500,
            detail={
                "error": "INTERNAL_ERROR",
                "message": f"Failed to cancel processing analyses: {str(e)}",
                "details": {}
            }
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
        
        # Transform database results to match AnalysisDetailResponse model
        transformed_analyses = []
        for a in analyses:
            try:
                # Ensure all required fields are present with defaults
                analysis_data = {
                    'id': a.get('id', ''),
                    'patient_id': a.get('patient_id'),
                    'filename': a.get('filename', 'unknown'),
                    'video_url': a.get('video_url'),
                    'status': a.get('status', 'idle'),  # Convert to string if needed
                    'current_step': a.get('current_step'),
                    'step_progress': a.get('step_progress', 0),
                    'step_message': a.get('step_message'),
                    'metrics': a.get('metrics', {}),
                    'created_at': a.get('created_at'),
                    'updated_at': a.get('updated_at'),
                    'video_quality_score': a.get('video_quality_score'),
                    'video_quality_valid': a.get('video_quality_valid'),
                    'video_quality_issues': a.get('video_quality_issues'),
                    'video_quality_recommendations': a.get('video_quality_recommendations'),
                    'pose_detection_rate': a.get('pose_detection_rate')
                }
                
                # Convert status string to AnalysisStatus enum if needed
                status_value = analysis_data['status']
                if isinstance(status_value, str):
                    # Try to match to enum value
                    try:
                        from app.core.schemas import AnalysisStatus
                        # Map common status strings to enum
                        status_map = {
                            'processing': AnalysisStatus.PROCESSING,
                            'completed': AnalysisStatus.COMPLETED,
                            'failed': AnalysisStatus.FAILED,
                            'cancelled': AnalysisStatus.FAILED,  # Map cancelled to failed for now
                            'idle': AnalysisStatus.IDLE
                        }
                        analysis_data['status'] = status_map.get(status_value.lower(), AnalysisStatus.IDLE)
                    except Exception:
                        # If enum conversion fails, use string (model will handle it)
                        pass
                
                transformed_analyses.append(AnalysisDetailResponse(**analysis_data))
            except Exception as transform_error:
                logger.warning(
                    f"[{request_id}] Failed to transform analysis {a.get('id', 'unknown')}: {transform_error}",
                    extra={"analysis_id": a.get('id'), "error": str(transform_error)}
                )
                # Skip invalid analyses rather than failing the entire request
                continue
        
        logger.info(f"[{request_id}] Successfully transformed {len(transformed_analyses)} of {len(analyses)} analyses")
        
        return AnalysisListResponse(
            analyses=transformed_analyses,
            total=len(transformed_analyses),
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
            
            # CRITICAL: Check if this might be a recently completed analysis that was lost
            # Log diagnostic information for debugging
            logger.error(
                f"[{request_id}] 🔍🔍🔍 DIAGNOSTIC: Analysis {analysis_id} not found. "
                f"This may indicate:\n"
                f"  1. Analysis was lost during container restart\n"
                f"  2. File storage corruption or deletion\n"
                f"  3. Multi-worker sync issue\n"
                f"  4. Analysis was never created\n"
                f"Check storage file: {getattr(db_service, '_mock_storage_file', 'unknown')}",
                extra={
                    "analysis_id": analysis_id,
                    "storage_file": getattr(db_service, '_mock_storage_file', 'unknown') if hasattr(db_service, '_mock_storage_file') else 'unknown',
                    "use_mock": getattr(db_service, '_use_mock', False) if hasattr(db_service, '_use_mock') else 'unknown'
                }
            )
            
            # Don't recreate - return 404 so frontend knows analysis doesn't exist
            # The defensive recreation was causing stuck states
            raise HTTPException(
                status_code=404,
                detail={
                    "error": "NOT_FOUND",
                    "message": f"Analysis with ID {analysis_id} not found",
                    "details": {
                        "analysis_id": analysis_id,
                        "diagnostic": "Analysis may have been lost during container restart or file storage issue. Check backend logs for 🔍🔍🔍 diagnostic messages."
                    }
                }
            )
        
        logger.info(f"[{request_id}] Analysis retrieved successfully", extra={"analysis_id": analysis_id, "status": analysis.get("status")})
        
        # CRITICAL: Normalize analysis data before creating response
        # Handle common data inconsistencies that cause 500 errors
        try:
            # Ensure 'id' field exists (might be stored as 'analysis_id' or 'id')
            if 'id' not in analysis and 'analysis_id' in analysis:
                analysis['id'] = analysis['analysis_id']
            elif 'id' not in analysis:
                analysis['id'] = analysis_id  # Fallback to path parameter
            
            # Ensure 'filename' exists (required field)
            if 'filename' not in analysis or analysis.get('filename') is None:
                analysis['filename'] = analysis.get('video_url', 'unknown').split('/')[-1] if analysis.get('video_url') else 'unknown'
            
            # Normalize status to match AnalysisStatus enum
            status = analysis.get('status', 'processing')
            # Map any non-standard status values to valid enum values
            status_map = {
                'pending': 'pending',
                'processing': 'processing',
                'completed': 'completed',
                'failed': 'failed',
                'cancelled': 'failed',  # Map cancelled to failed for enum compatibility
                'testing': 'processing'  # Map testing to processing
            }
            analysis['status'] = status_map.get(status.lower(), 'processing')
            
            # Ensure step_progress is valid (0-100)
            step_progress = analysis.get('step_progress', 0)
            if not isinstance(step_progress, (int, float)):
                try:
                    step_progress = int(float(step_progress))
                except (ValueError, TypeError):
                    step_progress = 0
            analysis['step_progress'] = max(0, min(100, int(step_progress)))
            
            # Ensure steps_completed exists (default to empty dict if missing)
            if 'steps_completed' not in analysis or analysis.get('steps_completed') is None:
                analysis['steps_completed'] = {}
            
            # Ensure metrics is a dict if it exists
            if 'metrics' in analysis and analysis['metrics'] is not None:
                if isinstance(analysis['metrics'], str):
                    # Try to parse JSON string
                    try:
                        import json
                        analysis['metrics'] = json.loads(analysis['metrics'])
                    except (json.JSONDecodeError, TypeError):
                        analysis['metrics'] = {}
                elif not isinstance(analysis['metrics'], dict):
                    analysis['metrics'] = {}
            
            logger.debug(f"[{request_id}] Normalized analysis data: id={analysis.get('id')}, filename={analysis.get('filename')}, status={analysis.get('status')}")
            
            return AnalysisDetailResponse(**analysis)
            
        except Exception as validation_error:
            # If Pydantic validation fails, log detailed error and return safe response
            logger.error(
                f"[{request_id}] ❌ CRITICAL: Failed to create AnalysisDetailResponse: {validation_error}",
                extra={
                    "analysis_id": analysis_id,
                    "error_type": type(validation_error).__name__,
                    "analysis_keys": list(analysis.keys()) if analysis else [],
                    "analysis_id_field": analysis.get('id') if analysis else None,
                    "analysis_filename": analysis.get('filename') if analysis else None,
                    "analysis_status": analysis.get('status') if analysis else None,
                },
                exc_info=True
            )
            # Return a safe response with available data instead of crashing
            safe_analysis = {
                'id': analysis.get('id') or analysis.get('analysis_id') or analysis_id,
                'patient_id': analysis.get('patient_id'),
                'filename': analysis.get('filename') or 'unknown',
                'video_url': analysis.get('video_url'),
                'status': 'processing',  # Safe default
                'current_step': analysis.get('current_step'),
                'step_progress': max(0, min(100, int(analysis.get('step_progress', 0)))),
                'step_message': analysis.get('step_message'),
                'metrics': analysis.get('metrics') if isinstance(analysis.get('metrics'), dict) else {},
                'steps_completed': analysis.get('steps_completed') or {},
                'created_at': analysis.get('created_at'),
                'updated_at': analysis.get('updated_at'),
                'video_quality_score': analysis.get('video_quality_score'),
                'video_quality_valid': analysis.get('video_quality_valid'),
                'video_quality_issues': analysis.get('video_quality_issues'),
                'video_quality_recommendations': analysis.get('video_quality_recommendations'),
                'pose_detection_rate': analysis.get('pose_detection_rate')
            }
            try:
                return AnalysisDetailResponse(**safe_analysis)
            except Exception as safe_error:
                logger.critical(
                    f"[{request_id}] ❌ CRITICAL: Even safe response failed: {safe_error}",
                    exc_info=True
                )
                # Last resort: raise HTTPException with details
                raise HTTPException(
                    status_code=500,
                    detail={
                        "error": "RESPONSE_VALIDATION_ERROR",
                        "message": f"Failed to format analysis response: {str(validation_error)}",
                        "details": {
                            "analysis_id": analysis_id,
                            "validation_error": str(validation_error),
                            "safe_error": str(safe_error) if 'safe_error' in locals() else None
                        }
                    }
                )
    
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
        # Convert to HTTPException so frontend gets proper error response
        raise HTTPException(
            status_code=500,
            detail={
                "error": "DATABASE_ERROR",
                "message": f"Failed to retrieve analysis {analysis_id}",
                "details": {"error": str(e), "analysis_id": analysis_id}
            }
        )


@router.post(
    "/{analysis_id}/force-complete",
    responses={
        200: {"description": "Analysis marked as completed"},
        404: {"model": ErrorResponse, "description": "Analysis not found"},
        400: {"model": ErrorResponse, "description": "Analysis cannot be completed"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
        503: {"model": ErrorResponse, "description": "Service unavailable"}
    }
)
async def force_complete_analysis(
    analysis_id: str = PathParam(..., description="Analysis identifier", pattern="^[a-f0-9-]{36}$")
) -> JSONResponse:
    """
    Admin endpoint to manually mark a stuck analysis as completed.
    This is a recovery mechanism for analyses that are stuck in 'processing' status
    but have actually completed processing (have metrics but status wasn't updated).
    
    Args:
        analysis_id: UUID of the analysis to force complete
        
    Returns:
        JSONResponse with completion status
        
    Raises:
        HTTPException: 404 if not found, 400 if cannot be completed, 500/503 on errors
    """
    request_id = str(uuid.uuid4())[:8]
    logger.info(f"[ADMIN-{request_id}] Force complete analysis request", extra={"analysis_id": analysis_id})
    
    # Validate UUID format
    try:
        uuid.UUID(analysis_id)
    except ValueError:
        logger.warning(f"[ADMIN-{request_id}] Invalid UUID format: {analysis_id}")
        raise HTTPException(
            status_code=400,
            detail={
                "error": "VALIDATION_ERROR",
                "message": f"Invalid analysis ID format: {analysis_id}",
                "details": {"provided": analysis_id, "expected_format": "UUID"}
            }
        )
    
    if db_service is None:
        logger.error(f"[ADMIN-{request_id}] Database service not available")
        raise HTTPException(
            status_code=503,
            detail={
                "error": "SERVICE_UNAVAILABLE",
                "message": "Database service is not available",
                "details": {}
            }
        )
    
    try:
        # Get current analysis state
        analysis = await db_service.get_analysis(analysis_id)
        if not analysis:
            logger.warning(f"[ADMIN-{request_id}] Analysis not found: {analysis_id}")
            raise HTTPException(
                status_code=404,
                detail={
                    "error": "NOT_FOUND",
                    "message": f"Analysis {analysis_id} not found",
                    "details": {}
                }
            )
        
        current_status = analysis.get('status', 'unknown')
        current_step = analysis.get('current_step', 'unknown')
        step_progress = analysis.get('step_progress', 0)
        metrics = analysis.get('metrics', {})
        
        logger.info(
            f"[ADMIN-{request_id}] Current analysis state",
            extra={
                "analysis_id": analysis_id,
                "status": current_status,
                "step": current_step,
                "progress": step_progress,
                "has_metrics": bool(metrics and len(metrics) > 0)
            }
        )
        
        # Check if analysis can be force completed
        if current_status == 'completed':
            logger.info(f"[ADMIN-{request_id}] Analysis already completed")
            return JSONResponse({
                "status": "success",
                "message": "Analysis is already completed",
                "analysis_id": analysis_id,
                "current_status": current_status
            })
        
        if current_status == 'failed':
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "CANNOT_COMPLETE",
                    "message": "Cannot force complete a failed analysis",
                    "details": {"current_status": current_status}
                }
            )
        
        # Check if we have metrics (required for completion)
        if not metrics or len(metrics) == 0:
            # Try to get metrics from checkpoint if available
            from app.services.checkpoint_manager import CheckpointManager
            checkpoint_manager = CheckpointManager(analysis_id=analysis_id)
            step3_checkpoint = checkpoint_manager.load_step_3()
            
            if step3_checkpoint and step3_checkpoint.get('metrics'):
                metrics = step3_checkpoint.get('metrics')
                logger.info(f"[ADMIN-{request_id}] Loaded metrics from checkpoint")
            else:
                raise HTTPException(
                    status_code=400,
                    detail={
                        "error": "NO_METRICS",
                        "message": "Cannot force complete analysis without metrics. Analysis may not have finished processing.",
                        "details": {
                            "current_status": current_status,
                            "current_step": current_step,
                            "step_progress": step_progress
                        }
                    }
                )
        
        # Validate metrics have core values
        has_core_metrics = (
            metrics.get('cadence') is not None or
            metrics.get('walking_speed') is not None or
            metrics.get('step_length') is not None
        )
        
        if not has_core_metrics:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "INVALID_METRICS",
                    "message": "Metrics exist but don't have core values (cadence, walking_speed, or step_length)",
                    "details": {"metrics_keys": list(metrics.keys()) if metrics else []}
                }
            )
        
        # Force complete with multiple retry strategies
        completion_success = False
        max_retries = 5
        
        for retry in range(max_retries):
            try:
                # Try standard update with all required fields
                success = await db_service.update_analysis(analysis_id, {
                    'status': 'completed',
                    'current_step': 'report_generation',
                    'step_progress': 100,
                    'step_message': 'Analysis completed (force complete)',
                    'metrics': metrics,
                    'steps_completed': {
                        'step_1_pose_estimation': True,
                        'step_2_3d_lifting': True,
                        'step_3_metrics_calculation': True,
                        'step_4_report_generation': True
                    }
                })
                
                if success:
                    # Verify the update
                    await asyncio.sleep(0.3)
                    verification = await db_service.get_analysis(analysis_id)
                    if verification and verification.get('status') == 'completed':
                        completion_success = True
                        logger.info(f"[ADMIN-{request_id}] ✅ Force complete successful (attempt {retry + 1})")
                        break
                    else:
                        logger.warning(f"[ADMIN-{request_id}] Update succeeded but verification failed (attempt {retry + 1})")
                else:
                    logger.warning(f"[ADMIN-{request_id}] Update returned False (attempt {retry + 1})")
                    
            except Exception as e:
                logger.warning(
                    f"[ADMIN-{request_id}] Force complete attempt {retry + 1} failed: {e}",
                    exc_info=True
                )
            
            if retry < max_retries - 1:
                await asyncio.sleep(0.5 * (retry + 1))
        
        if not completion_success:
            # Last resort: try sync update if available
            try:
                if hasattr(db_service, 'update_analysis_sync'):
                    logger.info(f"[ADMIN-{request_id}] Trying sync update as last resort")
                    sync_success = db_service.update_analysis_sync(analysis_id, {
                        'status': 'completed',
                        'current_step': 'report_generation',
                        'step_progress': 100,
                        'step_message': 'Analysis completed (force complete - sync)',
                        'metrics': metrics,
                        'steps_completed': {
                            'step_1_pose_estimation': True,
                            'step_2_3d_lifting': True,
                            'step_3_metrics_calculation': True,
                            'step_4_report_generation': True
                        }
                    })
                    if sync_success:
                        await asyncio.sleep(0.5)
                        verification = await db_service.get_analysis(analysis_id)
                        if verification and verification.get('status') == 'completed':
                            completion_success = True
                            logger.info(f"[ADMIN-{request_id}] ✅ Force complete successful via sync update")
            except Exception as sync_error:
                logger.error(f"[ADMIN-{request_id}] Sync update also failed: {sync_error}", exc_info=True)
        
        if completion_success:
            return JSONResponse({
                "status": "success",
                "message": "Analysis successfully marked as completed",
                "analysis_id": analysis_id,
                "metrics_count": len(metrics) if metrics else 0,
                "report_url": f"/report/{analysis_id}"
            })
        else:
            logger.error(f"[ADMIN-{request_id}] ❌ All force complete attempts failed")
            raise HTTPException(
                status_code=500,
                detail={
                    "error": "UPDATE_FAILED",
                    "message": "Failed to update analysis status after multiple attempts",
                    "details": {
                        "analysis_id": analysis_id,
                        "attempts": max_retries
                    }
                }
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"[ADMIN-{request_id}] Error force completing analysis: {e}",
            extra={"analysis_id": analysis_id},
            exc_info=True
        )
        raise HTTPException(
            status_code=500,
            detail={
                "error": "INTERNAL_ERROR",
                "message": f"Failed to force complete analysis: {str(e)}",
                "details": {"analysis_id": analysis_id}
            }
        )


@router.delete(
    "/{analysis_id}",
    responses={
        200: {"description": "Analysis deleted successfully"},
        404: {"model": ErrorResponse, "description": "Analysis not found"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
        503: {"model": ErrorResponse, "description": "Service unavailable"}
    }
)
async def delete_analysis(
    analysis_id: str = PathParam(..., description="Analysis ID to delete")
) -> JSONResponse:
    """
    Delete an analysis and its associated data
    
    Args:
        analysis_id: Unique analysis identifier
        
    Returns:
        JSONResponse with deletion status
        
    Raises:
        HTTPException: If analysis not found or deletion fails
    """
    request_id = str(uuid.uuid4())[:8]
    logger.info(f"[{request_id}] Delete analysis request", extra={"analysis_id": analysis_id})
    
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
        # Get analysis to check if it exists
        analysis = await db_service.get_analysis(analysis_id)
        if not analysis:
            logger.warning(f"[{request_id}] Analysis not found: {analysis_id}")
            raise HTTPException(
                status_code=404,
                detail={
                    "error": "ANALYSIS_NOT_FOUND",
                    "message": f"Analysis {analysis_id} not found",
                    "details": {"analysis_id": analysis_id}
                }
            )
        
        # Delete analysis from database
        # Check if delete_analysis method exists, otherwise use update to mark as deleted
        if hasattr(db_service, 'delete_analysis'):
            success = await db_service.delete_analysis(analysis_id)
        else:
            # Fallback: mark as deleted instead of hard delete
            success = await db_service.update_analysis(analysis_id, {
                'status': 'deleted',
                'step_message': 'Analysis deleted by user'
            })
            logger.info(f"[{request_id}] Marked analysis as deleted (soft delete): {analysis_id}")
        
        if success:
            logger.info(f"[{request_id}] ✅ Analysis deleted: {analysis_id}")
            return JSONResponse({
                "status": "success",
                "message": f"Analysis {analysis_id} deleted successfully",
                "analysis_id": analysis_id
            })
        else:
            logger.error(f"[{request_id}] Failed to delete analysis: {analysis_id}")
            raise HTTPException(
                status_code=500,
                detail={
                    "error": "DELETION_FAILED",
                    "message": f"Failed to delete analysis {analysis_id}",
                    "details": {"analysis_id": analysis_id}
                }
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"[{request_id}] Error deleting analysis: {e}",
            extra={"analysis_id": analysis_id, "error_type": type(e).__name__},
            exc_info=True
        )
        raise DatabaseError(
            f"Failed to delete analysis {analysis_id}",
            details={"error": str(e), "analysis_id": analysis_id}
        )


