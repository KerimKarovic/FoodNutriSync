import pytest
from io import BytesIO
from unittest.mock import patch, AsyncMock
from app.schemas import BLSUploadResponse

class TestUpsertIdempotency:
    """Test upsert behavior with duplicate uploads"""
    
    @patch('app.main.bls_service')
    def test_same_file_twice_idempotent(self, mock_service, client_with_mock_db):
        """Test uploading same file twice"""
        # First upload - should add records
        mock_service.upload_data = AsyncMock(return_value=BLSUploadResponse(
            added=2, updated=0, failed=0, errors=[]
        ))
        
        content = "SBLS\tST\tGCAL\nB123456\tApfel\t52\nB789012\tBirne\t57"
        files = {"file": ("test.txt", BytesIO(content.encode()), "text/plain")}
        
        response1 = client_with_mock_db.post("/admin/upload-bls", files=files)
        assert response1.status_code == 200
        assert response1.json()["added"] == 2
        
        # Second upload - should update existing records
        mock_service.upload_data = AsyncMock(return_value=BLSUploadResponse(
            added=0, updated=2, failed=0, errors=[]
        ))
        
        files = {"file": ("test.txt", BytesIO(content.encode()), "text/plain")}
        response2 = client_with_mock_db.post("/admin/upload-bls", files=files)
        
        assert response2.status_code == 200
        assert response2.json()["added"] == 0
        assert response2.json()["updated"] == 2
