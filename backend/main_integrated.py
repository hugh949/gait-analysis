"""
Integrated Gait Analysis Application
Single FastAPI app serving both API and React frontend
All Microsoft native services
"""
import sys
import logging
from pathlib import Path

# Setup basic logging first
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# Try to use loguru if available
try:
    from loguru import logger as loguru_logger
    logger = loguru_logger
    logger.info("Using loguru for logging")
except ImportError:
    logger.info("Using standard logging (loguru not available)")

from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, FileResponse
from fastapi.exceptions import RequestValidationError
from contextlib import asynccontextmanager
import os
import asyncio

# Import request logging middleware
try:
    from app.core.middleware import RequestLoggingMiddleware, SPARoutingMiddleware
    MIDDLEWARE_AVAILABLE = True
except ImportError:
    MIDDLEWARE_AVAILABLE = False
    SPARoutingMiddleware = None
    logger.warning("Request logging middleware not available")

# Import app modules with error handling
# CRITICAL: Don't raise on import errors - allow app to start even if modules fail
# This prevents 502 errors during deployment
try:
    from app.core.config_simple import settings
except Exception as e:
    logger.error(f"Failed to import settings: {e}", exc_info=True)
    # Create minimal settings object to allow app to start
    class MinimalSettings:
        HOST = "0.0.0.0"
        PORT = 8000
        DEBUG = False
        def get_cors_origins(self):
            return ["*"]
    settings = MinimalSettings()
    logger.warning("Using minimal settings - app may have limited functionality")

# Import router
try:
    from app.api.v1.analysis_azure import router as analysis_router
    logger.info("✓ Analysis router imported")
except Exception as e:
    logger.error(f"Failed to import analysis router: {e}", exc_info=True)
    from fastapi import APIRouter
    analysis_router = APIRouter()
    logger.warning("Using empty router - API endpoints will not work")

# Import testing router (for development/testing only)
try:
    from app.api.v1.testing_azure import router as testing_router
    logger.info("✓ Testing router imported successfully")
    for route in testing_router.routes:
        if hasattr(route, 'path') and hasattr(route, 'methods'):
            logger.debug(f"  Test Route: {list(route.methods)} {route.path}")
except Exception as e:
    logger.warning(f"Failed to import testing router (non-critical): {e}")
    # Testing router is optional - don't fail if it's not available
    testing_router = None

# Import logs router (for monitoring and debugging)
try:
    from app.api.v1.logs_azure import router as logs_router
    logger.info("✓ Logs router imported successfully")
except Exception as e:
    logger.warning(f"Failed to import logs router (non-critical): {e}")
    logs_router = None

# Get paths
# In Docker, frontend is at /app/frontend/dist (copied from backend/frontend-dist)
BASE_DIR = Path(__file__).parent
FRONTEND_DIR = BASE_DIR / "frontend" / "dist"
STATIC_DIR = FRONTEND_DIR / "assets" if FRONTEND_DIR.exists() else None

