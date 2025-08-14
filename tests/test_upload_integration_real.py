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
    
    @pytest.mark.asyncio
    async def test_real_insert_then_update_same_rows(self, async_session):
        """Test real database insert then update"""
        client = TestClient(app)
        
        # Override dependencies to use real session
        async def override_get_session():
            yield async_session  # Use yield instead of return
        
        def override_auth():
            return {"user_id": "admin", "roles": ["Admin"]}
        
        app.dependency_overrides[get_session] = override_get_session
        app.dependency_overrides[require_admin] = override_auth
        
        try:
            # Initial count
            initial_count = await self._count_bls_records(async_session)
            
            # Test data - using T prefix to avoid conflicts
            test_data = [
                {"SBLS": "T123456", "ST": "Test Apple", "STE": "Test Apple EN", "GCAL": "50.5"},
                {"SBLS": "T789012", "ST": "Test Orange", "STE": "Test Orange EN", "GCAL": "60.0"},
                {"SBLS": "T555666", "ST": "Test Banana", "STE": "Test Banana EN", "GCAL": "70.2"}
            ]
            
            csv_file = self._create_test_csv(test_data)
            
            # First upload - should insert 3 new records
            response1 = client.post(
                "/admin/upload-bls",
                files={"file": ("test.txt", csv_file, "text/plain")}
            )
            
            assert response1.status_code == 200
            result1 = response1.json()
            
            # Verify first upload response
            assert result1["added"] == 3
            assert result1["updated"] == 0
            assert result1["failed"] == 0
            
            # Verify database state after first upload
            count_after_insert = await self._count_bls_records(async_session)
            assert count_after_insert == initial_count + 3
            
            # Verify specific records exist
            apple_record = await self._get_bls_record(async_session, "T123456")
            assert apple_record is not None
            assert apple_record.ST == "Test Apple"
            
            # Second upload - same data with slight modifications
            test_data_updated = [
                {"SBLS": "T123456", "ST": "Test Apple Updated", "STE": "Test Apple EN", "GCAL": "55.5"},
                {"SBLS": "T789012", "ST": "Test Orange Updated", "STE": "Test Orange EN", "GCAL": "65.0"},
                {"SBLS": "T555666", "ST": "Test Banana Updated", "STE": "Test Banana EN", "GCAL": "75.2"}
            ]
            
            csv_file2 = self._create_test_csv(test_data_updated)
            
            # Second upload - should update 3 existing records
            response2 = client.post(
                "/admin/upload-bls",
                files={"file": ("test2.txt", csv_file2, "text/plain")}
            )
            
            assert response2.status_code == 200
            result2 = response2.json()
            
            # Verify second upload response
            assert result2["added"] == 0
            assert result2["updated"] == 3
            assert result2["failed"] == 0
            
            # Verify database state after update
            count_after_update = await self._count_bls_records(async_session)
            assert count_after_update == initial_count + 3  # Still same count
            
            # Verify records were updated, not duplicated
            apple_updated = await self._get_bls_record(async_session, "T123456")
            if apple_updated is None:
                pytest.fail("Apple record should exist after update")
            
            # Now Pylance knows apple_updated is not None
            assert apple_updated.ST == "Test Apple Updated"  # ST = German name
            assert float(apple_updated.GCAL) == 55.5  # GCAL = Energy in kcal
            
        finally:
            app.dependency_overrides.clear()
    
    @pytest.mark.asyncio
    @patch('app.services.bls_service.BLSService.upload_data')
    def test_real_partial_insert_partial_update(self, mock_upload, client_with_mock_db):
        """Test partial insert and partial update"""
        mock_upload.return_value = BLSUploadResponse(
            added=1,
            updated=1,
            failed=0,
            errors=[]
        )
        
        csv_content = "SBLS,ST,ENERC\nB123456,New Food,100\nB123457,Updated Food,200"
        files = {"file": ("test.csv", csv_content, "text/csv")}
        response = client_with_mock_db.post("/admin/upload-bls", files=files)
        assert response.status_code == 200
    
    @pytest.mark.asyncio
    async def test_real_database_state_verification(self, async_session):
        """Test database state verification"""
        client = TestClient(app)
        app.dependency_overrides[get_session] = lambda: async_session
        
        try:
            initial_count = await self._count_bls_records(async_session)
            
            # Upload with known nutrient values
            test_data = [
                {
                    "SBLS": "T999888", 
                    "ST": "Test Verification Food", 
                    "GCAL": "123.45",
                    "ZF": "10.5",
                    "ZE": "15.2"
                }
            ]
            
            csv_file = self._create_test_csv(test_data)
            response = client.post(
                "/admin/upload-bls",
                files={"file": ("verify.txt", csv_file, "text/plain")}
            )
            
            assert response.status_code == 200
            result = response.json()
            
            # Verify response counts
            assert result["added"] == 1
            assert result["updated"] == 0
            assert result["failed"] == 0
            
            # Verify exact database state
            final_count = await self._count_bls_records(async_session)
            assert final_count == initial_count + 1
            
            # Verify specific record and values
            record = await self._get_bls_record(async_session, "T999888")
            if record is None:
                pytest.fail("Verification record should exist")
            
            # Now Pylance knows record is not None
            assert record.ST == "Test Verification Food"  # ST = German name
            assert float(record.GCAL) == 123.45  # GCAL = Energy in kcal
            assert float(record.ZF) == 10.5  # ZF = Fat
            assert float(record.ZE) == 15.2  # ZE = Protein
            
        finally:
            app.dependency_overrides.clear()
    
    @pytest.mark.asyncio
    async def test_transactionality_partial_failure(self, async_session):
        """Test transaction rollback on failure"""
        client = TestClient(app)
        app.dependency_overrides[get_session] = lambda: async_session
        
        try:
            initial_count = await self._count_bls_records(async_session)
            
            # Mix of valid and invalid data
            test_data = [
                {"SBLS": "T777777", "ST": "Valid Food", "GCAL": "100"},      # Valid
                {"SBLS": "INVALID", "ST": "Invalid BLS", "GCAL": "200"},    # Invalid BLS format
                {"SBLS": "T888888", "ST": "Another Valid", "GCAL": "300"}   # Valid
            ]
            
            csv_file = self._create_test_csv(test_data)
            response = client.post(
                "/admin/upload-bls",
                files={"file": ("partial.txt", csv_file, "text/plain")}
            )
            
            assert response.status_code == 200
            result = response.json()
            
            # Should process valid records, reject invalid ones
            assert result["added"] == 2  # T777777, T888888
            assert result["failed"] == 1  # INVALID
            assert len(result["errors"]) > 0
            
            # Verify only valid records were saved
            final_count = await self._count_bls_records(async_session)
            assert final_count == initial_count + 2
            
            # Verify specific records
            valid1 = await self._get_bls_record(async_session, "T777777")
            valid2 = await self._get_bls_record(async_session, "T888888")
            invalid = await self._get_bls_record(async_session, "INVALID")
            
            assert valid1 is not None
            assert valid2 is not None
            assert invalid is None
            
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





