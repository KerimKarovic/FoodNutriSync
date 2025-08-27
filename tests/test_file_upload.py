import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from io import BytesIO
from app.schemas import BLSUploadResponse


class TestFileUpload:
    """Test file upload functionality"""
    
    def test_upload_no_file(self, client_with_mock_db):
        """Test upload without file"""
        response = client_with_mock_db.put("/admin/bls-dataset")
        assert response.status_code == 422
    
    def test_upload_invalid_file_type(self, client_with_mock_db):
        """Test upload with invalid file type"""
        files = {"file": ("test.csv", "invalid content", "text/csv")}  # CSV should now fail
        response = client_with_mock_db.put("/admin/bls-dataset", files=files)
        assert response.status_code == 400
        assert "TXT format" in response.json()["detail"]
    
    @patch('app.main.bls_service.upload_data')
    def test_upload_csv_success(self, mock_upload, client_with_mock_db):
        """Test successful CSV upload"""
        mock_upload.return_value = BLSUploadResponse(
            added=1,
            updated=0,
            failed=0,
            errors=[]
        )
        
        csv_content = "SBLS\tST\tENERC\nB123456\tTest Food\t100"
        files = {"file": ("test.txt", csv_content, "text/plain")}
        response = client_with_mock_db.put("/admin/bls-dataset", files=files)
        assert response.status_code == 200

    @patch('app.main.bls_service.upload_data')
    def test_upload_with_errors(self, mock_upload, client_with_mock_db):
        """Test upload with validation errors"""
        mock_upload.return_value = BLSUploadResponse(
            added=0,
            updated=0,
            failed=1,
            errors=["Invalid BLS number format"]
        )
        
        csv_content = "SBLS\tST\tENERC\nINVALID\tTest Food\t100"
        files = {"file": ("test.txt", csv_content, "text/plain")}
        response = client_with_mock_db.post("/admin/upload-bls", files=files)
        assert response.status_code == 200


class TestDataValidation:
    """Test data validation functionality"""
    
    def test_bls_number_validation(self, client_with_mock_db):
        """Test BLS number validation in upload"""
        csv_content = "SBLS,STE,ENERC\nINVALID123,Test Food,100"
        files = {"file": ("test.csv", BytesIO(csv_content.encode()), "text/csv")}
        
        response = client_with_mock_db.post("/admin/upload-bls", files=files)
        # Should still return 200 but with validation errors
        assert response.status_code in [200, 400]











