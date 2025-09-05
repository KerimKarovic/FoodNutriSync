import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
from app.main import app

class TestAuthEndpoints:
    """Test authentication endpoints"""
    
    def test_user_login_endpoint_exists(self):
        """User login endpoint accepts JWT tokens"""
        client = TestClient(app)
        
        with patch('app.auth.jwt_verifier.decode') as mock_decode:
            mock_decode.return_value = {"sub": "test@example.com"}
            
            response = client.post("/auth/login", json={"token": "valid.jwt.token"})
            assert response.status_code == 200
            assert response.json()["status"] == "ok"

    def test_user_logout_endpoint(self):
        """User logout endpoint works"""
        client = TestClient(app)
        response = client.post("/auth/logout")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

    def test_admin_login_requires_credentials(self):
        """Admin login requires email/password"""
        client = TestClient(app)
        
        # Missing credentials
        response = client.post("/auth/admin-login", json={})
        assert response.status_code == 422

    def test_invalid_jwt_rejected(self):
        """Invalid JWT tokens are rejected"""
        client = TestClient(app)
        
        with patch('app.auth.jwt_verifier.decode') as mock_decode:
            mock_decode.side_effect = Exception("Invalid token")
            
            response = client.post("/auth/login", json={"token": "invalid.token"})
            assert response.status_code == 401

class TestJWTAuth:
    """Test JWT authentication logic"""
    
    def test_require_bls_reader_accepts_integration_role(self, client_with_bls_auth):
        """BLS reader accepts ROLE_INTEGRATION"""
        with patch('app.services.bls_service.BLSService.search_by_name', return_value=[]):
            response = client_with_bls_auth.get("/bls/search?q=test")
            assert response.status_code == 200

    def test_require_bls_reader_accepts_admin_role(self):
        """BLS reader accepts ROLE_SUPER_ADMIN"""
        with patch('app.auth.get_current_user') as mock_get_user:
            mock_get_user.return_value = {
                "sub": "admin@example.com", 
                "roles": ["ROLE_SUPER_ADMIN"]
            }
            
            client = TestClient(app)
            with patch('app.services.bls_service.BLSService.search_by_name', return_value=[]):
                response = client.get("/bls/search?q=test", headers={"Authorization": "Bearer token"})
                assert response.status_code == 200

    def test_require_bls_reader_rejects_invalid_role(self):
        """BLS reader rejects invalid roles"""
        with patch('app.auth.get_current_user') as mock_get_user:
            mock_get_user.return_value = {
                "sub": "user@example.com",
                "roles": ["ROLE_USER"]  # Invalid role
            }
            
            client = TestClient(app)
            response = client.get("/bls/search?q=test", headers={"Authorization": "Bearer token"})
            assert response.status_code == 403
