import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient
from app.main import app, get_session
from app.services.bls_service import BLSService


@pytest.fixture(scope="function")
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


@pytest.fixture(scope="function")
def mock_bls_service():
    """Mock BLS service for testing"""
    return AsyncMock(spec=BLSService)


@pytest.fixture(scope="function")
def client_with_mock_db(mock_session):
    """Test client with mocked database and logger"""
    app.dependency_overrides[get_session] = lambda: mock_session
    
    # Mock the logger to prevent logging errors in tests
    with patch('app.main.app_logger') as mock_logger:
        mock_logger.log_api_query = MagicMock()
        mock_logger.log_upload_start = MagicMock()
        mock_logger.log_upload_success = MagicMock()
        mock_logger.log_upload_error = MagicMock()
        mock_logger.logger = MagicMock()
        
        with TestClient(app) as client:
            yield client
    
    # Clean up
    app.dependency_overrides.clear()









