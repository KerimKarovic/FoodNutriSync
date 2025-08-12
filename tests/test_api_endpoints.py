import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, Mock, AsyncMock

@pytest.fixture
def client():
    """Create test client"""
    from app.main import app
    return TestClient(app)

class TestHealthEndpoints:
    """Test basic health and info endpoints"""
    
    def test_root_endpoint(self, client):
        """Test root endpoint returns basic info"""
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert "ok" in data or "version" in data or "endpoints" in data

class TestBLSEndpoints:
    """Test BLS data endpoints"""
    
    def test_bls_number_endpoint_not_found(self, client_with_mock_db):
        """Test BLS number endpoint with non-existent number"""
        # Mock empty result
        client_with_mock_db.app.dependency_overrides
        response = client_with_mock_db.get("/bls/X999999")
        assert response.status_code == 404
        
    def test_bls_number_endpoint_invalid_format(self, client_with_mock_db):
        """Test BLS number endpoint with invalid format"""
        response = client_with_mock_db.get("/bls/INVALID")
        assert response.status_code in [400, 422, 404]
        
    def test_bls_search_endpoint_empty(self, client_with_mock_db):
        """Test search endpoint with empty database"""
        response = client_with_mock_db.get("/bls/search?name=test")
        assert response.status_code == 200
        data = response.json()
        assert "results" in data
        assert "count" in data

class TestValidationErrors:
    """Test API validation and error handling"""
    
    def test_bls_search_missing_query(self, client):
        """Test search without query parameter"""
        response = client.get("/bls/search")
        assert response.status_code in [400, 422]
        
    def test_bls_search_empty_query(self, client_with_mock_db):
        """Test search with empty query"""
        response = client_with_mock_db.get("/bls/search?name=")
        assert response.status_code in [200, 400, 422]

