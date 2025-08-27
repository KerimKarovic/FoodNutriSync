import pytest
import asyncio
from fastapi.testclient import TestClient
from unittest.mock import Mock, AsyncMock, MagicMock, patch
from sqlalchemy.ext.asyncio import AsyncSession
import os
import tempfile
from io import BytesIO

@pytest.fixture
def client():
    """Basic test client"""
    from app.main import app
    return TestClient(app)

@pytest.fixture
def client_with_mock_db():
    """Test client with mocked database"""
    from app.main import app
    with patch('app.main.get_session') as mock_get_session:
        mock_session = AsyncMock(spec=AsyncSession)
        mock_get_session.return_value = mock_session
        yield TestClient(app)

@pytest.fixture
def sample_bls_data():
    """Sample BLS data for testing"""
    return """SBLS\tST\tENERC\tEPRO\tVC\tMNA
B123456\tApfel\t52\t0.3\t4.6\t3
B789012\tBirne\t57\t0.4\t10.4\t7
C345678\tBanane\t89\t1.1\t22.8\t27"""

@pytest.fixture
def sample_csv_file(sample_bls_data):
    """Create temporary CSV file for testing"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        f.write(sample_bls_data)
        f.flush()
        yield f.name
    os.unlink(f.name)

@pytest.fixture
def mock_azure_env():
    """Mock Azure environment variables"""
    env_vars = {
        'DATABASE_URL': 'postgresql+asyncpg://test:test@localhost:5432/test_db',
        'ALEMBIC_DATABASE_URL': 'postgresql+psycopg2://test:test@localhost:5432/test_db',
        'ENVIRONMENT': 'testing',
        'LOG_LEVEL': 'DEBUG'
    }
    with patch.dict(os.environ, env_vars):
        yield env_vars

@pytest.fixture
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()
