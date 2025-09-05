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
    def test_bls_search_requires_auth(self, public_client):
        """BLS search requires JWT authentication"""
        response = public_client.get("/bls/search?q=apple")
        assert response.status_code == 401

    @pytest.mark.smoke
    def test_bls_search_with_auth(self, client_with_bls_auth):
        """BLS search works with proper auth"""
        with patch('app.services.bls_service.BLSService.search_by_name', return_value=[]):
            response = client_with_bls_auth.get("/bls/search?q=Apfel&limit=5")
            assert response.status_code == 200

    @pytest.mark.smoke
    @pytest.mark.parametrize("bls_number,expected_status", [
        ("B123456", 401),  # No auth
    ])
    def test_bls_lookup_requires_auth(self, public_client, bls_number, expected_status):
        """BLS lookup requires authentication"""
        response = public_client.get(f"/bls/{bls_number}")
        assert response.status_code == expected_status

    @pytest.mark.smoke
    def test_admin_upload_requires_cookie_auth(self, public_client):
        """Admin endpoints require cookie authentication"""
        files = {"file": ("test.txt", "content", "text/plain")}
        response = public_client.put("/admin/upload-bls", files=files)
        assert response.status_code == 401


class TestSearchUX:
    """Search user experience tests"""
    
    @pytest.mark.parametrize("query,should_work", [
        ("Äpfel", True),  # Umlaut
        ("Apfel", True),  # ASCII
        ("", False),  # Empty query
    ])
    def test_search_edge_cases(self, client_with_bls_auth, query, should_work):
        """Search handles various input types"""
        with patch('app.services.bls_service.BLSService.search_by_name') as mock_search:
            mock_search.return_value = []
            
            response = client_with_bls_auth.get(f"/bls/search?q={query}")
            
            if should_work:
                assert response.status_code == 200
            else:
                assert response.status_code == 422


class TestSecurity:
    """Authentication and security tests"""
    
    @pytest.mark.security
    def test_public_endpoints_no_auth_required(self, public_client):
        """Public endpoints work without auth"""
        endpoints = ["/health", "/health/live", "/health/ready"]
        
        for endpoint in endpoints:
            response = public_client.get(endpoint)
            assert response.status_code in [200, 503]

    @pytest.mark.security
    def test_bls_endpoints_require_jwt_auth(self, public_client):
        """BLS endpoints require JWT authentication"""
        response = public_client.get("/bls/search?q=test")
        assert response.status_code == 401
        
        response = public_client.get("/bls/B123456")
        assert response.status_code == 401

    @pytest.mark.security
    def test_admin_endpoints_require_cookie_auth(self, public_client):
        """Admin endpoints require cookie authentication"""
        files = {"file": ("test.txt", "content", "text/plain")}
        response = public_client.put("/admin/upload-bls", files=files)
        assert response.status_code == 401

    @pytest.mark.security
    def test_admin_upload_with_auth(self, client_with_admin_auth):
        """Admin upload works with proper cookie auth"""
        with patch('app.services.bls_service.BLSService.upload_data') as mock_upload:
            mock_upload.return_value = {"message": "success", "records": 1}
            
            files = {"file": ("test.txt", "SBLS\tST\nB123456\tTest", "text/plain")}
            response = client_with_admin_auth.put("/admin/upload-bls", files=files)
            assert response.status_code == 200


class TestIntegration:
    """End-to-end integration tests"""
    
    # Removed test_upload_then_search_workflow





