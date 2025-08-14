import os
import sys
from pathlib import Path
from unittest.mock import Mock

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
import pytest
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from app.database import Base, get_session

# Load environment variables
load_dotenv()

@pytest.fixture(scope="session")
async def async_engine():
    """Create async engine for testing"""
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL environment variable is not set for testing.")
    
    engine = create_async_engine(
        database_url,
        echo=False,  # Set to True for SQL debugging
        future=True
    )
    
    # Create tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    yield engine
    
    # Cleanup
    await engine.dispose()

@pytest.fixture
async def async_session(async_engine):
    """Create async session for each test"""
    async_session_maker = async_sessionmaker(
        async_engine, 
        expire_on_commit=False
    )
    
    async with async_session_maker() as session:
        yield session

@pytest.fixture
def client_with_mock_db():
    """Create test client with mocked database"""
    from app.main import app
    from fastapi.testclient import TestClient
    
    # Override dependencies for testing
    def override_get_session():
        return Mock()
    
    def override_auth():
        return True  # Mock authentication
    
    app.dependency_overrides[get_session] = override_get_session
    # Add auth override if you have authentication
    # app.dependency_overrides[get_current_user] = override_auth
    
    client = TestClient(app)
    yield client
    
    # Clean up
    app.dependency_overrides.clear()

