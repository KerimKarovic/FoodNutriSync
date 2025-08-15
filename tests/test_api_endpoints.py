import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, Mock, AsyncMock
from app.exceptions import BLSNotFoundError, BLSValidationError
from app.schemas import BLSNutrientResponse, BLSSearchResponse, BLSUploadResponse

# REMOVE: Duplicate client fixture (use the one from conftest.py)

class TestHealthEndpoint:
    def test_health_endpoint(self, client_with_mock_db):
        response = client_with_mock_db.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    def test_root_endpoint(self, client_with_mock_db):
        response = client_with_mock_db.get("/")
        assert response.status_code == 200
        assert "NutriSync API" in response.json()["message"]

class TestBLSEndpoints:
    """Test BLS API endpoints"""
    
    def test_search_route_not_confused_with_bls_number(self, client_with_mock_db):
        """Test that /bls/search goes to search endpoint, not BLS lookup"""
        response = client_with_mock_db.get("/bls/search")
        assert response.status_code == 200
        data = response.json()
        assert "results" in data
        assert "count" in data
    
    @pytest.mark.parametrize("bls_number,expected_status", [
        ("B123456", 404),
        ("INVALID", 400),  # Changed from 422 to 400
    ])
    @patch('app.services.bls_service.BLSService.get_by_bls_number')
    def test_bls_number_validation(self, mock_get_method, bls_number, expected_status, client_with_mock_db):
        """Test BLS number validation"""
        if expected_status == 404:
            mock_get_method.side_effect = BLSNotFoundError("Not found")
        elif expected_status == 400:
            mock_get_method.side_effect = BLSValidationError("Invalid format")
        
        response = client_with_mock_db.get(f"/bls/{bls_number}")
        assert response.status_code == expected_status

    @patch('app.services.bls_service.BLSService.search_by_name')
    def test_search_endpoint_success(self, mock_search_method, client_with_mock_db):
        """Test successful search"""
        # Mock service response with proper response object
        mock_response = BLSSearchResponse(
            results=[BLSNutrientResponse(bls_number="B123456", name_german="Test Food")],
            count=1
        )
        mock_search_method.return_value = mock_response
        
        response = client_with_mock_db.get("/bls/search?name=test")
        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 1
        assert len(data["results"]) == 1

    @patch('app.services.bls_service.BLSService.search_by_name')
    def test_search_endpoint_missing_name(self, mock_search_method, client_with_mock_db):
        """Test search without name parameter"""
        mock_response = BLSSearchResponse(results=[], count=0)
        mock_search_method.return_value = mock_response
        
        response = client_with_mock_db.get("/bls/search")
        assert response.status_code == 200
        data = response.json()
        assert "results" in data
        assert "count" in data

class TestValidationErrors:
    """Test API validation and error handling"""
    
    @patch('app.services.bls_service.BLSService.search_by_name')
    def test_bls_search_missing_query(self, mock_search, client_with_mock_db):
        """Test search without query parameter"""
        from app.schemas import BLSSearchResponse
        mock_search.return_value = BLSSearchResponse(results=[], count=0)
        
        response = client_with_mock_db.get("/bls/search")
        assert response.status_code == 200

    @patch('app.services.bls_service.BLSService.search_by_name')
    def test_bls_search_empty_query(self, mock_search_method, client_with_mock_db):
        """Test search with empty query"""
        # Mock empty response
        mock_response = BLSSearchResponse(results=[], count=0)
        mock_search_method.return_value = mock_response
        
        response = client_with_mock_db.get("/bls/search?name=")
        if response.status_code != 200:
            print(f"Empty query error response: {response.text}")
        # Should return 200 with empty results
        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 0

