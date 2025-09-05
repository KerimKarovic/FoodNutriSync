# scripts/test_jwt_api.py
import os, json, requests
from dotenv import load_dotenv
from jose import jwt
import time

load_dotenv()
BASE = os.getenv("API_BASE_URL", "http://127.0.0.1:8000")
SECRET = os.getenv("JWT_SECRET_KEY", "dev-secret")
ALG = "HS256"
AUD = os.getenv("ALLOWED_APP_CODES", "KWAS,KOA,DDN,FWH,KA").split(",")

def token(email, roles, mins=60):
    now = int(time.time())  # Use time.time() instead of datetime.utcnow().timestamp()
    payload = {"sub": email, "email": email, "roles": roles, "iss": "LM_AUTH", "aud": AUD, "iat": now, "exp": now + mins*60}
    return jwt.encode(payload, SECRET, algorithm=ALG)

def auth_header(tok): return {"Authorization": f"Bearer {tok}"}

def t(name, method, url, expect, headers=None, **kwargs):
    r = requests.request(method, url, headers=headers, **kwargs)
    ok = (r.status_code == expect)
    print(f"[{'OK' if ok else '!!'}] {name}: {r.status_code} (expected {expect}) -> {url}")
    if not ok: print("Response:", r.text[:300])
    return ok

if __name__ == "__main__":
    admin = token("admin@kiratik.de", ["ROLE_SUPER_ADMIN"])
    integ = token("integration@kiratik.de", ["ROLE_INTEGRATION"])

    # 1) /bls/search (should be readable by integration & admin)
    q = "Apfel"
    t("bls/search no token", "GET", f"{BASE}/bls/search?q={q}", 401)
    t("bls/search integration", "GET", f"{BASE}/bls/search?q={q}", 200, headers=auth_header(integ))
    t("bls/search admin", "GET", f"{BASE}/bls/search?q={q}", 200, headers=auth_header(admin))

    # 2) /admin UI (HTML) — should be 302 (redirect to /login) for integration, 200 for admin
    t("admin UI no token", "GET", f"{BASE}/admin", 302)
    t("admin UI integration", "GET", f"{BASE}/admin", 302, headers=auth_header(integ))
    t("admin UI admin", "GET", f"{BASE}/admin", 200, headers=auth_header(admin))

    # 3) /admin/upload-bls — should be forbidden for integration (403), allowed for admin (likely 422/400 without a real file)
    t("upload-bls no token", "PUT", f"{BASE}/admin/upload-bls", 401)
    t("upload-bls integration", "PUT", f"{BASE}/admin/upload-bls", 403, headers=auth_header(integ))
    # admin call without file -> 422 expected (validates permission first, then body)
    t("upload-bls admin (no file)", "PUT", f"{BASE}/admin/upload-bls", 422, headers=auth_header(admin))