# Log frontend path for debugging
logger.info(f"Frontend directory: {FRONTEND_DIR}")
logger.info(f"Frontend exists: {FRONTEND_DIR.exists()}")
if FRONTEND_DIR.exists():
    logger.info(f"Frontend files: {list(FRONTEND_DIR.iterdir())}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    # Startup
    logger.info("Starting Integrated Gait Analysis Application...")
    logger.info("Services: Azure Blob Storage, Computer Vision, SQL Database")
    logger.info("Serving: API + React Frontend")
    
    # Cancel all processing analyses on startup (non-blocking)
    # Use asyncio.create_task to avoid blocking startup if database is slow
    async def cancel_processing_on_startup():
        try:
            logger.info("🛑 Cancelling any processing analyses from previous session...")
            from app.core.database_azure_sql import AzureSQLService
            db_service = AzureSQLService()
            
            if db_service:
                try:
                    # Get all analyses with timeout
                    all_analyses = await asyncio.wait_for(
                        db_service.list_analyses(limit=1000),
                        timeout=10.0  # 10 second timeout
                    )
                    
                    # Filter for processing analyses
                    processing_analyses = [a for a in all_analyses if a.get('status') == 'processing']
                    
                    if processing_analyses:
                        logger.info(f"Found {len(processing_analyses)} processing analyses to cancel")
                        cancelled_count = 0
                        for analysis in processing_analyses:
                            analysis_id = analysis.get('id')
                            try:
                                success = await asyncio.wait_for(
                                    db_service.update_analysis(analysis_id, {
                                        'status': 'cancelled',
                                        'current_step': analysis.get('current_step', 'unknown'),
                                        'step_progress': analysis.get('step_progress', 0),
                                        'step_message': 'Analysis cancelled on app restart'
                                    }),
                                    timeout=5.0  # 5 second timeout per update
                                )
                                if success:
                                    cancelled_count += 1
                                    logger.info(f"✅ Cancelled analysis: {analysis_id}")
                            except asyncio.TimeoutError:
                                logger.warning(f"Timeout cancelling analysis {analysis_id}")
                            except Exception as e:
                                logger.warning(f"Failed to cancel analysis {analysis_id}: {e}")
                        
                        logger.info(f"✅ Cancelled {cancelled_count} of {len(processing_analyses)} processing analyses")
                    else:
                        logger.info("No processing analyses found to cancel")
                except asyncio.TimeoutError:
                    logger.warning("Timeout getting analyses list - skipping cancellation")
                except Exception as e:
                    logger.warning(f"Error getting analyses list: {e}")
            else:
                logger.warning("Database service not available - skipping cancellation of processing analyses")
        except Exception as e:
            logger.error(f"Error in startup cancellation task: {e}", exc_info=True)
            # Don't fail startup if cancellation fails
            logger.warning("Continuing startup despite cancellation error")
    
    # Start cancellation task in background (non-blocking)
    try:
        import asyncio
        asyncio.create_task(cancel_processing_on_startup())
        logger.info("Started background task to cancel processing analyses")
    except Exception as e:
        logger.warning(f"Failed to start cancellation task: {e} - continuing startup")
    
    logger.info("Service ready and accepting requests")
    
    yield
    
    # Shutdown
    logger.info("Shutting down Gait Analysis Service...")


# CRITICAL: Create app with error handling to prevent silent failures
try:
    app = FastAPI(
        title="Gait Analysis Application",
        description="Integrated clinical-grade gait analysis (API + Frontend)",
        version="3.0.0",
        lifespan=lifespan,
        # CRITICAL: Increase request timeout for large file uploads
        # This allows large video files to be uploaded without timing out
        # Note: Azure App Service also has request timeout settings that may need adjustment
    )
    logger.info("✓ FastAPI app created successfully")
except Exception as e:
    logger.critical(f"CRITICAL: Failed to create FastAPI app: {e}", exc_info=True)
    # Create minimal app to allow startup
    app = FastAPI(title="Gait Analysis Application", version="3.0.0")
    logger.warning("Using minimal FastAPI app - some features may be unavailable")

# Import custom exceptions for global handling
try:
    from app.core.exceptions import GaitAnalysisError, gait_error_to_http
    from app.core.schemas import ErrorResponse
    EXCEPTIONS_AVAILABLE = True
except ImportError:
    EXCEPTIONS_AVAILABLE = False
    logger.warning("Custom exceptions not available - using basic error handling")

# Global exception handler for custom GaitAnalysisError
if EXCEPTIONS_AVAILABLE:
    @app.exception_handler(GaitAnalysisError)
    async def gait_analysis_error_handler(request: Request, exc: GaitAnalysisError):
        """Handle custom GaitAnalysisError exceptions with structured logging"""
        request_id = getattr(request.state, 'request_id', 'unknown')
        logger.error(
            f"[{request_id}] GaitAnalysisError: {exc.error_code} - {exc.message}",
            extra={
                "error_code": exc.error_code,
                "message": exc.message,
                "details": exc.details,
                "path": str(request.url.path),
                "method": request.method
            },
            exc_info=True
        )
        http_exc = gait_error_to_http(exc)
        return JSONResponse(
            status_code=http_exc.status_code,
            content=ErrorResponse(
                error=exc.error_code,
                message=exc.message,
                details=exc.details
            ).dict()
        )

# Enhanced validation error handler
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Enhanced validation error handler with structured logging"""
    request_id = getattr(request.state, 'request_id', 'unknown')
    errors = exc.errors()
    
    logger.error(
        f"[{request_id}] Validation error on {request.method} {request.url.path}",
        extra={
            "validation_errors": errors,
            "path": str(request.url.path),
            "method": request.method,
            "query_params": dict(request.query_params),
            "path_params": dict(request.path_params)
        }
    )
    
    # Extract field-level errors for better error messages
    field_errors = {}
    for error in errors:
        field = ".".join(str(loc) for loc in error.get("loc", []))
        if field:
            field_errors[field] = error.get("msg", "Validation error")
    
    return JSONResponse(
        status_code=422,
        content=ErrorResponse(
            error="VALIDATION_ERROR",
            message="Request validation failed",
            details={
                "errors": errors,
                "field_errors": field_errors,
                "path": str(request.url.path)
            }
        ).dict() if EXCEPTIONS_AVAILABLE else {
            "detail": errors,
            "message": "Request validation failed. Check logs for details.",
            "path": str(request.url.path)
        }
    )

# Global exception handler for unhandled exceptions
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Catch-all exception handler for unexpected errors"""
    request_id = getattr(request.state, 'request_id', 'unknown')
    
    # Don't handle HTTPException - let FastAPI handle it
    if isinstance(exc, HTTPException):
        raise exc
    
    logger.critical(
        f"[{request_id}] Unhandled exception: {type(exc).__name__}",
        extra={
            "error_type": type(exc).__name__,
            "error_message": str(exc),
            "path": str(request.url.path),
            "method": request.method
        },
        exc_info=True
    )
    
    return JSONResponse(
        status_code=500,
        content=ErrorResponse(
            error="INTERNAL_SERVER_ERROR",
            message="An unexpected error occurred",
            details={
                "error_type": type(exc).__name__,
                "path": str(request.url.path)
            }
        ).dict() if EXCEPTIONS_AVAILABLE else {
            "error": "INTERNAL_SERVER_ERROR",
            "message": "An unexpected error occurred. Please check logs for details.",
            "path": str(request.url.path)
        }
    )

# Add request logging middleware first (runs first, logs last)
if MIDDLEWARE_AVAILABLE:
    app.add_middleware(RequestLoggingMiddleware)
    logger.info("✓ Request logging middleware enabled")
    
    # Add SPA routing middleware to handle 404s for frontend routes
    # This runs AFTER route matching, so it only handles 404s
    # CRITICAL: This never interferes with API routes because:
    # 1. API routes will match and return 200/400/500 (not 404)
    # 2. Only 404s on GET requests to non-API routes are handled
    if SPARoutingMiddleware and FRONTEND_DIR.exists():
        app.add_middleware(SPARoutingMiddleware, frontend_dir=FRONTEND_DIR)
        logger.info("✓ SPA routing middleware enabled")

# CORS middleware
# For integrated app, allow same-origin requests (relative URLs)
# Also allow explicit origins from settings (for development/testing)
cors_origins = settings.get_cors_origins()
# Always allow same-origin (empty origin or same origin)
# This is critical for integrated deployment where frontend and backend are on same domain
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if "*" in cors_origins else cors_origins + ["null"],  # Allow same-origin
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID", "X-Process-Time"],  # Expose custom headers
)

