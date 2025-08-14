import pytest
from unittest.mock import patch
from app.schemas import BLSSearchResponse

class TestSearchUX:
    """Test search user experience edge cases"""
    
    @pytest.mark.parametrize("search_term,should_work", [
        ("Äpfel", True),
        ("Apfel", True),
        ("Müsli", True),
        ("Musli", True),
        ("Weiß", True),
        ("Weiss", True),
        ("'; DROP TABLE bls; --", True),
        ("<script>alert('xss')</script>", True),
        ("", True),
        ("a" * 1000, True),
    ])
    @patch('app.services.bls_service.BLSService.search_by_name')
    def test_search_edge_cases(self, mock_search, search_term, should_work, client_with_mock_db):
        """Test search user experience edge cases"""
        mock_response = BLSSearchResponse(results=[], count=0)
        mock_search.return_value = mock_response
        
        response = client_with_mock_db.get(f"/bls/search?name={search_term}")
        assert response.status_code == 200
    
    @pytest.mark.parametrize("limit", [1, 50, 100, 101, -1, 0])
    @patch('app.services.bls_service.BLSService.search_by_name')
    def test_limit_clamping(self, mock_search, limit, client_with_mock_db):
        """Test limit parameter validation"""
        mock_response = BLSSearchResponse(results=[], count=0)
        mock_search.return_value = mock_response
        
        response = client_with_mock_db.get(f"/bls/search?limit={limit}")
        if limit > 100 or limit <= 0:
            assert response.status_code == 422
        else:
            assert response.status_code == 200

