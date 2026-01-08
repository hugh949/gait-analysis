"""
Custom exception classes for the application
Provides structured error handling with proper error codes and messages
"""
from typing import Optional, Dict, Any
from fastapi import HTTPException, status


class GaitAnalysisError(Exception):
    """Base exception for gait analysis errors"""
    def __init__(self, message: str, error_code: str = "GAIT_ERROR", details: Optional[Dict[str, Any]] = None):
        self.message = message
        self.error_code = error_code
        self.details = details or {}
        super().__init__(self.message)


class VideoProcessingError(GaitAnalysisError):
    """Error during video processing"""
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message, "VIDEO_PROCESSING_ERROR", details)


class PoseEstimationError(GaitAnalysisError):
    """Error during pose estimation"""
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message, "POSE_ESTIMATION_ERROR", details)


class GaitMetricsError(GaitAnalysisError):
    """Error during gait metrics calculation"""
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message, "GAIT_METRICS_ERROR", details)


class ValidationError(GaitAnalysisError):
    """Input validation error"""
    def __init__(self, message: str, field: Optional[str] = None, details: Optional[Dict[str, Any]] = None):
        error_details = details or {}
        if field:
            error_details["field"] = field
        super().__init__(message, "VALIDATION_ERROR", error_details)


class StorageError(GaitAnalysisError):
    """Error with storage operations"""
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message, "STORAGE_ERROR", details)


class DatabaseError(GaitAnalysisError):
    """Error with database operations"""
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message, "DATABASE_ERROR", details)


def gait_error_to_http(exception: GaitAnalysisError) -> HTTPException:
    """Convert GaitAnalysisError to HTTPException with proper status code"""
    # Map error codes to HTTP status codes
    status_map = {
        "VALIDATION_ERROR": status.HTTP_400_BAD_REQUEST,
        "VIDEO_PROCESSING_ERROR": status.HTTP_422_UNPROCESSABLE_ENTITY,
        "POSE_ESTIMATION_ERROR": status.HTTP_500_INTERNAL_SERVER_ERROR,
        "GAIT_METRICS_ERROR": status.HTTP_500_INTERNAL_SERVER_ERROR,
        "STORAGE_ERROR": status.HTTP_503_SERVICE_UNAVAILABLE,
        "DATABASE_ERROR": status.HTTP_503_SERVICE_UNAVAILABLE,
    }
    
    http_status = status_map.get(exception.error_code, status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    return HTTPException(
        status_code=http_status,
        detail={
            "error": exception.error_code,
            "message": exception.message,
            "details": exception.details
        }
    )
