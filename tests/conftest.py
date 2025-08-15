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
    
    # Cleanup
    app.dependency_overrides.clear()

# REMOVE: Any unused fixtures like async_session, mock_bls_service, etc.


