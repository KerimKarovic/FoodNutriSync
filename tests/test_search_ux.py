import pytest
from unittest.mock import patch, AsyncMock
from app.schemas import BLSSearchResponse

class TestSearchUX:
    """Test search user experience edge cases"""
    
    @pytest.mark.parametrize("search_term,should_work", [
        ("Äpfel", True),
        ("Apfel", True),  # Should find Äpfel
        ("Müsli", True),
        ("Musli", True),  # Should find Müsli
        ("Weiß", True),
        ("Weiss", True),  # Should find Weiß
        ("'; DROP TABLE bls; --", True),  # SQL injection attempt
        ("<script>alert('xss')</script>", True),  # XSS attempt
        ("", True),  # Empty search
        ("a" * 1000, True),  # Very long search
    ])
    @patch('app.main.bls_service')
    def test_search_edge_cases(self, mock_service, search_term, should_work, client_with_mock_db):
        """Test search with various edge cases"""
        mock_service.search_by_name = AsyncMock(return_value=BLSSearchResponse(
            results=[], count=0
        ))
        
        response = client_with_mock_db.get(f"/bls/search?name={search_term}")
        
        if should_work:
            assert response.status_code == 200
        else:
            assert response.status_code in [400, 422]
    
    @pytest.mark.parametrize("limit", [1, 50, 100, 101, -1, 0])
    def test_limit_clamping(self, limit, client_with_mock_db):
        """Test limit parameter validation"""
        response = client_with_mock_db.get(f"/bls/search?name=test&limit={limit}")
        
        if 1 <= limit <= 100:
            assert response.status_code == 200
        else:
            assert response.status_code == 422  # Validation error
