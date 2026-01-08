"""
Pydantic schemas for API request/response validation
Provides strong type checking and validation
"""
from pydantic import BaseModel, Field, validator, HttpUrl
from typing import Optional, Dict, Any, List
from datetime import datetime
from enum import Enum


class ViewType(str, Enum):
    """Valid view types for gait analysis"""
    FRONT = "front"
    SIDE = "side"
    BACK = "back"


class AnalysisStatus(str, Enum):
    """Valid analysis statuses"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class VideoUploadRequest(BaseModel):
    """Request model for video upload with validation"""
    patient_id: Optional[str] = Field(None, max_length=100, description="Patient identifier")
    view_type: ViewType = Field(ViewType.FRONT, description="Camera view type")
    reference_length_mm: Optional[float] = Field(
        None, 
        gt=0, 
        le=10000, 
        description="Reference length in millimeters for scale calibration"
    )
    fps: float = Field(30.0, gt=0, le=120, description="Video frames per second")
    
    @validator('patient_id')
    def validate_patient_id(cls, v):
        if v is not None and len(v.strip()) == 0:
            raise ValueError("patient_id cannot be empty string")
        return v
    
    @validator('fps')
    def validate_fps(cls, v):
        if v <= 0:
            raise ValueError("fps must be greater than 0")
        if v > 120:
            raise ValueError("fps cannot exceed 120")
        return v
    
    @validator('reference_length_mm')
    def validate_reference_length(cls, v):
        if v is not None and v <= 0:
            raise ValueError("reference_length_mm must be greater than 0")
        if v is not None and v > 10000:
            raise ValueError("reference_length_mm cannot exceed 10000mm (10m)")
        return v
    
    class Config:
        use_enum_values = True
        schema_extra = {
            "example": {
                "patient_id": "PATIENT_001",
                "view_type": "front",
                "reference_length_mm": 1000.0,
                "fps": 30.0
            }
        }


class AnalysisResponse(BaseModel):
    """Response model for analysis operations"""
    analysis_id: str = Field(..., description="Unique analysis identifier")
    status: AnalysisStatus = Field(..., description="Current analysis status")
    message: str = Field(..., description="Status message")
    patient_id: Optional[str] = Field(None, description="Patient identifier")
    created_at: Optional[datetime] = Field(None, description="Analysis creation timestamp")
    
    class Config:
        use_enum_values = True
        schema_extra = {
            "example": {
                "analysis_id": "123e4567-e89b-12d3-a456-426614174000",
                "status": "processing",
                "message": "Video uploaded successfully. Analysis in progress.",
                "patient_id": "PATIENT_001",
                "created_at": "2024-01-08T12:00:00Z"
            }
        }


class AnalysisDetailResponse(BaseModel):
    """Detailed analysis response with metrics"""
    id: str
    patient_id: Optional[str]
    filename: str
    video_url: Optional[str]
    status: AnalysisStatus
    current_step: Optional[str]
    step_progress: int = Field(0, ge=0, le=100)
    step_message: Optional[str]
    metrics: Optional[Dict[str, Any]]
    created_at: Optional[datetime]
    updated_at: Optional[datetime]
    
    class Config:
        use_enum_values = True


class AnalysisListResponse(BaseModel):
    """Response model for listing analyses"""
    analyses: List[AnalysisDetailResponse]
    total: int = Field(..., ge=0, description="Total number of analyses")
    limit: int = Field(..., ge=1, le=1000, description="Requested limit")
    
    class Config:
        schema_extra = {
            "example": {
                "analyses": [],
                "total": 0,
                "limit": 50
            }
        }


class ErrorResponse(BaseModel):
    """Standard error response model"""
    error: str = Field(..., description="Error code")
    message: str = Field(..., description="Error message")
    details: Optional[Dict[str, Any]] = Field(None, description="Additional error details")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Error timestamp")
    
    class Config:
        schema_extra = {
            "example": {
                "error": "VALIDATION_ERROR",
                "message": "Invalid input parameter",
                "details": {"field": "fps", "value": -1},
                "timestamp": "2024-01-08T12:00:00Z"
            }
        }


class HealthResponse(BaseModel):
    """Health check response"""
    status: str = Field(..., description="Service status")
    service: str = Field(..., description="Service name")
    version: str = Field(..., description="Service version")
    components: Optional[Dict[str, str]] = Field(None, description="Component statuses")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Check timestamp")
