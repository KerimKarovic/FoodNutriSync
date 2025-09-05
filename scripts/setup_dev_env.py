# scripts/setup_dev_env.py
"""
Setup development environment with proper JWT keys and test data
"""
import os
from pathlib import Path
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

def generate_jwt_keypair():
    """Generate RSA keypair for JWT testing"""
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )
    
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption()
    )
    
    public_key = private_key.public_key()
    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    )
    
    return private_pem.decode(), public_pem.decode()

def setup_env_file():
    """Create .env file with development settings"""
    project_root = Path(__file__).parent.parent
    env_file = project_root / ".env"
    
    if env_file.exists():
        print(f"✓ .env file already exists at {env_file}")
        return
    
    private_key, public_key = generate_jwt_keypair()
    
    env_content = f'''# FoodNutriSync Development Environment
# Database
DATABASE_URL=postgresql+asyncpg://postgres:password@localhost:5432/nutrisync_dev
ALEMBIC_DATABASE_URL=postgresql+psycopg2://postgres:password@localhost:5432/nutrisync_dev

# JWT Authentication (Development Keys)
JWT_SECRET_KEY=dev-secret-key-change-in-production
LICENSEMANAGER_PUBLIC_KEY_PEM="{public_key}"
LICENSEMANAGER_ISS=LM_AUTH
LICENSEMANAGER_AUDIENCE=FNS
JWT_ALGORITHM=RS256

# Admin Credentials (Development Only)
ADMIN_EMAIL=admin@kiratik.de
ADMIN_PASSWORD=admin123

# Environment
ENVIRONMENT=development
LOG_LEVEL=DEBUG
API_BASE_URL=http://127.0.0.1:8000

# Testing
TESTING=0
'''
    
    env_file.write_text(env_content)
    print(f"✓ Created .env file at {env_file}")
    print(f"✓ Generated development JWT keypair")
    print(f"\nNext steps:")
    print(f"1. Update database credentials in .env")
    print(f"2. Run: alembic upgrade head")
    print(f"3. Run: uvicorn app.main:app --reload")

if __name__ == "__main__":
    setup_env_file()