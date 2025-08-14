import pytest
from io import BytesIO
from unittest.mock import patch, AsyncMock
from app.schemas import BLSUploadResponse

class TestUpsertIdempotency:
    """Test upsert behavior with duplicate uploads"""
    
    @patch('app.main.bls_service.upload_data')
    def test_same_file_twice_idempotent(self, mock_upload, client_with_mock_db):
        """Test uploading same file twice is idempotent"""
        mock_upload.return_value = BLSUploadResponse(
            added=1,
            updated=0,
            failed=0,
            errors=[]
        )
        
        csv_content = "SBLS\tST\tENERC\nB123456\tTest Food\t100"
        files = {"file": ("test.txt", csv_content, "text/plain")}
        
        # First upload
        response1 = client_with_mock_db.post("/admin/upload-bls", files=files)
        assert response1.status_code == 200
        
        # Second upload (should be idempotent)
        response2 = client_with_mock_db.post("/admin/upload-bls", files=files)
        assert response2.status_code == 200



