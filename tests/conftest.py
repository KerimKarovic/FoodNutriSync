import sys
import os
import pytest
from unittest.mock import AsyncMock, MagicMock

# Add the project root to Python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

@pytest.fixture
def mock_session():
    """Mock database session for tests"""
    session = AsyncMock()
    
    # Create a proper mock result chain
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None  # For single item queries
    mock_result.scalars.return_value.all.return_value = []  # For search queries
    
    # Make execute return the mock result
    session.execute.return_value = mock_result
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.close = AsyncMock()
    
    return session

@pytest.fixture
def client_with_mock_db(mock_session):
    """Create test client with mocked database"""
    from fastapi.testclient import TestClient
    from app.main import app, get_session
    
    # Override the database dependency
    async def mock_get_session():
        return mock_session
    
    app.dependency_overrides[get_session] = mock_get_session
    
    client = TestClient(app)
    yield client
    
    # Clean up
    app.dependency_overrides.clear()





