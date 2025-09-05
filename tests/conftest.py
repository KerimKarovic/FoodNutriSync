import pytest
import asyncio
from fastapi.testclient import TestClient
from unittest.mock import Mock, AsyncMock, MagicMock, patch
from sqlalchemy.ext.asyncio import AsyncSession
import os
from app.main import app
@pytest.fixture
def client():
    """Basic test client"""
    return TestClient(app)

@pytest.fixture(scope="session", autouse=True)
def _set_test_env():
    os.environ.setdefault("TESTING", "1")
    os.environ.setdefault("ADMIN_TOKEN", "test-token")
    os.environ.setdefault("JWT_SECRET_KEY", "test-secret")
    os.environ.setdefault("LICENSEMANAGER_PUBLIC_KEY_PEM", "test-key")

@pytest.fixture
def public_client():
    """Test client for public endpoints (no auth)"""
    with patch.dict(os.environ, {"TESTING": "1", "ENVIRONMENT": "development"}):
        yield TestClient(app)

@pytest.fixture
def mock_jwt_user():
    """Mock JWT user for BLS reader endpoints"""
    return {
        "sub": "integration@example.com",
        "email": "integration@example.com", 
        "roles": ["ROLE_INTEGRATION"],
        "iss": "LM_AUTH"
    }

@pytest.fixture
def mock_admin_user():
    """Mock admin user for admin endpoints"""
    return {
        "sub": "admin@example.com",
        "email": "admin@example.com",
        "roles": ["ROLE_SUPER_ADMIN"],
        "iss": "LM_AUTH"
    }

@pytest.fixture
def client_with_mock_db():
    """Test client with mocked database"""
    with patch('app.database.get_session') as mock_get_session:
        mock_session = AsyncMock()
        mock_session.execute.return_value.scalar.return_value = 1
        mock_get_session.return_value = mock_session
        
        with patch.dict(os.environ, {"TESTING": "1"}):
            yield TestClient(app)

@pytest.fixture
def client_with_bls_auth(mock_jwt_user):
    """Test client with JWT auth for BLS endpoints"""
    with patch('app.auth.get_current_user', return_value=mock_jwt_user), \
        patch('app.auth.require_bls_reader', return_value=mock_jwt_user):
        yield TestClient(app)

@pytest.fixture  
def client_with_admin_auth(mock_admin_user):
    """Test client with cookie auth for admin endpoints"""
    with patch('app.auth.get_current_admin_cookie', return_value=mock_admin_user), \
        patch('app.auth.require_admin_cookie', return_value=mock_admin_user):
        yield TestClient(app)

@pytest.fixture
def sample_bls_data():
    """Sample BLS data for testing"""
    return "SBLS\tST\tENERC\tEPRO\tVC\tMNA\nB123456\tTest Food\t100\t5.0\t2.0\t50"

@pytest.fixture
def mock_azure_env(monkeypatch):
    """Mock Azure environment variables for testing"""
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("AZURE_POSTGRES_FQDN", "test-server.postgres.database.azure.com")
    monkeypatch.setenv("AZURE_POSTGRES_DB", "test_db")
    monkeypatch.setenv("AZURE_POSTGRES_USER", "test_user")
    monkeypatch.setenv("AZURE_POSTGRES_PASSWORD", "test_password")
    monkeypatch.setenv("AZURE_APPINSIGHTS_CONNECTION_STRING", "InstrumentationKey=test-key")
    monkeypatch.setenv("AZURE_CONTAINERAPPS_ENV", "test-env")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://test_user:test_password@test-server.postgres.database.azure.com:5432/test_db")
    monkeypatch.setenv("ALEMBIC_DATABASE_URL", "postgresql+psycopg2://test_user:test_password@test-server.postgres.database.azure.com:5432/test_db")


@pytest.fixture
def client_with_auth(mock_user):
    """Test client with mocked authentication"""
    from app.main import app
    
    # Mock all auth dependencies that are used in main.py
    with patch('app.auth.get_current_user', return_value=mock_user), \
        patch('app.auth.require_admin', return_value=mock_user), \
        patch('app.auth.require_bls_reader', return_value=mock_user), \
        patch('app.main.get_current_user', return_value=mock_user), \
        patch('app.main.require_admin', return_value=mock_user), \
        patch('app.main.require_bls_reader', return_value=mock_user):
        
        # Set testing environment
        with patch.dict(os.environ, {"ENVIRONMENT": "development", "TESTING": "1"}):
            yield TestClient(app)

@pytest.fixture
def client_with_mock_db_and_auth(client_with_mock_db):
    """Test client with both mocked database and authentication"""
    with patch('app.auth.get_current_user') as mock_get_user, \
         patch('app.auth.require_bls_reader') as mock_require_bls:
        
        mock_user = {
            "user_id": "test_user",
            "roles": ["Admin", "BLS-Data-Reader"],
            "email": "test@example.com"
        }
        mock_get_user.return_value = mock_user
        mock_require_bls.return_value = mock_user
        
        yield client_with_mock_db
