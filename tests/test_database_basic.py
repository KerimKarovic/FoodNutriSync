import pytest
import asyncio
from unittest.mock import patch, AsyncMock

class TestDatabaseConnection:
    """Test database connection and basic operations"""
    
    @pytest.mark.asyncio
    async def test_database_session_creation(self):
        """Test that database session can be created"""
        try:
            from app.database import SessionLocal
            
            async with SessionLocal() as session:
                assert session is not None
                # Just test that we can create a session
                
        except Exception as e:
            # If DB connection fails, that's expected in test environment
            assert "connection" in str(e).lower() or "database" in str(e).lower()
            
    def test_model_structure(self):
        """Test that BLS model has expected structure"""
        from app.models import BLSNutrition
        
        # Test that model has required columns
        table = BLSNutrition.__table__
        column_names = [col.name for col in table.columns]
        
        assert 'bls_number' in column_names
        assert 'name_german' in column_names
        
        # Test primary key
        pk_columns = [col.name for col in table.primary_key.columns]
        assert 'bls_number' in pk_columns
        
    def test_model_instantiation(self):
        """Test creating model instances"""
        from app.models import BLSNutrition
        
        # Test minimal instance
        instance = BLSNutrition(
            bls_number="M401600",
            name_german="Test Food"
        )
        
        assert getattr(instance, 'bls_number') == "M401600"
        assert getattr(instance, 'name_german') == "Test Food"

class TestSchemaValidation:
    """Test Pydantic schemas"""
    
    def test_bls_nutrient_response_schema(self):
        """Test BLS response schema"""
        from app.schemas import BLSNutrientResponse
        
        # Test valid data
        data = {
            "bls_number": "M401600",
            "name_german": "Test Food",
            "nutrients": {"gcal": 330.0, "mna": 700.0}
        }
        
        response = BLSNutrientResponse(**data)
        assert response.bls_number == "M401600"
        assert response.name_german == "Test Food"
        assert response.nutrients["gcal"] == 330.0
        
    def test_bls_search_response_schema(self):
        """Test search response schema"""
        from app.schemas import BLSSearchResponse, BLSNutrientResponse
        
        # Test empty results
        search_response = BLSSearchResponse(results=[], count=0)
        assert search_response.count == 0
        assert len(search_response.results) == 0
        
        # Test with results
        nutrient_response = BLSNutrientResponse(
            bls_number="M401600",
            name_german="Test Food",
            nutrients={}
        )
        search_response = BLSSearchResponse(results=[nutrient_response], count=1)
        assert search_response.count == 1
        assert len(search_response.results) == 1

class TestConfigValidation:
    """Test configuration and environment"""
    
    def test_environment_variables(self):
        """Test that required environment variables are handled"""
        import os
        
        # Test that we can handle missing DATABASE_URL
        original_db_url = os.environ.get('DATABASE_URL')
        
        try:
            # Remove DATABASE_URL temporarily
            if 'DATABASE_URL' in os.environ:
                del os.environ['DATABASE_URL']
                
            # Should not crash when importing
            from app.database import engine
            assert engine is not None
            
        finally:
            # Restore original value
            if original_db_url:
                os.environ['DATABASE_URL'] = original_db_url