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

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from contextlib import asynccontextmanager
import os

from app.core.config_simple import settings
from app.api.v1.analysis_azure import router as analysis_router

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

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.get_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API routes
app.include_router(analysis_router, prefix="/api/v1/analysis", tags=["analysis"])


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
    async def serve_spa(full_path: str):
        """
        Serve React SPA - all non-API routes return index.html
        This enables client-side routing
        """
        # Don't serve API routes
        if full_path.startswith("api/"):
            return {"error": "Not found"}
        
        # Serve index.html for all other routes
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


