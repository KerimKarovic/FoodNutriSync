import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, Mock, AsyncMock
from app.exceptions import BLSNotFoundError, BLSValidationError
from app.schemas import BLSNutrientResponse, BLSSearchResponse, BLSUploadResponse

# Remove the duplicate client fixture - use the one from conftest.py

class TestHealthEndpoint:
    def test_health_endpoint(self, client_with_mock_db):
        response = client_with_mock_db.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") in ("ok", "degraded")
        assert "version" in data
        assert "uptime_s" in data


class TestBLSEndpoints:
    """Test BLS API endpoints"""
    
    def test_search_route_not_confused_with_bls_number(self, client_with_mock_db):
        """Test search route works correctly"""
        response = client_with_mock_db.get("/bls/search?name=test")
        assert response.status_code == 200
        data = response.json()
        assert "results" in data and "count" in data
    
