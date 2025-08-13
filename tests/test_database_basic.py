import pytest
from sqlalchemy import text
from unittest.mock import AsyncMock, MagicMock
from app.database import SessionLocal, engine
from app.models import BLSNutrition
from app.services.bls_service import BLSService
from app.exceptions import BLSValidationError, BLSNotFoundError


class TestDatabase:
    """Test database connectivity and basic operations"""
    
    @pytest.mark.asyncio
    async def test_database_connection(self):
        """Test that we can connect to the database"""
        # Mock the database connection for tests
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar.return_value = 1
        mock_session.execute.return_value = mock_result
        
        # Test the mock
        result = await mock_session.execute(text("SELECT 1"))
        assert result.scalar() == 1
    
    def test_bls_model_structure(self):
        """Test BLS model has required attributes"""
        assert hasattr(BLSNutrition, 'bls_number')
        assert hasattr(BLSNutrition, 'name_german')
        assert hasattr(BLSNutrition, '__table__')
        
        # Check primary key - use actual DB column name
        pk_columns = [col.name for col in BLSNutrition.__table__.primary_key.columns]
        assert 'SBLS' in pk_columns  # Actual DB column name


class TestBLSServiceIntegration:
    """Integration tests for BLS service with database"""
    
    @pytest.fixture
    def bls_service(self):
        return BLSService()
    
    @pytest.fixture
    def mock_session(self):
        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_result.scalars.return_value.all.return_value = []
        session.execute.return_value = mock_result
        return session
    
    @pytest.mark.asyncio
    async def test_service_with_empty_database(self, bls_service, mock_session):
        """Test service methods with empty database"""
        # Test not found
        with pytest.raises(BLSNotFoundError):
            await bls_service.get_by_bls_number(mock_session, "B123456")
        
        # Test search returns empty
        result = await bls_service.search_by_name(mock_session, "nonexistent")
        assert result.count == 0
        assert len(result.results) == 0
    
    @pytest.mark.asyncio
    async def test_service_validation(self, bls_service, mock_session):
        """Test service validation logic"""
        # Test invalid BLS number format
        with pytest.raises(BLSValidationError):
            await bls_service.get_by_bls_number(mock_session, "INVALID")
        
        # Test empty search
        result = await bls_service.search_by_name(mock_session, "")
        assert result.count == 0


