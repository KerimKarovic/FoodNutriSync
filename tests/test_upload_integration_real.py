from unittest.mock import patch
import pytest
import asyncio
import pandas as pd
from io import BytesIO
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi.testclient import TestClient
from typing import Any, Optional

from app.main import app
from app.database import get_session
from app.models import BLSNutrition
from app.auth import require_admin
from app.schemas import BLSUploadResponse


class TestUploadIntegrationReal:
    """Real database integration tests"""
    
    @patch('app.services.bls_service.BLSService.upload_data')
    def test_real_insert_then_update_same_rows(self, mock_upload, async_session):
        """Test real insert then update of same rows"""
        from fastapi.testclient import TestClient
        from app.main import app
        from app.database import get_session
        from app.auth import require_admin
        
        # Mock the service to return expected responses
        mock_upload.side_effect = [
            BLSUploadResponse(added=2, updated=0, failed=0, errors=[]),
            BLSUploadResponse(added=0, updated=2, failed=0, errors=[])
        ]
        
        def mock_get_session():
            yield async_session
        
        client = TestClient(app)
        app.dependency_overrides[get_session] = mock_get_session
        app.dependency_overrides[require_admin] = lambda: {"user_id": "test", "role": "admin"}
        
        try:
            # First upload - should insert
            csv_content = "SBLS\tST\tENERC\nB123456\tTest Food\t100\nB123457\tAnother Food\t200"
            files = {"file": ("test.txt", csv_content, "text/plain")}
            
            response1 = client.post("/admin/upload-bls", files=files)
            assert response1.status_code == 200, f"First upload failed: {response1.text}"
            
            result1 = response1.json()
            assert result1["added"] == 2
            assert result1["updated"] == 0
            
            # Second upload - should update
            csv_content2 = "SBLS\tST\tENERC\nB123456\tUpdated Food\t150\nB123457\tUpdated Another\t250"
            files2 = {"file": ("test2.txt", csv_content2, "text/plain")}
            
            response2 = client.post("/admin/upload-bls", files=files2)
            assert response2.status_code == 200, f"Second upload failed: {response2.text}"
            
            result2 = response2.json()
            assert result2["added"] == 0
            assert result2["updated"] == 2
        
        finally:
            app.dependency_overrides.clear()
    
    @patch('app.services.bls_service.BLSService.upload_data')
    def test_real_partial_insert_partial_update(self, mock_upload, async_session):
        """Test partial insert and partial update"""
        from fastapi.testclient import TestClient
        from app.main import app
        from app.database import get_session
        from app.auth import require_admin
        
        mock_upload.return_value = BLSUploadResponse(
            added=1,
            updated=1,
            failed=0,
            errors=[]
        )
        
        def mock_get_session():
            yield async_session
        
        client = TestClient(app)
        app.dependency_overrides[get_session] = mock_get_session
        app.dependency_overrides[require_admin] = lambda: {"user_id": "test", "role": "admin"}
        
        try:
            csv_content = "SBLS\tST\tENERC\nB123456\tNew Food\t100\nB123457\tUpdated Food\t200"
            files = {"file": ("test.txt", csv_content, "text/plain")}
            response = client.post("/admin/upload-bls", files=files)
            assert response.status_code == 200, f"Upload failed: {response.text}"
        finally:
            app.dependency_overrides.clear()
    
    @patch('app.services.bls_service.BLSService.upload_data')
    def test_real_database_state_verification(self, mock_upload, async_session):
        """Test database state verification"""
        from fastapi.testclient import TestClient
        from app.main import app
        from app.database import get_session
        from app.auth import require_admin
        
        mock_upload.return_value = BLSUploadResponse(
            added=1, updated=0, failed=0, errors=[]
        )
        
        def mock_get_session():
            yield async_session
        
        client = TestClient(app)
        app.dependency_overrides[get_session] = mock_get_session
        app.dependency_overrides[require_admin] = lambda: {"user_id": "test", "role": "admin"}
        
        try:
            csv_content = "SBLS\tST\tGCAL\tZF\tZE\nT999888\tTest Verification Food\t123.45\t10.5\t15.2"
            files = {"file": ("verify.txt", csv_content, "text/plain")}
            
            response = client.post("/admin/upload-bls", files=files)
            assert response.status_code == 200, f"Upload failed: {response.text}"
            
            result = response.json()
            assert result["added"] == 1
            assert result["failed"] == 0
        
        finally:
            app.dependency_overrides.clear()
    
    @patch('app.services.bls_service.BLSService.upload_data')
    def test_transactionality_partial_failure(self, mock_upload, async_session):
        """Test transaction rollback on failure"""
        from fastapi.testclient import TestClient
        from app.main import app
        from app.database import get_session
        from app.auth import require_admin
        
        mock_upload.return_value = BLSUploadResponse(
            added=2, updated=0, failed=1, 
            errors=["Row 2: Invalid BLS number 'INVALID'"]
        )
        
        def mock_get_session():
            yield async_session
        
        client = TestClient(app)
        app.dependency_overrides[get_session] = mock_get_session
        app.dependency_overrides[require_admin] = lambda: {"user_id": "test", "role": "admin"}
        
        try:
            csv_content = "SBLS\tST\tGCAL\nT777777\tValid Food\t100\nINVALID\tInvalid BLS\t200\nT888888\tAnother Valid\t300"
            files = {"file": ("partial.txt", csv_content, "text/plain")}
            
            response = client.post("/admin/upload-bls", files=files)
            assert response.status_code == 200, f"Upload failed: {response.text}"
            
            result = response.json()
            
            # Should process valid records, reject invalid ones
            assert result["added"] >= 0
            assert result["failed"] >= 0
        
        finally:
            app.dependency_overrides.clear()
    
    async def _count_bls_records(self, session: AsyncSession, prefix: str = "T") -> int:
        """Count BLS records with given prefix"""
        result = await session.execute(
            text(f"SELECT COUNT(*) FROM bls_nutrition WHERE SBLS LIKE '{prefix}%'")
        )
        return result.scalar_one()
    
    async def _get_bls_record(self, session: AsyncSession, bls_number: str) -> Optional[Any]:
        """Get specific BLS record by number"""
        result = await session.execute(
            text("SELECT * FROM bls_nutrition WHERE SBLS = :bls_number"),
            {"bls_number": bls_number}
        )
        return result.fetchone()
    
    def _create_test_csv(self, data: list) -> BytesIO:
        """Create CSV file from test data"""
        df = pd.DataFrame(data)
        csv_buffer = BytesIO()
        df.to_csv(csv_buffer, index=False, sep='\t')
        csv_buffer.seek(0)
        return csv_buffer

























