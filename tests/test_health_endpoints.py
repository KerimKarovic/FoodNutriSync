import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, AsyncMock
import json

class TestHealthEndpoints:
    """Test health check endpoints for deployment monitoring"""
    
    @patch('app.main.get_session')
    def test_basic_health_endpoint(self, mock_get_session, client):
        """Test basic health endpoint"""
        # Mock database session
        mock_session = AsyncMock()
        mock_result = AsyncMock()
        mock_result.scalar.return_value = 100
        mock_session.execute.return_value = mock_result
        mock_get_session.return_value = mock_session
        
        response = client.get("/health")
        assert response.status_code == 200
        
        data = response.json()
        assert data["status"] == "ok"
        assert "timestamp" in data

    def test_health_endpoint_structure(self, client):
        """Test health endpoint response structure"""
        response = client.get("/health")
        data = response.json()
        
        required_fields = ["status", "timestamp"]
        for field in required_fields:
            assert field in data

    @patch('app.main.get_session')
    def test_readiness_probe_with_db(self, mock_get_session, client):
        """Test readiness probe with database connection"""
        # Mock successful database connection
        mock_session = AsyncMock()
        mock_result = AsyncMock()
        mock_result.scalar.return_value = None
        mock_session.execute.return_value = mock_result
        mock_get_session.return_value = mock_session
        
        response = client.get("/health/ready")
        assert response.status_code == 200

    @patch('app.main.get_session')
    def test_readiness_probe_db_failure(self, mock_get_session, client):
        """Test readiness probe with database failure"""
        # Mock database connection failure
        mock_get_session.side_effect = Exception("Database connection failed")
        
        response = client.get("/health/ready")
        assert response.status_code == 503

    def test_liveness_probe(self, client):
        """Test liveness probe endpoint"""
        response = client.get("/health/live")
        assert response.status_code == 200
        
        data = response.json()
        assert data["status"] == "alive"

    def test_health_endpoints_json_format(self, client):
        """Test that all health endpoints return valid JSON"""
        endpoints = ["/health", "/health/ready", "/health/live"]
        
        for endpoint in endpoints:
            response = client.get(endpoint)
            assert response.headers["content-type"] == "application/json"
            
            # Verify it's valid JSON
            data = response.json()
            assert isinstance(data, dict)
            assert "status" in data

class TestHealthMonitoring:
    """Test health monitoring functionality for Azure Container Apps"""
    
    def test_health_check_performance(self, client):
        """Test health check response time"""
        import time
        
        start_time = time.time()
        response = client.get("/health")
        end_time = time.time()
        
        assert response.status_code == 200
        # Health check should be fast (under 1 second)
        assert (end_time - start_time) < 1.0

    def test_concurrent_health_checks(self, client):
        """Test multiple concurrent health checks"""
        import concurrent.futures
        import threading
        
        def make_health_request():
            return client.get("/health")
        
        # Make 10 concurrent requests
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(make_health_request) for _ in range(10)]
            responses = [future.result() for future in futures]
        
        # All should succeed
        for response in responses:
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "ok"

    def test_health_check_under_load(self, client):
        """Test health checks under simulated load"""
        # Simulate some load by making multiple API calls
        for _ in range(5):
            client.get("/bls/search?name=test&limit=1")
        
        # Health check should still work
        response = client.get("/health")
        assert response.status_code == 200
        
        data = response.json()
        assert data["status"] == "ok"

class TestAzureProbeCompatibility:
    """Test compatibility with Azure Container Apps health probes"""
    
    def test_liveness_probe_azure_format(self, client):
        """Test liveness probe matches Azure Container Apps expectations"""
        response = client.get("/health/live")
        
        # Azure expects 200 status for healthy
        assert response.status_code == 200
        
        # Should return JSON
        assert response.headers["content-type"] == "application/json"
        
        data = response.json()
        assert isinstance(data, dict)

    def test_readiness_probe_azure_format(self, client):
        """Test readiness probe matches Azure Container Apps expectations"""
        response = client.get("/health/ready")
        
        # Azure expects 200 status for ready
        assert response.status_code == 200
        
        # Should return JSON
        assert response.headers["content-type"] == "application/json"
        
        data = response.json()
        assert isinstance(data, dict)

    def test_probe_endpoints_no_auth(self, client):
        """Test that health probes don't require authentication"""
        # Health endpoints should work without JWT token
        endpoints = ["/health", "/health/ready", "/health/live"]
        
        for endpoint in endpoints:
            response = client.get(endpoint)
            # Should not return 401 Unauthorized
            assert response.status_code != 401
            assert response.status_code == 200

    def test_probe_response_size(self, client):
        """Test that probe responses are small (for efficiency)"""
        endpoints = ["/health", "/health/ready", "/health/live"]
        
        for endpoint in endpoints:
            response = client.get(endpoint)
            
            # Response should be small (under 1KB)
            content_length = len(response.content)
            assert content_length < 1024, f"{endpoint} response too large: {content_length} bytes"


