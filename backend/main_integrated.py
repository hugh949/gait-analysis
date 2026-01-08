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

# Import app modules with error handling
try:
    from app.core.config_simple import settings
except Exception as e:
    logger.error(f"Failed to import settings: {e}", exc_info=True)
    raise

try:
    from app.api.v1.analysis_azure import router as analysis_router
except Exception as e:
    logger.error(f"Failed to import analysis router: {e}", exc_info=True)
    raise

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
    logger.info("Service ready and accepting requests")
    
    yield
    
    # Shutdown
    logger.info("Shutting down Gait Analysis Service...")


app = FastAPI(
    title="Gait Analysis Application",
    description="Integrated clinical-grade gait analysis (API + Frontend)",
    version="3.0.0",
    lifespan=lifespan
)

# Add exception handler for validation errors to log them
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Log validation errors for debugging"""
    logger.error(f"Validation error on {request.method} {request.url.path}")
    logger.error(f"Validation errors: {exc.errors()}")
    logger.error(f"Request URL: {request.url}")
    return JSONResponse(
        status_code=422,
        content={
            "detail": exc.errors(),
            "message": "Request validation failed. Check logs for details.",
            "path": str(request.url.path)
        }
    )

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
    expose_headers=["*"],
)

# CRITICAL: Register API routes BEFORE catch-all routes
# FastAPI matches routes in registration order, so specific routes must come first

# API routes - must be registered before catch-all
app.include_router(analysis_router, prefix="/api/v1/analysis", tags=["analysis"])

# Also add a health endpoint at /api/v1/health for frontend compatibility
@app.get("/api/v1/health")
async def api_health_check():
    """API health check endpoint (for frontend compatibility)"""
    return {
        "status": "healthy",
        "service": "Gait Analysis API",
        "version": "3.0.0"
    }


# Health check endpoints
@app.get("/")
async def root():
    """Root endpoint - serves React app"""
    index_path = FRONTEND_DIR / "index.html"
    if index_path.exists():
        return FileResponse(index_path)
    return {
        "status": "healthy",
        "service": "Gait Analysis Application (Integrated)",
        "version": "3.0.0",
        "architecture": "Microsoft Native Services"
    }


@app.get("/health")
async def health_check():
    """Detailed health check"""
    return {
        "status": "healthy",
        "components": {
            "azure_storage": "configured",
            "azure_vision": "configured",
            "azure_sql": "configured"
        },
        "architecture": "Microsoft Native",
        "frontend": "integrated"
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
    
    @app.get("/{full_path:path}")
    async def serve_spa(request: Request, full_path: str):
        """
        Serve React SPA - all non-API routes return index.html
        This enables client-side routing
        
        NOTE: This catch-all route should NOT match API routes because:
        1. API routes are registered before this (more specific routes match first)
        2. FastAPI matches routes in registration order
        3. If an API route doesn't match, this will catch it (which is fine for 404s)
        """
        # Double-check: if this somehow matches an API route, return 404
        # (This shouldn't happen due to route ordering, but safety check)
        if full_path.startswith("api/"):
            logger.warning(f"API route caught by catch-all: {full_path} - this shouldn't happen!")
            return {"error": "API route not found", "path": full_path}
        
        # Serve index.html for all other routes (React SPA routing)
        index_path = FRONTEND_DIR / "index.html"
        if index_path.exists():
            return FileResponse(index_path)
        return {"error": "Frontend not found"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main_integrated:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG
    )