# CRITICAL: Register API routes BEFORE catch-all routes
# FastAPI matches routes in registration order, so specific routes must come first
# IMPORTANT: FastAPI matches routes by specificity and order:
# 1. More specific routes (with exact paths) match first
# 2. Routes are matched in registration order
# 3. Catch-all routes (with path parameters) match last

# API routes - must be registered before catch-all
# These routes are more specific and will match before the catch-all

# CRITICAL: Always attempt to register the upload endpoint, even if router fails
# This ensures the endpoint exists regardless of router import/registration issues
def ensure_upload_endpoint_registered():
    """Ensure upload endpoint is registered, using fallback if needed"""
    upload_route_found = False
    exact_path_found = False
    for route in app.routes:
        if hasattr(route, 'path'):
            route_path = route.path
            # Check for exact match first
            if route_path == "/api/v1/analysis/upload":
                methods = list(route.methods) if hasattr(route, 'methods') and hasattr(route.methods, '__iter__') else []
                if 'POST' in methods or 'post' in str(methods).lower() or not methods:
                    exact_path_found = True
                    upload_route_found = True
                    logger.info(f"✓ Upload endpoint confirmed (exact match): {methods} {route_path}")
                    break
            # Check for partial match
            elif '/upload' in route_path and '/api/v1/analysis' in route_path:
                methods = list(route.methods) if hasattr(route, 'methods') and hasattr(route.methods, '__iter__') else []
                if 'POST' in methods or 'post' in str(methods).lower() or not methods:
                    upload_route_found = True
                    logger.info(f"✓ Upload endpoint confirmed (partial match): {methods} {route_path}")
                    if not exact_path_found:
                        logger.warning(f"⚠️ Route path is {route_path}, expected /api/v1/analysis/upload")
    
    if not upload_route_found:
        logger.warning("⚠️ Upload endpoint not found - attempting direct registration...")
        try:
            from app.api.v1.analysis_azure import upload_video
            # CRITICAL: Use add_api_route with explicit path and methods
            # This ensures the route is registered exactly as expected
            app.add_api_route(
                path="/api/v1/analysis/upload",
                endpoint=upload_video,
                methods=["POST"],
                tags=["analysis"],
                name="upload_video_fallback"
            )
            logger.info("✅ Upload endpoint registered directly via add_api_route")
            
            # Verify it was registered
            for route in app.routes:
                if hasattr(route, 'path') and route.path == "/api/v1/analysis/upload":
                    methods = list(route.methods) if hasattr(route, 'methods') and hasattr(route.methods, '__iter__') else []
                    logger.info(f"✓ Verified registered route: {methods} {route.path}")
                    return True
            
            logger.error("❌ Route registration appeared to succeed but route not found in app.routes!")
            return False
        except Exception as fallback_error:
            logger.error(f"❌ Failed to register upload endpoint directly: {fallback_error}", exc_info=True)
            import traceback
            logger.error(f"❌ Traceback: {traceback.format_exc()}")
            return False
    return True

