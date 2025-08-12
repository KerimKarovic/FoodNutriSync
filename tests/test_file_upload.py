import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from io import BytesIO
from app.schemas import BLSUploadResponse


class TestFileUpload:
    """Test file upload functionality"""
    
    def test_upload_no_file(self, client_with_mock_db):
        """Test upload endpoint without file"""
        response = client_with_mock_db.post("/admin/upload-bls")
        assert response.status_code == 422
    
    def test_upload_invalid_file_type(self, client_with_mock_db):
        """Test upload with invalid file type"""
        files = {"file": ("test.txt", BytesIO(b"content"), "text/plain")}
        response = client_with_mock_db.post("/admin/upload-bls", files=files)
        assert response.status_code == 400
        assert "File must be CSV or Excel format" in response.json()["detail"]
    
    @patch('app.main.bls_service')
    def test_upload_csv_success(self, mock_service, client_with_mock_db):
        """Test successful CSV upload"""
        # Mock service response
        mock_upload_response = BLSUploadResponse(
            added=5,
            updated=0,
            failed=0,
            errors=[]
        )
        mock_service.upload_data = AsyncMock(return_value=mock_upload_response)
        
        csv_content = "SBLS,STE,ENERC\nB123456,Test Food,100"
        files = {"file": ("test.csv", BytesIO(csv_content.encode()), "text/csv")}
        
        response = client_with_mock_db.post("/admin/upload-bls", files=files)
        assert response.status_code == 200
        data = response.json()
        assert data["added"] == 5
        assert data["failed"] == 0
    
    @patch('app.main.bls_service')
    def test_upload_with_errors(self, mock_service, client_with_mock_db):
        """Test upload with validation errors"""
        # Mock service response with errors
        mock_upload_response = BLSUploadResponse(
            added=3,
            updated=0,
            failed=2,
            errors=["Row 1: Invalid BLS number", "Row 3: Missing name"]
        )
        mock_service.upload_data = AsyncMock(return_value=mock_upload_response)
        
        csv_content = "SBLS,STE,ENERC\nINVALID,Test Food,100"
        files = {"file": ("test.csv", BytesIO(csv_content.encode()), "text/csv")}
        
        response = client_with_mock_db.post("/admin/upload-bls", files=files)
        assert response.status_code == 200
        data = response.json()
        assert data["failed"] == 2
        assert len(data["errors"]) == 2


class TestDataValidation:
    """Test data validation functionality"""
    
    def test_bls_number_validation(self, client_with_mock_db):
        """Test BLS number validation in upload"""
        csv_content = "SBLS,STE,ENERC\nINVALID123,Test Food,100"
        files = {"file": ("test.csv", BytesIO(csv_content.encode()), "text/csv")}
        
        response = client_with_mock_db.post("/admin/upload-bls", files=files)
        # Should still return 200 but with validation errors
        assert response.status_code in [200, 400]


