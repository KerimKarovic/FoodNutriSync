import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, AsyncMock


class TestSmoke:
    """Core smoke tests - run on every push"""
    
    @pytest.mark.smoke
    def test_health_endpoints_json_format(self, client_with_mock_db):
        """Health endpoints return proper JSON with status"""
        # Liveness - always works
        response = client_with_mock_db.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert data["status"] == "healthy"
        
        # Live endpoint
        response = client_with_mock_db.get("/health/live")
        assert response.status_code == 200
        
        # Readiness with DB
        response = client_with_mock_db.get("/health/ready")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data

    @pytest.mark.smoke
    def test_openapi_docs_accessible(self, client_with_mock_db):
        """API docs are accessible"""
        response = client_with_mock_db.get("/openapi.json")
        assert response.status_code == 200
        data = response.json()
        assert "openapi" in data
        
        response = client_with_mock_db.get("/docs")
        assert response.status_code == 200

    @pytest.mark.smoke
    def test_bls_search_public_access(self, public_client):
        """BLS search works without auth"""
        with patch('app.main.bls_service.search_by_name') as mock_search:
            mock_search.return_value = []
            response = public_client.get("/bls/search?name=test")
            assert response.status_code == 200

    @pytest.mark.smoke
    @pytest.mark.parametrize("bls_number,expected_status", [
        ("B123456", 404),  # Valid format, not found
        ("invalid", 422),  # Invalid format
    ])
    def test_bls_lookup_validation(self, public_client, bls_number, expected_status):
        """BLS lookup validates format correctly"""
        response = public_client.get(f"/bls/{bls_number}")
        assert response.status_code == expected_status

    @pytest.mark.smoke
    def test_admin_upload_requires_auth(self, client_with_mock_db):
        """Admin endpoints require authentication"""
        files = {"file": ("test.txt", "content", "text/plain")}
        response = client_with_mock_db.put("/admin/upload-bls", files=files)
        assert response.status_code == 401


class TestSearchUX:
    """Search user experience tests"""
    
    @pytest.mark.parametrize("query,should_work", [
        ("Äpfel", True),  # Umlaut
        ("Apfel", True),  # ASCII
        ("Müsli", True),  # Another umlaut
        ("<script>alert('xss')</script>", True),  # XSS attempt
        ("'; DROP TABLE bls; --", True),  # SQL injection attempt
        ("a" * 1000, True),  # Long string
        ("", False),  # Empty query
    ])
    def test_search_edge_cases(self, public_client, query, should_work):
        """Search handles various input types"""
        with patch('app.main.bls_service.search_by_name') as mock_search:
            mock_search.return_value = []
            
            response = public_client.get(f"/bls/search?name={query}")
            
            if should_work:
                assert response.status_code == 200
            else:
                assert response.status_code == 422

    @pytest.mark.parametrize("limit,expected_status", [
        (1, 200),
        (50, 200), 
        (100, 200),
        (101, 422),
        (-1, 422),
        (0, 422),
    ])
    def test_limit_validation(self, public_client, limit, expected_status):
        """Search limit validation"""
        with patch('app.main.bls_service.search_by_name') as mock_search:
            mock_search.return_value = []
            
            response = public_client.get(f"/bls/search?name=test&limit={limit}")
            assert response.status_code == expected_status

class TestSecurity:
    """Authentication and security tests"""
    
    @pytest.mark.security
    def test_public_endpoints_no_auth_required(self, public_client):
        """Public endpoints work without auth"""
        endpoints = ["/health", "/health/live", "/health/ready", "/docs", "/openapi.json"]
        
        for endpoint in endpoints:
            response = public_client.get(endpoint)
            assert response.status_code in [200, 503]  # 503 for readiness if DB down

    @pytest.mark.security
    def test_admin_endpoints_require_auth(self, client_with_mock_db):
        """Admin endpoints require authentication"""
        files = {"file": ("test.txt", "content", "text/plain")}
        response = client_with_mock_db.put("/admin/upload-bls", files=files)
        assert response.status_code == 401


class TestIntegration:
    """End-to-end integration tests"""
    
    # Removed test_upload_then_search_workflow



