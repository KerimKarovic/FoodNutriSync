# scripts/generate_test_token.py
import os, time
from datetime import datetime, timedelta
from jose import jwt  # install: pip install python-jose[cryptography]
from dotenv import load_dotenv

load_dotenv()
SECRET = os.getenv("JWT_SECRET_KEY", "dev-secret")  # set in .env!
ALG = "HS256"
AUD = os.getenv("LICENSEMANAGER_AUDIENCE", "FNS")  # Updated to match your config

def make_token(email: str, roles, minutes: int = 1440):
    now = int(time.time())
    payload = {
        "iat": now, 
        "exp": now + minutes*60, 
        "sub": email, 
        "email": email, 
        "iss": "LM_AUTH",  # Match your LICENSEMANAGER_ISS
        "aud": AUD, 
        "roles": roles
    }
    return jwt.encode(payload, SECRET, algorithm=ALG)

if __name__ == "__main__":
    # Updated role names to match your new auth system
    admin = make_token("admin@kiratik.de", ["ROLE_SUPER_ADMIN"])
    integ = make_token("integration@kiratik.de", ["ROLE_INTEGRATION"])
    
    print("\n=== JWT Tokens for FoodNutriSync ===")
    print(f"\nAdmin (ROLE_SUPER_ADMIN):")
    print(f"Bearer {admin}")
    print(f"\nIntegration (ROLE_INTEGRATION):")
    print(f"Bearer {integ}")
    
    # Test invalid role
    invalid = make_token("user@kiratik.de", ["ROLE_USER"])
    print(f"\nInvalid Role (should be rejected):")
    print(f"Bearer {invalid}")
    
    print(f"\n=== Usage ===")
    print(f"1. Copy a token above")
    print(f"2. Go to http://localhost:8000/docs")
    print(f"3. Click 'Authorize' and paste the full 'Bearer ...' string")
    print(f"4. Test BLS endpoints (admin token works for everything)")


