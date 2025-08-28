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
        assert data["status"] == "ok"
        
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
        response = client_with_mock_db.post("/admin/upload-bls", files=files)
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


class TestIngestion:
    """File upload and data validation tests"""
    
    @pytest.mark.ingest
    def test_upload_success(self, client_with_mock_db_and_auth):
        """Successful file upload"""
        from app.schemas import BLSUploadResponse
        
        with patch('app.main.bls_service.upload_data') as mock_upload:
            mock_upload.return_value = BLSUploadResponse(
                added=1, updated=0, failed=0, errors=[]
            )
            
            csv_content = "SBLS\tST\tENERC\nB123456\tTest Food\t100"
            files = {"file": ("test.txt", csv_content, "text/plain")}
            
            response = client_with_mock_db_and_auth.post("/admin/upload-bls", files=files)
            assert response.status_code == 200

    @pytest.mark.ingest
    def test_upload_validation_errors(self, client_with_mock_db_and_auth):
        """Upload validation for empty/invalid files"""
        # Empty file
        files = {"file": ("empty.txt", "", "text/plain")}
        response = client_with_mock_db_and_auth.post("/admin/upload-bls", files=files)
        assert response.status_code == 422
        
        # Wrong file type
        files = {"file": ("test.jpg", "not csv", "image/jpeg")}
        response = client_with_mock_db_and_auth.post("/admin/upload-bls", files=files)
        assert response.status_code == 400

    @pytest.mark.ingest
    @pytest.mark.parametrize("delimiter,content", [
        ("\t", "SBLS\tST\tENERC\nB123456\tApfel\t52"),
        (";", "SBLS;ST;ENERC\nB123456;Apfel;52"),
        (",", "SBLS,ST,ENERC\nB123456,Apfel,52")
    ])
    def test_delimiter_support(self, delimiter, content):
        """Support for different delimiters"""
        from app.services.bls_service import BLSDataValidator
        import pandas as pd
        from io import BytesIO
        
        df = pd.read_csv(BytesIO(content.encode()), sep=delimiter)
        validator = BLSDataValidator()
        valid_records, errors = validator.validate_dataframe(df, "test.txt")
        
        assert len(valid_records) == 1
        assert len(errors) == 0

    @pytest.mark.ingest
    def test_idempotency(self, client_with_mock_db_and_auth):
        """Uploading same file twice is idempotent"""
        from app.schemas import BLSUploadResponse
        
        with patch('app.main.bls_service.upload_data') as mock_upload:
            mock_upload.return_value = BLSUploadResponse(
                added=1, updated=0, failed=0, errors=[]
            )
            
            csv_content = "SBLS\tST\tENERC\nB123456\tTest Food\t100"
            files = {"file": ("test.txt", csv_content, "text/plain")}
            
            # First upload
            response1 = client_with_mock_db_and_auth.post("/admin/upload-bls", files=files)
            assert response1.status_code == 200
            
            # Second upload should work the same
            response2 = client_with_mock_db_and_auth.post("/admin/upload-bls", files=files)
            assert response2.status_code == 200


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
        response = client_with_mock_db.post("/admin/upload-bls", files=files)
        assert response.status_code == 401


class TestIntegration:
    """End-to-end integration tests"""
    
    @pytest.mark.integration
    def test_upload_then_search_workflow(self, client_with_mock_db_and_auth):
        """Complete workflow: upload data then search for it"""
        from app.schemas import BLSUploadResponse, BLSSearchResponse, BLSNutrientResponse
        
        # Mock upload
        with patch('app.main.bls_service.upload_data') as mock_upload, \
            patch('app.main.bls_service.search_by_name') as mock_search:
            
            mock_upload.return_value = BLSUploadResponse(
                added=1, updated=0, failed=0, errors=[]
            )
            mock_search.return_value = BLSSearchResponse(
                results=[BLSNutrientResponse(
                    bls_number="B123456", 
                    name_german="Test Food", 
                    nutrients={"ENERC": 100}
                )],
                count=1
            )
            
            # Upload
            csv_content = "SBLS\tST\tENERC\nB123456\tTest Food\t100"
            files = {"file": ("test.txt", csv_content, "text/plain")}
            upload_response = client_with_mock_db_and_auth.post("/admin/upload-bls", files=files)
            assert upload_response.status_code == 200
            
            # Search
            search_response = client_with_mock_db_and_auth.get("/bls/search?name=Test")
            assert search_response.status_code == 200
            results = search_response.json()
            assert len(results) == 1
            assert results[0]["sbls"] == "B123456"

