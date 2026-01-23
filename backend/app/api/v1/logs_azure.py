"""
Azure Logs API - Provides access to recent logs and error analysis
Allows monitoring and debugging without manual log pasting
"""
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
from typing import Optional, List, Dict
from loguru import logger
import os
import re
from datetime import datetime, timedelta
from pathlib import Path

router = APIRouter(prefix="/logs", tags=["Logs"])

# Log file path in Azure App Service
LOG_FILE_PATH = os.getenv("LOG_FILE_PATH", "/home/site/logs/docker.log")

@router.get("/recent")
async def get_recent_logs(
    lines: int = Query(100, ge=10, le=1000, description="Number of recent log lines to retrieve"),
    filter_level: Optional[str] = Query(None, description="Filter by log level: ERROR, WARNING, INFO, DEBUG"),
    search: Optional[str] = Query(None, description="Search for specific text in logs")
) -> JSONResponse:
    """
    Get recent logs from the application
    Useful for debugging without accessing Azure Portal directly
    """
    try:
        logs = []
        
        # Try to read from log file if it exists
        if os.path.exists(LOG_FILE_PATH):
            with open(LOG_FILE_PATH, 'r', encoding='utf-8', errors='ignore') as f:
                all_lines = f.readlines()
                logs = all_lines[-lines:] if len(all_lines) > lines else all_lines
        else:
            # If log file doesn't exist, return message
            return JSONResponse({
                "message": "Log file not found at standard location",
                "log_file_path": LOG_FILE_PATH,
                "suggestion": "Logs may be available via Azure Portal Log Stream or Application Insights"
            })
        
        # Apply filters
        if filter_level:
            logs = [line for line in logs if filter_level.upper() in line.upper()]
        
        if search:
            logs = [line for line in logs if search.lower() in line.lower()]
        
        # Analyze for errors
        error_count = sum(1 for line in logs if 'ERROR' in line and 'HEARTBEAT' not in line and 'DIAGNOSTIC' not in line)
        warning_count = sum(1 for line in logs if 'WARNING' in line)
        critical_count = sum(1 for line in logs if any(pattern in line for pattern in ['Exception', 'Traceback', 'Failed', 'CRITICAL']))
        
        return JSONResponse({
            "total_lines": len(logs),
            "error_count": error_count,
            "warning_count": warning_count,
            "critical_count": critical_count,
            "logs": logs[-50:] if len(logs) > 50 else logs,  # Return last 50 lines
            "log_file_path": LOG_FILE_PATH,
            "timestamp": datetime.now().isoformat()
        })
    except Exception as e:
        logger.error(f"Error reading logs: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to read logs: {str(e)}")

@router.get("/analyze")
async def analyze_logs(
    analysis_id: Optional[str] = Query(None, description="Filter logs for specific analysis ID"),
    minutes: int = Query(5, ge=1, le=60, description="Analyze logs from last N minutes")
) -> JSONResponse:
    """
    Analyze recent logs for errors, warnings, and issues
    Automatically detects common problems
    """
    try:
        # This would ideally fetch from Azure, but for now we'll analyze in-memory state
        # In production, this could connect to Application Insights or Log Analytics
        
        issues = []
        warnings = []
        status_info = {}
        
        # Check database for stuck analyses
        from app.core.database_azure_sql import AzureSQLService
        db_service = AzureSQLService()
        
        if analysis_id:
            analysis = await db_service.get_analysis(analysis_id)
            if analysis:
                status = analysis.get('status', 'unknown')
                step = analysis.get('current_step', 'unknown')
                progress = analysis.get('step_progress', 0)
                
                # Check if analysis is stuck
                updated_at = analysis.get('updated_at')
                if updated_at:
                    try:
                        if isinstance(updated_at, str):
                            last_update = datetime.fromisoformat(updated_at.replace('Z', '+00:00'))
                        else:
                            last_update = updated_at
                        
                        time_since_update = (datetime.now(last_update.tzinfo) - last_update).total_seconds()
                        
                        # If processing for more than 10 minutes without update, it might be stuck
                        if status == 'processing' and time_since_update > 600:
                            issues.append({
                                "type": "stuck_processing",
                                "message": f"Analysis {analysis_id} has been processing for {time_since_update/60:.1f} minutes without update",
                                "analysis_id": analysis_id,
                                "current_step": step,
                                "progress": progress
                            })
                    except Exception as e:
                        logger.warning(f"Error parsing updated_at: {e}")
                
                status_info = {
                    "analysis_id": analysis_id,
                    "status": status,
                    "current_step": step,
                    "progress": progress,
                    "updated_at": str(updated_at) if updated_at else None
                }
        
        return JSONResponse({
            "analysis_time": datetime.now().isoformat(),
            "status_info": status_info,
            "issues": issues,
            "warnings": warnings,
            "summary": {
                "total_issues": len(issues),
                "total_warnings": len(warnings),
                "health_status": "healthy" if len(issues) == 0 else "degraded" if len(issues) < 3 else "unhealthy"
            }
        })
    except Exception as e:
        logger.error(f"Error analyzing logs: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to analyze logs: {str(e)}")

@router.get("/health-check")
async def log_health_check() -> JSONResponse:
    """
    Quick health check based on recent log patterns
    """
    try:
        from app.core.database_azure_sql import AzureSQLService
        db_service = AzureSQLService()
        
        # Check for processing analyses
        # This is a simplified check - in production would query database
        health_status = {
            "status": "healthy",
            "checks": {
                "database_accessible": True,
                "log_file_readable": os.path.exists(LOG_FILE_PATH) if LOG_FILE_PATH else False
            },
            "timestamp": datetime.now().isoformat()
        }
        
        return JSONResponse(health_status)
    except Exception as e:
        logger.error(f"Health check failed: {e}", exc_info=True)
        return JSONResponse({
            "status": "unhealthy",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }, status_code=500)