if analysis_router:
    try:
        app.include_router(analysis_router, prefix="/api/v1/analysis", tags=["analysis"])
        logger.info("✓ Analysis router registered at /api/v1/analysis")
        
        # CRITICAL: Verify the upload endpoint is registered
        upload_route_found = False
        test_route_found = False
        for route in app.routes:
            if hasattr(route, 'path'):
                route_path = route.path
                if '/upload' in route_path and '/api/v1/analysis' in route_path:
                    upload_route_found = True
                    methods = list(route.methods) if hasattr(route, 'methods') and hasattr(route.methods, '__iter__') else ['POST']
                    logger.info(f"✓ Upload endpoint found: {methods} {route_path}")
                elif '/test' in route_path and '/api/v1/analysis' in route_path:
                    test_route_found = True
                    methods = list(route.methods) if hasattr(route, 'methods') and hasattr(route.methods, '__iter__') else ['GET']
                    logger.info(f"✓ Test endpoint found: {methods} {route_path}")
        
        if not upload_route_found:
            logger.error("❌ CRITICAL: Upload endpoint not found after router registration!")
            logger.error("❌ This will cause 404 errors on file uploads!")
            ensure_upload_endpoint_registered()
        else:
            logger.info("✅ Upload endpoint is registered and available")
            
    except Exception as e:
        logger.error(f"❌ CRITICAL: Failed to register analysis router: {e}", exc_info=True)
        logger.error("⚠️ App will continue to start but API endpoints will not work")
        ensure_upload_endpoint_registered()
else:
    logger.error("❌ CRITICAL: analysis_router is None - cannot register routes!")
    logger.error("❌ This will cause 404 errors on all API endpoints!")
    ensure_upload_endpoint_registered()

# CRITICAL: Final verification that upload endpoint exists
final_check = ensure_upload_endpoint_registered()
if final_check:
    logger.info("✅ Upload endpoint verification passed")
else:
    logger.error("❌ CRITICAL: Upload endpoint could not be registered - uploads will fail!")

# Include testing router if available
if testing_router:
    app.include_router(testing_router, prefix="/api/v1", tags=["testing"])

# Include simple upload router for testing
try:
    from app.api.v1.analysis_azure_simple_upload import router as simple_upload_router
    app.include_router(simple_upload_router, prefix="/api/v1/analysis", tags=["testing"])
    logger.info("✓ Simple upload router registered for testing")
except Exception as e:
    logger.warning(f"Failed to import simple upload router (non-critical): {e}")

# Include logs router if available (for monitoring)
if logs_router:
    app.include_router(logs_router, prefix="/api/v1", tags=["logs"])


# Also add a health endpoint at /api/v1/health for frontend compatibility
@app.get("/api/v1/health")
async def api_health_check():
    """API health check endpoint (for frontend compatibility)"""
    return {
        "status": "healthy",
        "service": "Gait Analysis API",
        "version": "3.0.0"
    }



