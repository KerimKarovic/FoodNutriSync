# scripts/generate_test_token.py
import os, time
from datetime import datetime, timedelta
from jose import jwt  # install: pip install python-jose[cryptography]
from dotenv import load_dotenv

load_dotenv()
SECRET = os.getenv("JWT_SECRET_KEY", "dev-secret")  # set in .env!
ALG = "HS256"
AUD = os.getenv("ALLOWED_APP_CODES", "KWAS,KOA,DDN,FWH,KA").split(",")

def make_token(email: str, roles, minutes: int = 1440):
    now = int(time.time())
    payload = {"iat": now, "exp": now + minutes*60, "sub": email, "email": email, "iss": "LM_AUTH", "aud": AUD, "roles": roles}
    return jwt.encode(payload, SECRET, algorithm=ALG)

if __name__ == "__main__":
    admin = make_token("admin@kiratik.de", ["ROLE_SUPER_ADMIN"])
    integ = make_token("integration@kiratik.de", ["ROLE_INTEGRATION"])
    print("\nAdmin:\nBearer", admin)
    print("\nIntegration:\nBearer", integ)
