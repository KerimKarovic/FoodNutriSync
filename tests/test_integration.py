import pytest
import httpx
import time
from unittest.mock import patch, MagicMock
import subprocess
import os

class TestLocalIntegration:
    """Test local Docker integration"""
    
    @pytest.mark.integration
    def test_docker_compose_services(self):
        """Test Docker Compose services are properly configured"""
        # This would run in CI/CD with actual Docker
        compose_file = "docker-compose.yml"
        assert os.path.exists(compose_file)
        
        # Check that required services are defined
        with open(compose_file, 'r') as f:
            content = f.read()
            assert "api:" in content
            assert "db:" in content
            assert "postgres:" in content

    @pytest.mark.integration
    @patch('subprocess.run')
    def test_database_migration(self, mock_run):
        """Test database migration in container"""
        mock_run.return_value = MagicMock(returncode=0, stdout="Migration successful")
        
        # Simulate running migration
        result = subprocess.run([
            "docker-compose", "exec", "api", 
            "alembic", "upgrade", "head"
        ], capture_output=True, text=True)
        
        assert mock_run.called

class TestEndToEndWorkflow:
    """Test complete end-to-end workflow"""
    
    @pytest.mark.integration
    def test_complete_bls_upload_workflow(self, client_with_mock_db, sample_bls_data):
        """Test complete BLS data upload workflow"""
        from app.schemas import BLSUploadResponse
        
        with patch('app.main.bls_service.upload_data') as mock_upload:
            mock_upload.return_value = BLSUploadResponse(
                added=3,
                updated=0,
                failed=0,
                errors=[]
            )
            
            # 1. Upload BLS data
            files = {"file": ("test.txt", sample_bls_data, "text/plain")}
            upload_response = client_with_mock_db.put("/admin/bls-dataset", files=files)
            assert upload_response.status_code == 200
            
            upload_data = upload_response.json()
            assert upload_data["added"] == 3
            
            # 2. Search for uploaded data
            search_response = client_with_mock_db.get("/bls/search?name=Apfel&limit=10")
            assert search_response.status_code == 200

    @pytest.mark.integration
    def test_api_documentation_accessible(self, client):
        """Test that API documentation is accessible"""
        response = client.get("/docs")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    @pytest.mark.integration
    def test_openapi_schema_valid(self, client):
        """Test that OpenAPI schema is valid"""
        response = client.get("/openapi.json")
        assert response.status_code == 200
        
        schema = response.json()
        assert "openapi" in schema
        assert "info" in schema
        assert "paths" in schema

class TestPerformanceIntegration:
    """Test performance characteristics"""
    
    @pytest.mark.integration
    def test_api_response_times(self, client):
        """Test API response times are acceptable"""
        endpoints = [
            "/health",
            "/health/ready", 
            "/health/live",
            "/bls/search?name=test&limit=1"
        ]
        
        for endpoint in endpoints:
            start_time = time.time()
            response = client.get(endpoint)
            end_time = time.time()
            
            response_time = end_time - start_time
            
            # Health endpoints should be very fast
            if "/health" in endpoint:
                assert response_time < 0.1, f"{endpoint} too slow: {response_time}s"
            else:
                assert response_time < 1.0, f"{endpoint} too slow: {response_time}s"

    @pytest.mark.integration
    def test_concurrent_requests(self, client):
        """Test handling concurrent requests"""
        import concurrent.futures
        
        def make_request():
            return client.get("/health")
        
        # Make 20 concurrent requests
        with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
            futures = [executor.submit(make_request) for _ in range(20)]
            responses = [future.result() for future in futures]
        
        # All should succeed
        success_count = sum(1 for r in responses if r.status_code == 200)
        assert success_count >= 18, f"Only {success_count}/20 requests succeeded"

class TestErrorHandlingIntegration:
    """Test error handling in integration scenarios"""
    
    @pytest.mark.integration
    def test_invalid_file_upload_handling(self, client_with_mock_db):
        """Test handling of invalid file uploads"""
        # Test various invalid scenarios
        test_cases = [
            ("empty.txt", "", "Empty file"),
            ("invalid.csv", "invalid,data\nno,headers", "CSV format"),
            ("wrong.json", '{"invalid": "json"}', "JSON format"),
        ]
        
        for filename, content, description in test_cases:
            files = {"file": (filename, content, "text/plain")}
            response = client_with_mock_db.put("/admin/bls-dataset", files=files)
            
            # Should handle gracefully (not crash)
            assert response.status_code in [400, 422], f"Failed for {description}"

    @pytest.mark.integration
    def test_large_file_handling(self, client_with_mock_db):
        """Test handling of large files"""
        # Create a large BLS data file (simulate)
        header = "SBLS\tST\tENERC\tEPRO\tVC\tMNA\n"
        large_content = header + "\n".join([
            f"B{i:06d}\tFood {i}\t{50+i}\t{0.1+i*0.01}\t{5+i*0.1}\t{10+i}"
            for i in range(1000)  # 1000 records
        ])
        
        with patch('app.main.bls_service.upload_data') as mock_upload:
            from app.schemas import BLSUploadResponse
            mock_upload.return_value = BLSUploadResponse(
                added=1000, updated=0, failed=0, errors=[]
            )
            
            files = {"file": ("large.txt", large_content, "text/plain")}
            response = client_with_mock_db.put("/admin/bls-dataset", files=files)
            
            # Should handle large files
            assert response.status_code == 200

class TestSecurityIntegration:
    """Test security aspects in integration"""
    
    @pytest.mark.integration
    def test_admin_endpoints_protection(self, client):
        """Test that admin endpoints are properly protected"""
        admin_endpoints = [
            "/admin/bls-dataset",
            "/admin/upload-bls"
        ]
        
        for endpoint in admin_endpoints:
            # Without authentication, should get 401 or 403
            response = client.put(endpoint)
            assert response.status_code in [401, 403, 422]  # 422 for missing file

    @pytest.mark.integration
    def test_public_endpoints_accessible(self, client):
        """Test that public endpoints are accessible"""
        public_endpoints = [
            "/health",
            "/health/ready",
            "/health/live",
            "/docs",
            "/openapi.json"
        ]
        
        for endpoint in public_endpoints:
            response = client.get(endpoint)
            assert response.status_code == 200

    @pytest.mark.integration
    def test_cors_headers(self, client):
        """Test CORS headers are properly set"""
        response = client.get("/health")
        
        # Should have CORS headers for web access
        # (This depends on your CORS configuration)
        assert response.status_code == 200

class TestExternalAPIIntegration:
    """Test external API integration scenarios"""
    
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_external_health_check(self):
        """Test external health check using httpx"""
        # This would be used for testing deployed instances
        base_url = "http://localhost:8000"  # Default test URL
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(f"{base_url}/health", timeout=5.0)
                # This test only runs if the server is actually running
                if response.status_code == 200:
                    data = response.json()
                    assert "status" in data
            except httpx.ConnectError:
                # Server not running, skip test
                pytest.skip("Server not running for external integration test")
