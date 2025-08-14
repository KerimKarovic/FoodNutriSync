import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, Mock, AsyncMock
from app.exceptions import BLSNotFoundError, BLSValidationError
from app.schemas import BLSNutrientResponse, BLSSearchResponse, BLSUploadResponse

@pytest.fixture
def client():
    """Create test client"""
    from app.main import app
    return TestClient(app)

class TestHealthEndpoints:
    """Test basic health and info endpoints"""
    
    def test_root_endpoint(self, client):
        """Test root endpoint returns basic info"""
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert "message" in data or "version" in data

class TestBLSEndpoints:
    """Test BLS API endpoints"""
    
    @pytest.mark.parametrize("bls_number,expected_status", [
        ("B123456", 404),  # No data in test DB
        ("INVALID", 422),  # Invalid format should return 422
        # Remove "search" test case since it matches the search route
    ])
    def test_bls_number_validation(self, bls_number, expected_status, client):
        """Test BLS number validation"""
        response = client.get(f"/bls/{bls_number}")
        assert response.status_code == expected_status

    def test_search_route_not_confused_with_bls_number(self, client):
        """Test that /bls/search goes to search endpoint, not BLS lookup"""
        response = client.get("/bls/search")
        assert response.status_code == 200
        data = response.json()
        assert "results" in data
        assert "count" in data

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
        if response.status_code != 200:
            print(f"Search error response: {response.text}")
        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 1
        assert len(data["results"]) == 1

    def test_search_endpoint_missing_name(self, client_with_mock_db):
        """Test search endpoint without name parameter"""
        response = client_with_mock_db.get("/bls/search")
        assert response.status_code == 200  # Should work with default empty name

class TestValidationErrors:
    """Test API validation and error handling"""
    
    def test_bls_search_missing_query(self, client):
        """Test search without query parameter"""
        response = client.get("/bls/search")
        assert response.status_code == 200  # Should work with default empty name
        
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
    """Hardening tests for TXT bulk import edge cases"""

    @pytest.mark.asyncio
    @patch("app.services.bls_service.BLSService._bulk_upsert", autospec=True)
    def test_upload_txt_parses_german_decimal_commas(self, mock_upsert, client_with_mock_db):
        """
        Ensure '50,5' (German decimal) is normalized to 50.5 before DB upsert.
        We capture the records passed into _bulk_upsert and assert parsed floats.
        """
        captured = {}
        def _capture(self, session, records):
            assert len(records) == 1
            captured.update(records[0])
            return len(records)
        mock_upsert.side_effect = _capture

        content = "SBLS\tST\tGCAL\nB123456\tApfel\t50,5\n"
        files = {"file": ("bls_sample.txt", content.encode("utf-8"), "text/plain")}

        r = client_with_mock_db.post("/admin/upload-bls", files=files)
        assert r.status_code == 200, r.text
        body = r.json()
        # Endpoint should succeed and report 1 processed row
        assert body.get("added", 0) + body.get("updated", 0) == 1
        # The service should have parsed to a float 50.5 (not '50,5' string)
        assert captured["GCAL"] == pytest.approx(50.5, rel=0, abs=1e-6)

    @pytest.mark.asyncio
    @patch("app.services.bls_service.BLSService._bulk_upsert", autospec=True)
    def test_upload_txt_rejects_negative_values(self, mock_upsert, client_with_mock_db):
        """
        Negative nutrient values are not allowed by our spec -> validation error, no upsert call.
        """
        mock_upsert.return_value = 0  # should not be called if row is invalid

        content = "SBLS\tST\tGCAL\nB123457\tBirne\t-1\n"
        files = {"file": ("bls_negative.txt", content.encode("utf-8"), "text/plain")}

        r = client_with_mock_db.post("/admin/upload-bls", files=files)
        assert r.status_code == 200, r.text
        body = r.json()
        # Entire row should fail validation
        assert body.get("failed", 0) == 1
        assert isinstance(body.get("errors"), list) and len(body["errors"]) >= 1
        mock_upsert.assert_not_called()

    @pytest.mark.asyncio
    @patch("app.services.bls_service.BLSService._bulk_upsert", autospec=True)
    def test_upload_txt_wrong_delimiter_semicolon_yields_validation_errors(self, mock_upsert, client_with_mock_db):
        """
        Semicolon-delimited .txt should not parse as expected by read_table (tab default),
        leading to missing mandatory columns -> validation errors.
        """
        mock_upsert.return_value = 0

        content = "SBLS;ST;GCAL\nB123458;Kirsche;12,3\n"
        files = {"file": ("bls_semicolon.txt", content.encode("utf-8"), "text/plain")}

        r = client_with_mock_db.post("/admin/upload-bls", files=files)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("failed", 0) >= 1
        mock_upsert.assert_not_called()

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
    @patch("app.services.bls_service.BLSService._bulk_upsert", autospec=True)
    def test_upload_large_file_smoke_does_not_500(self, mock_upsert, client_with_mock_db):
        """
        Large-ish TXT (e.g., 2k rows) should be accepted without server error.
        We don't assert timing; we only ensure the request succeeds and upsert is invoked.
        """
        # Just return number of records to emulate success without DB
        mock_upsert.side_effect = lambda self, session, records: len(records)

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




