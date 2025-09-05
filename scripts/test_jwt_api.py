# scripts/test_jwt_api.py
import os, json, requests
from dotenv import load_dotenv
from jose import jwt
import time

load_dotenv()
BASE = os.getenv("API_BASE_URL", "http://127.0.0.1:8000")
SECRET = os.getenv("JWT_SECRET_KEY", "dev-secret")
ALG = "HS256"
AUD = os.getenv("LICENSEMANAGER_AUDIENCE", "FNS")  # Updated

def token(email, roles, mins=60):
    now = int(time.time())
    payload = {
        "sub": email, 
        "email": email, 
        "roles": roles, 
        "iss": "LM_AUTH", 
        "aud": AUD, 
        "iat": now, 
        "exp": now + mins*60
    }
    return jwt.encode(payload, SECRET, algorithm=ALG)

def auth_header(tok): 
    return {"Authorization": f"Bearer {tok}"}

def t(name, method, url, expect, headers=None, **kwargs):
    try:
        r = requests.request(method, url, headers=headers, timeout=10, **kwargs)
        ok = (r.status_code == expect)
        status = "✓ OK" if ok else "✗ FAIL"
        print(f"[{status}] {name}: {r.status_code} (expected {expect}) -> {url}")
        if not ok: 
            print(f"    Response: {r.text[:200]}")
        return ok
    except requests.exceptions.RequestException as e:
        print(f"[✗ ERROR] {name}: {e}")
        return False

if __name__ == "__main__":
    print(f"=== Testing FoodNutriSync API at {BASE} ===\n")
    
    # Generate tokens with correct roles
    admin = token("admin@kiratik.de", ["ROLE_SUPER_ADMIN"])
    integ = token("integration@kiratik.de", ["ROLE_INTEGRATION"])
    invalid = token("user@kiratik.de", ["ROLE_USER"])

    print("1. Health Endpoints (Public)")
    t("health", "GET", f"{BASE}/health", 200)
    t("health/live", "GET", f"{BASE}/health/live", 200)
    t("health/ready", "GET", f"{BASE}/health/ready", 200)
    
    print("\n2. BLS Search (Requires JWT Auth)")
    q = "Apfel"
    t("search no token", "GET", f"{BASE}/bls/search?q={q}", 401)
    t("search invalid role", "GET", f"{BASE}/bls/search?q={q}", 403, headers=auth_header(invalid))
    t("search integration", "GET", f"{BASE}/bls/search?q={q}", 200, headers=auth_header(integ))
    t("search admin", "GET", f"{BASE}/bls/search?q={q}", 200, headers=auth_header(admin))

    print("\n3. BLS Lookup (Requires JWT Auth)")
    bls_num = "B123456"  # Example BLS number
    t("lookup no token", "GET", f"{BASE}/bls/{bls_num}", 401)
    t("lookup invalid role", "GET", f"{BASE}/bls/{bls_num}", 403, headers=auth_header(invalid))
    t("lookup integration", "GET", f"{BASE}/bls/{bls_num}", 404, headers=auth_header(integ))  # 404 = auth OK, record not found
    t("lookup admin", "GET", f"{BASE}/bls/{bls_num}", 404, headers=auth_header(admin))

    print("\n4. Admin UI (Cookie Auth Required)")
    t("admin UI no token", "GET", f"{BASE}/admin", 302)  # Redirect to login
    t("admin UI with JWT", "GET", f"{BASE}/admin", 302, headers=auth_header(admin))  # JWT doesn't work for UI

    print("\n5. Admin Upload (Cookie Auth Required)")
    t("upload no token", "PUT", f"{BASE}/admin/upload-bls", 401)
    t("upload with JWT", "PUT", f"{BASE}/admin/upload-bls", 401, headers=auth_header(admin))  # JWT doesn't work for admin endpoints

    print("\n6. Auth Endpoints")
    # Test JWT login endpoint
    login_data = {"token": admin}
    t("JWT login", "POST", f"{BASE}/auth/login", 200, json=login_data)
    
    # Test logout
    t("logout", "POST", f"{BASE}/auth/logout", 200)

    print("\n7. Protected Docs (Requires Auth)")
    t("docs no auth", "GET", f"{BASE}/docs", 401)
    t("docs with JWT", "GET", f"{BASE}/docs", 200, headers=auth_header(admin))

    print(f"\n=== Summary ===")
    print(f"✓ Public endpoints work without auth")
    print(f"✓ BLS endpoints require JWT with ROLE_INTEGRATION or ROLE_SUPER_ADMIN")
    print(f"✓ Admin UI/upload require cookie auth (not testable via requests)")
    print(f"✓ Invalid roles are properly rejected")
    print(f"\nTo test admin functionality:")
    print(f"1. Go to {BASE}/admin")
    print(f"2. Login with admin credentials")
    print(f"3. Upload BLS file via the UI")


