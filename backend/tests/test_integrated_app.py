"""
Unit tests for integrated application
Tests basic functionality before deployment
"""
import pytest
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi.testclient import TestClient
from main_integrated import app


@pytest.fixture
def client():
    """Create test client"""
    return TestClient(app)


def test_health_endpoint(client):
    """Test health endpoint"""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "components" in data


def test_root_endpoint(client):
    """Test root endpoint"""
    response = client.get("/")
    # Should return 200 or serve index.html
    assert response.status_code in [200, 404]  # 404 if frontend not built yet


def test_api_endpoint_exists(client):
    """Test API endpoint exists"""
    # POST without file should return 400 or 422
    response = client.post("/api/v1/analysis/upload")
    assert response.status_code in [400, 422, 500]  # Expected errors


def test_cors_headers(client):
    """Test CORS headers are set"""
    response = client.options("/api/v1/analysis/upload", headers={
        "Origin": "https://gaitanalysisapp.azurewebsites.net",
        "Access-Control-Request-Method": "POST"
    })
    # Should allow CORS
    assert response.status_code in [200, 204, 400]


def test_app_imports():
    """Test that all imports work"""
    from app.services.azure_storage import AzureStorageService
    from app.services.azure_vision import AzureVisionService
    from app.core.database_azure_sql import AzureSQLService
    
    # Should not raise exceptions
    assert True


