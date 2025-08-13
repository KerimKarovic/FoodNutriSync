
import pytest
from unittest.mock import AsyncMock, MagicMock
from app.services.bls_service import BLSService, BLSDataValidator
from app.exceptions import BLSValidationError, BLSNotFoundError
import pandas as pd


class TestBLSService:
    """Test BLS service business logic"""
    
    @pytest.fixture
    def bls_service(self):
        return BLSService()
    
    @pytest.fixture
    def mock_session(self):
        return AsyncMock()
    
    @pytest.mark.asyncio
    async def test_get_by_bls_number_invalid_format(self, bls_service, mock_session):
        """Test BLS number validation"""
        with pytest.raises(BLSValidationError):
            await bls_service.get_by_bls_number(mock_session, "INVALID")
    
    @pytest.mark.asyncio
    async def test_get_by_bls_number_not_found(self, bls_service, mock_session):
        """Test BLS number not found"""
        # Mock empty result
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result
        
        with pytest.raises(BLSNotFoundError):
            await bls_service.get_by_bls_number(mock_session, "B123456")


class TestBLSDataValidator:
    """Test BLS data validation logic"""
    
    @pytest.fixture
    def validator(self):
        return BLSDataValidator()
    
    def test_validate_bls_number_valid(self, validator):
        """Test valid BLS number patterns"""
        row = pd.Series({'SBLS': 'B123456', 'STE': 'Test Food'})
        assert validator._extract_bls_number(row) == 'B123456'
    
    def test_validate_bls_number_invalid(self, validator):
        """Test invalid BLS number patterns"""
        row = pd.Series({'SBLS': 'INVALID', 'STE': 'Test Food'})
        assert validator._extract_bls_number(row) is None
    
    def test_validate_name_extraction(self, validator):
        """Test German name extraction"""
        row = pd.Series({'SBLS': 'B123456', 'ST': 'Test Food'})
        assert validator._extract_german_name(row) == 'Test Food'