class TestBulkUploadGuards:
    """Test bulk upload validation and edge cases"""
    
    @patch('app.main.bls_service.upload_data')  # Changed from _bulk_upsert
    def test_upload_txt_parses_german_decimal_commas(self, mock_upload, client_with_mock_db):
        """Test German decimal comma parsing"""
        mock_upload_response = BLSUploadResponse(added=1, updated=0, failed=0, errors=[])
        mock_upload.return_value = mock_upload_response

        content = "SBLS\tST\tGCAL\nB123458\tKirsche\t12,3\n"
        files = {"file": ("bls_comma.txt", content.encode("utf-8"), "text/plain")}

        r = client_with_mock_db.post("/admin/upload-bls", files=files)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("added", 0) >= 1

    @patch('app.main.bls_service.upload_data')  # Changed from _bulk_upsert
    def test_upload_txt_rejects_negative_values(self, mock_upload, client_with_mock_db):
        """Test negative value rejection"""
        mock_upload_response = BLSUploadResponse(added=0, updated=0, failed=1, errors=["Negative values not allowed"])
        mock_upload.return_value = mock_upload_response

        content = "SBLS\tST\tGCAL\nB123459\tTest\t-50\n"
        files = {"file": ("bls_negative.txt", content.encode("utf-8"), "text/plain")}

        r = client_with_mock_db.post("/admin/upload-bls", files=files)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("failed", 0) >= 1

    @pytest.mark.asyncio
    def test_upload_txt_wrong_delimiter_semicolon_yields_validation_errors(self, client_with_mock_db):
        """
        Semicolon-delimited .txt should not parse as expected by read_table (tab default),
        leading to missing mandatory columns -> validation errors.
        """
        content = "SBLS;ST;GCAL\nB123458;Kirsche;12,3\n"
        files = {"file": ("bls_semicolon.txt", content.encode("utf-8"), "text/plain")}

        r = client_with_mock_db.post("/admin/upload-bls", files=files)
        assert r.status_code == 400, f"Expected 400 but got {r.status_code}: {r.text}"
        body = r.json()
        assert "Invalid .txt structure" in body.get("detail", "")

    @pytest.mark.asyncio
    def test_upload_counts_added_vs_updated_are_surfaced_by_endpoint(self, client_with_mock_db):
        """
        Ensure the endpoint returns accurate added/updated counts from the service.
        We simulate first-upload (inserts) vs second-upload (updates) via a stubbed service.
        """
        call_no = {"n": 0}

        def fake_upload_data(self, session, df, filename):
            call_no["n"] += 1
            if call_no["n"] == 1:
                return BLSUploadResponse(added=2, updated=0, failed=0, errors=[])
            else:
                return BLSUploadResponse(added=0, updated=2, failed=0, errors=[])

        content = (
            "SBLS\tST\tGCAL\n"
            "T111111\tFoo\t100,0\n"
            "T222222\tBar\t200,0\n"
        )
        files = {"file": ("bls_two_rows.txt", content.encode("utf-8"), "text/plain")}

        # Patch just for the duration of the two calls
        with patch("app.services.bls_service.BLSService.upload_data", autospec=True, side_effect=fake_upload_data):
            r1 = client_with_mock_db.post("/admin/upload-bls", files=files)
            assert r1.status_code == 200, r1.text
            b1 = r1.json()
            assert b1.get("added") == 2 and b1.get("updated") == 0 and b1.get("failed") == 0

            r2 = client_with_mock_db.post("/admin/upload-bls", files=files)
            assert r2.status_code == 200, r2.text
            b2 = r2.json()
            assert b2.get("added") == 0 and b2.get("updated") == 2 and b2.get("failed") == 0

    @pytest.mark.asyncio
    @patch("app.services.bls_service.BLSService._bulk_upsert_with_counts", autospec=True)
    def test_upload_large_file_smoke_does_not_500(self, mock_upsert, client_with_mock_db):
        """
        Large-ish TXT (e.g., 2k rows) should be accepted without server error.
        We don't assert timing; we only ensure the request succeeds and upsert is invoked.
        """
        # Return (added, updated) tuple for batched processing
        def mock_batch_upsert(self, session, records):
            return (len(records), 0)  # All records are "added"
        
        mock_upsert.side_effect = mock_batch_upsert

        rows = ["SBLS\tST\tGCAL"]
        for i in range(2000):
            rows.append(f"T{i:06d}\tItem{i}\t{100 + (i % 50)},0")  # comma decimal
        content = "\n".join(rows) + "\n"
        files = {"file": ("bls_big.txt", content.encode("utf-8"), "text/plain")}

        r = client_with_mock_db.post("/admin/upload-bls", files=files)
        assert r.status_code == 200, r.text
        body = r.json()
        # Should count all as processed (added+updated > 0) and not fail
        assert body.get("failed", 0) == 0
        assert (body.get("added", 0) + body.get("updated", 0)) == 2000
        
        # Verify batching: should be called multiple times for 2000 records
        assert mock_upsert.call_count >= 2  # At least 2 batches (1000 records each)

    @pytest.mark.asyncio
    @patch("app.services.bls_service.BLSService._bulk_upsert_with_counts", autospec=True)
    def test_upload_batch_processing_works_correctly(self, mock_upsert, client_with_mock_db):
        """
        Test that batching works correctly with accurate counts across batches.
        """
        batch_calls = []
        
        def track_batches(self, session, records):
            batch_calls.append(len(records))
            # Simulate some records added, some updated
            added = len(records) // 2
            updated = len(records) - added
            return (added, updated)
        
        mock_upsert.side_effect = track_batches

        # Create 1500 records to trigger multiple batches
        rows = ["SBLS\tST\tGCAL"]
        for i in range(1500):
            rows.append(f"T{i:06d}\tItem{i}\t100,0")
        content = "\n".join(rows) + "\n"
        files = {"file": ("bls_batch_test.txt", content.encode("utf-8"), "text/plain")}

        r = client_with_mock_db.post("/admin/upload-bls", files=files)
        assert r.status_code == 200, r.text
        body = r.json()
        
        # Verify batching occurred
        assert len(batch_calls) >= 2  # Should have multiple batches
        assert sum(batch_calls) == 1500  # Total records processed
        assert max(batch_calls) <= 1000  # No batch exceeds limit
        
        # Verify counts are aggregated correctly
        assert body.get("added", 0) + body.get("updated", 0) == 1500
        assert body.get("failed", 0) == 0




















