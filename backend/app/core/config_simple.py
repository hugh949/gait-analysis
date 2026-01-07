"""
Simplified Application Configuration - No Pydantic Issues
"""
import os
from typing import List
from dotenv import load_dotenv

load_dotenv()

# Simple settings class - no pydantic
class Settings:
    """Application settings - simple Python class"""
    
    # Application
    APP_NAME: str = "Gait Analysis Service"
    DEBUG: bool = os.getenv("DEBUG", "False").lower() == "true"
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "8000"))
    
    # CORS - Simple function, no pydantic
    @staticmethod
    def get_cors_origins() -> List[str]:
        """Get CORS origins as list"""
        cors_str = os.getenv(
            "CORS_ORIGINS", 
            "http://localhost:3000,http://localhost:5173,https://jolly-meadow-0a467810f.1.azurestaticapps.net"
        )
        return [origin.strip() for origin in cors_str.split(",") if origin.strip()]
    
    # Azure Services
    AZURE_STORAGE_CONNECTION_STRING: str = os.getenv("AZURE_STORAGE_CONNECTION_STRING", "")
    AZURE_STORAGE_CONTAINER: str = os.getenv("AZURE_STORAGE_CONTAINER", "gait-videos")
    AZURE_COSMOS_ENDPOINT: str = os.getenv("AZURE_COSMOS_ENDPOINT", "")
    AZURE_COSMOS_KEY: str = os.getenv("AZURE_COSMOS_KEY", "")
    AZURE_COSMOS_DATABASE: str = os.getenv("AZURE_COSMOS_DATABASE", "gait-analysis")
    
    # Processing
    MAX_VIDEO_SIZE_MB: int = 500
    SUPPORTED_VIDEO_FORMATS: List[str] = [".mp4", ".avi", ".mov", ".mkv"]

settings = Settings()



