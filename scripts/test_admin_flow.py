# scripts/test_admin_flow.py
"""
Test admin authentication flow using requests session to handle cookies
"""
import os, requests
from dotenv import load_dotenv

load_dotenv()
BASE = os.getenv("API_BASE_URL", "http://127.0.0.1:8000")
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "admin@kiratik.de")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")

def test_admin_flow():
    """Test complete admin authentication and upload flow"""
    session = requests.Session()
    
    print(f"=== Testing Admin Flow at {BASE} ===\n")
    
    # 1. Try admin UI without auth (should redirect)
    print("1. Testing admin UI access...")
    r = session.get(f"{BASE}/admin", allow_redirects=False)
    print(f"   Admin UI without auth: {r.status_code} (expected 302 redirect)")
    
    # 2. Try admin login
    print("\n2. Testing admin login...")
    login_data = {"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
    r = session.post(f"{BASE}/auth/admin-login", json=login_data)
    print(f"   Admin login: {r.status_code}")
    if r.status_code == 200:
        print(f"   Login successful!")
    else:
        print(f"   Login failed: {r.text[:200]}")
        return
    
    # 3. Try admin UI with cookie
    print("\n3. Testing admin UI with cookie...")
    r = session.get(f"{BASE}/admin")
    print(f"   Admin UI with cookie: {r.status_code}")
    if r.status_code == 200:
        print(f"   ✓ Admin UI accessible")
    else:
        print(f"   ✗ Admin UI still blocked: {r.text[:200]}")
    
    # 4. Try admin upload with cookie
    print("\n4. Testing admin upload...")
    sample_data = "SBLS\tST\tENERC\nB123456\tTest Food\t100"
    files = {"file": ("test.txt", sample_data, "text/plain")}
    r = session.put(f"{BASE}/admin/upload-bls", files=files)
    print(f"   Admin upload: {r.status_code}")
    if r.status_code == 200:
        print(f"   ✓ Upload successful: {r.json()}")
    else:
        print(f"   Upload response: {r.text[:200]}")
    
    # 5. Test logout
    print("\n5. Testing logout...")
    r = session.post(f"{BASE}/auth/logout")
    print(f"   Logout: {r.status_code}")
    
    # 6. Verify admin UI blocked after logout
    print("\n6. Testing admin UI after logout...")
    r = session.get(f"{BASE}/admin", allow_redirects=False)
    print(f"   Admin UI after logout: {r.status_code} (expected 302)")

if __name__ == "__main__":
    test_admin_flow()