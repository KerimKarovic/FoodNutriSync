import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, Mock, AsyncMock
from app.exceptions import BLSNotFoundError, BLSValidationError
from app.schemas import BLSNutrientResponse, BLSSearchResponse

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
        assert "message" in data or "version" in data

class TestBLSEndpoints:
    """Test BLS API endpoints"""
    
    @pytest.mark.parametrize("bls_number,expected_status", [
        ("B123456", 404),  # No data in test DB
        ("INVALID", 422),  # Invalid format should return 422
        # Remove "search" test case since it matches the search route
    ])
    def test_bls_number_validation(self, bls_number, expected_status, client):
        """Test BLS number validation"""
        response = client.get(f"/bls/{bls_number}")
        assert response.status_code == expected_status

    def test_search_route_not_confused_with_bls_number(self, client):
        """Test that /bls/search goes to search endpoint, not BLS lookup"""
        response = client.get("/bls/search")
        assert response.status_code == 200
        data = response.json()
        assert "results" in data
        assert "count" in data

    @patch('app.services.bls_service.BLSService.search_by_name')
    def test_search_endpoint_success(self, mock_search_method, client_with_mock_db):
        """Test successful search"""
        # Mock service response with proper response object
        mock_response = BLSSearchResponse(
            results=[BLSNutrientResponse(bls_number="B123456", name_german="Test Food")],
            count=1
        )
        mock_search_method.return_value = mock_response
        
        response = client_with_mock_db.get("/bls/search?name=test")
        if response.status_code != 200:
            print(f"Search error response: {response.text}")
        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 1
        assert len(data["results"]) == 1

    def test_search_endpoint_missing_name(self, client_with_mock_db):
        """Test search endpoint without name parameter"""
        response = client_with_mock_db.get("/bls/search")
        assert response.status_code == 200  # Should work with default empty name

class TestValidationErrors:
    """Test API validation and error handling"""
    
    def test_bls_search_missing_query(self, client):
        """Test search without query parameter"""
        response = client.get("/bls/search")
        assert response.status_code == 200  # Should work with default empty name
        
    @patch('app.services.bls_service.BLSService.search_by_name')
    def test_bls_search_empty_query(self, mock_search_method, client_with_mock_db):
        """Test search with empty query"""
        # Mock empty response
        mock_response = BLSSearchResponse(results=[], count=0)
        mock_search_method.return_value = mock_response
        
        response = client_with_mock_db.get("/bls/search?name=")
        if response.status_code != 200:
            print(f"Empty query error response: {response.text}")
        # Should return 200 with empty results
        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 0