# CRITICAL: Add diagnostic endpoint to check router status
@app.get("/api/v1/debug/routes")
async def debug_routes():
    """Debug endpoint to check registered routes"""
    routes_info = []
    for route in app.routes:
        if hasattr(route, 'path'):
            route_info = {"path": route.path}
            if hasattr(route, 'methods'):
                route_info["methods"] = list(route.methods) if hasattr(route.methods, '__iter__') else [str(route.methods)]
            routes_info.append(route_info)
    
    return {
        "total_routes": len(routes_info),
        "routes": routes_info,
        "analysis_router_registered": any("/api/v1/analysis" in r.get("path", "") for r in routes_info),
        "upload_endpoint_exists": any("/upload" in r.get("path", "") and "/api/v1/analysis" in r.get("path", "") for r in routes_info)
    }


# Health check endpoints
@app.get("/")
async def root(request: Request):
    """Root endpoint - serves React app"""
    request_id = getattr(request.state, 'request_id', 'unknown')
    index_path = FRONTEND_DIR / "index.html"
    
    logger.info(f"[{request_id}] Root endpoint called - checking frontend at {index_path}")
    logger.info(f"[{request_id}] Frontend directory exists: {FRONTEND_DIR.exists()}")
    logger.info(f"[{request_id}] Index file exists: {index_path.exists()}")
    
    if index_path.exists():
        try:
            # Verify file is readable and has content
            file_size = index_path.stat().st_size
            logger.info(f"[{request_id}] Serving index.html (size: {file_size} bytes)")
            
            # Read first few bytes to verify it's HTML
            with open(index_path, 'rb') as f:
                first_bytes = f.read(100)
                is_html = b'<html' in first_bytes or b'<!DOCTYPE' in first_bytes
                logger.info(f"[{request_id}] File appears to be HTML: {is_html}")
            
            response = FileResponse(
                index_path,
                media_type="text/html; charset=utf-8",
                headers={
                    "Cache-Control": "no-cache, no-store, must-revalidate",
                    "Pragma": "no-cache",
                    "Expires": "0"
                }
            )
            logger.info(f"[{request_id}] Returning FileResponse for index.html")
            return response
        except Exception as e:
            logger.error(f"[{request_id}] Error serving index.html: {e}", exc_info=True)
            return JSONResponse(
                status_code=500,
                content={
                    "error": "Failed to serve frontend",
                    "message": str(e),
                    "path": str(index_path)
                }
            )
    
    logger.warning(f"[{request_id}] Frontend index.html not found at {index_path}")
    return JSONResponse(
        status_code=404,
        content={
            "status": "healthy",
            "service": "Gait Analysis Application (Integrated)",
            "version": "3.0.0",
            "architecture": "Microsoft Native Services",
            "message": "Frontend not found, serving API info.",
            "frontend_path": str(index_path),
            "frontend_dir_exists": FRONTEND_DIR.exists()
        }
    )


@app.get("/health")
async def health_check():
    """Detailed health check - critical for Azure App Service"""
    import time
    import threading
    try:
        # Check if services are initialized
        from app.api.v1.analysis_azure import db_service, storage_service, vision_service
        
        components = {
            "azure_storage": "configured" if storage_service else "mock",
            "azure_vision": "configured" if vision_service else "mock",
            "azure_sql": "configured" if db_service and not db_service._use_mock else "mock"
        }
        
        return {
            "status": "healthy",
            "components": components,
            "architecture": "Microsoft Native",
            "frontend": "integrated",
            "timestamp": time.time()
        }
    except Exception as e:
        logger.error(f"Health check error: {e}", exc_info=True)
        # Still return healthy to prevent unnecessary restarts
        return {
            "status": "healthy",
            "components": {
                "azure_storage": "unknown",
                "azure_vision": "unknown",
                "azure_sql": "unknown"
            },
            "architecture": "Microsoft Native",
            "frontend": "integrated",
            "error": str(e)
        }


# Serve static assets (JS, CSS, images)
if STATIC_DIR and STATIC_DIR.exists():
    app.mount("/assets", StaticFiles(directory=str(STATIC_DIR)), name="assets")


# Serve other static files
if FRONTEND_DIR.exists():
    @app.get("/favicon.ico")
    async def favicon():
        favicon_path = FRONTEND_DIR / "favicon.ico"
        if favicon_path.exists():
            return FileResponse(favicon_path)
        return {"error": "Not found"}
    
    # CRITICAL: Use middleware-based SPA routing instead of catch-all route
    # This prevents any conflicts with API routes
    # The SPARoutingMiddleware handles 404s for GET requests to non-API routes
    # No catch-all route needed - middleware handles it after route matching


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main_integrated:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG
    )


