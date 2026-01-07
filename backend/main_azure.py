"""
Main FastAPI application - Microsoft Native Architecture
Minimal dependencies - only Azure SDKs
"""
import sys
import logging

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

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from app.core.config_simple import settings
from app.api.v1.analysis_azure import router as analysis_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    # Startup
    logger.info("Starting Gait Analysis Service (Microsoft Native Architecture)...")
    logger.info("Services: Azure Blob Storage, Computer Vision, SQL Database")
    logger.info("Service ready and accepting requests")
    
    yield
    
    # Shutdown
    logger.info("Shutting down Gait Analysis Service...")


app = FastAPI(
    title="Gait Analysis API (Azure Native)",
    description="Clinical-grade gait analysis using Microsoft Azure services",
    version="2.0.0",
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

# Include routers
app.include_router(analysis_router, prefix="/api/v1/analysis", tags=["analysis"])


@app.get("/")
async def root():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "Gait Analysis API (Azure Native)",
        "version": "2.0.0",
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
        "architecture": "Microsoft Native"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main_azure:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG
    )


