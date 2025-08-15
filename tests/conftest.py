import pytest
from fastapi.testclient import TestClient
from unittest.mock import Mock, AsyncMock, MagicMock
from sqlalchemy.ext.asyncio import AsyncSession

@pytest.fixture
def client():
    """Basic test client"""
    from app.main import app
    return TestClient(app)

@pytest.fixture
def client_with_mock_db():
    """Create test client with mocked database and disabled auth"""
    from app.main import app
    from app.database import get_session
    from app.auth import get_current_user, require_admin
    
    def override_get_session():
        return Mock()
    
    def override_get_current_user():
        return {
            "user_id": "test_user", 
            "roles": ["User", "Admin"],
            "payload": {"sub": "test_user", "roles": ["User", "Admin"]}
        }
    
    def override_require_admin():
        return {
            "user_id": "admin_user", 
            "roles": ["Admin"],
            "payload": {"sub": "admin_user", "roles": ["Admin"]}
        }
    
    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[get_current_user] = override_get_current_user
    app.dependency_overrides[require_admin] = override_require_admin
    
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()

@pytest.fixture
def async_session():
    """Mock async session for testing"""
    session = AsyncMock(spec=AsyncSession)
    
    # Configure the mock to handle basic operations
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.close = AsyncMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    
    # Make sure execute returns a mock result that behaves like a real result
    mock_result = AsyncMock()
    mock_result.fetchall.return_value = []
    mock_result.fetchone.return_value = None
    mock_result.scalar.return_value = None
    mock_result.scalar_one.return_value = 0
    mock_result.scalar_one_or_none.return_value = None
    mock_result.scalars.return_value.all.return_value = []
    mock_result.scalars.return_value.first.return_value = None
    
    # Make execute always return the mock result
    session.execute.return_value = mock_result
    
    # Make sure the session doesn't raise any async-related errors
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)
    
    return session

