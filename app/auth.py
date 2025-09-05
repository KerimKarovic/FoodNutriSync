# app/auth.py
from __future__ import annotations

import os
import secrets
import logging
from typing import Any, Dict, List, Optional, Union

from fastapi import APIRouter, Body, Depends, HTTPException, Request, Response, Security, status
from fastapi.security import HTTPBearer
import jwt  # PyJWT
from jwt import PyJWTError

logger = logging.getLogger(__name__)

auth_router = APIRouter()
docs_bearer = HTTPBearer(auto_error=False)  # for Swagger "Authorize"

# -----------------------------
# Cookie helpers
# -----------------------------
def _cookie_cfg() -> Dict[str, Any]:
    name = os.getenv("AUTH_COOKIE_NAME", "lm_token")
    domain = os.getenv("AUTH_COOKIE_DOMAIN") or None
    path = os.getenv("AUTH_COOKIE_PATH", "/")
    max_age = int(os.getenv("AUTH_COOKIE_MAX_AGE_SECONDS", "86400"))
    same_site = os.getenv("AUTH_COOKIE_SAMESITE", "strict").lower()  # 'lax' | 'strict' | 'none'
    env = os.getenv("ENVIRONMENT", "development").lower()
    secure = same_site == "none" or env == "production"
    return dict(name=name, domain=domain, path=path, max_age=max_age, samesite=same_site, secure=secure, httponly=True)

def set_auth_cookie(response: Response, token: str) -> None:
    cfg = _cookie_cfg()
    response.set_cookie(
        key=cfg["name"], value=token, max_age=cfg["max_age"], path=cfg["path"],
        domain=cfg["domain"], secure=cfg["secure"], httponly=cfg["httponly"], samesite=cfg["samesite"]
    )

def clear_auth_cookie(response: Response) -> None:
    cfg = _cookie_cfg()
    response.delete_cookie(key=cfg["name"], path=cfg["path"], domain=cfg["domain"])
    # legacy cleanup
    response.delete_cookie(key="admin_session", path="/", domain=cfg["domain"])

# -----------------------------
# JWT verification (HS256 for local tests, RS256 for LM)
# -----------------------------
class JWTVerifier:
    def __init__(self) -> None:
        self.issuer = os.getenv("LICENSEMANAGER_ISS", "LM_AUTH")
        self.clock_skew = int(os.getenv("JWT_CLOCK_SKEW_SECONDS", "300"))
        self.rs_alg = os.getenv("JWT_ALGORITHM", "RS256")
        self._public_key_pem: Optional[bytes] = None

    async def _load_public_key_pem(self) -> bytes:
        pem = os.getenv("LICENSEMANAGER_PUBLIC_KEY_PEM")
        if pem:
            return pem.encode("utf-8")
        url = os.getenv("LICENSEMANAGER_PUBLIC_KEY_URL")
        if not url:
            raise RuntimeError("Public key not configured: set LICENSEMANAGER_PUBLIC_KEY_PEM or LICENSEMANAGER_PUBLIC_KEY_URL")
        # simple, sync fetch using urllib to avoid pulling httpx here
        import urllib.request
        with urllib.request.urlopen(url, timeout=10) as r:
            return r.read()

    async def _public_key(self):
        if not self._public_key_pem:
            self._public_key_pem = await self._load_public_key_pem()
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        
        key = serialization.load_pem_public_key(self._public_key_pem)
        if not isinstance(key, rsa.RSAPublicKey):
            raise RuntimeError("Expected RSA public key for RS256 algorithm")
        return key

    def _expected_audiences(self) -> List[str]:
        """
        Allowed audiences for tokens (comma-separated env). Defaults match the senior project’s pattern.
        """
        raw = os.getenv("ALLOWED_APP_CODES", "KWAS,KOA,DDN,FWH,KA")
        return [x.strip() for x in raw.split(",") if x.strip()]

    def _validate_audience(self, payload: Dict[str, Any]) -> None:
        token_aud = payload.get("aud")
        if not token_aud:
            raise HTTPException(status_code=403, detail="Token missing audience claim")
        if isinstance(token_aud, str):
            token_aud_list = [token_aud]
        elif isinstance(token_aud, list):
            token_aud_list = token_aud
        else:
            raise HTTPException(status_code=403, detail="Invalid audience format")
        if not any(a in self._expected_audiences() for a in token_aud_list):
            raise HTTPException(
                status_code=403,
                detail=f"Invalid token audience. Expected one of: {self._expected_audiences()}, got: {token_aud_list}"
            )

    async def decode(self, token: str) -> Dict[str, Any]:
        try:
            header = jwt.get_unverified_header(token)
            alg = header.get("alg")
        except PyJWTError:
            raise HTTPException(status_code=403, detail="Invalid token header")

        # Select key & algorithms based on alg
        if alg == "HS256":
            key = os.getenv("JWT_SECRET_KEY")
            if not key:
                raise HTTPException(status_code=500, detail="HS256 used but JWT_SECRET_KEY not set")
            algorithms = ["HS256"]
        elif alg == "RS256":
            key = await self._public_key()
            algorithms = [self.rs_alg]
        else:
            raise HTTPException(status_code=403, detail=f"Unsupported algorithm: {alg}")

        try:
            # Decode without audience, then validate audience manually (string/list). :contentReference[oaicite:4]{index=4}
            payload = jwt.decode(
                token,
                key=key,
                algorithms=algorithms,
                issuer=self.issuer,
                options={"verify_aud": False},
                leeway=self.clock_skew,
            )
            self._validate_audience(payload)  # manual aud check
            roles = payload.get("roles") or []
            if not isinstance(roles, list):
                roles = [roles]
            payload["roles"] = roles
            return payload
        except PyJWTError as e:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Invalid token: {e}")

jwt_verifier = JWTVerifier()

def _dev_bypass_enabled() -> bool:
    return os.getenv("TESTING") == "1" or os.getenv("ENVIRONMENT", "development").lower() == "development"

def _get_token_from_request(request: Request) -> Optional[str]:
    # Bearer header first
    auth = request.headers.get("Authorization")
    if auth and auth.lower().startswith("bearer "):
        return auth.split(" ", 1)[1].strip()
    # Cookie
    return request.cookies.get(_cookie_cfg()["name"])

# -----------------------------
# Current user + role guards
# -----------------------------
async def get_current_user(request: Request) -> Dict[str, Any]:
    if _dev_bypass_enabled() and os.getenv("AUTH_DEV_BYPASS", "0") == "1":
        # Enable only when you explicitly set AUTH_DEV_BYPASS=1
        return {"sub": "dev@test.local", "email": "dev@test.local", "roles": ["ROLE_SUPER_ADMIN"], "bypass": True}

    token = _get_token_from_request(request)
    if not token:
        raise HTTPException(status_code=401, detail="Missing token")
    return await jwt_verifier.decode(token)

def _is_admin(roles: List[str]) -> bool:
    return any(r in {"ROLE_SUPER_ADMIN", "Super-Admin", "Admin", "ROLE_ADMIN"} for r in roles)

def _is_bls_reader(roles: List[str]) -> bool:
    return "ROLE_INTEGRATION" in roles or _is_admin(roles)

async def require_admin(user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    if not _is_admin(user.get("roles", [])):
        raise HTTPException(status_code=403, detail="Admin role required")
    return user

async def require_bls_reader(user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    if not _is_bls_reader(user.get("roles", [])):
        raise HTTPException(status_code=403, detail="BLS read permission required")
    return user

def get_current_user_with_roles(required_roles: List[str]):
    """
    Matches senior project pattern: dependency factory for arbitrary roles. :contentReference[oaicite:5]{index=5}
    """
    async def _dep(user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
        roles = user.get("roles", [])
        if not any(r in roles for r in required_roles):
            raise HTTPException(status_code=403, detail=f"User lacks required roles: {required_roles}")
        return user
    return _dep

# -----------------------------
# Auth endpoints (JSON bodies)
# -----------------------------
from pydantic import BaseModel, EmailStr

class TokenLoginRequest(BaseModel):
    token: str

class AdminLoginRequest(BaseModel):
    email: EmailStr
    password: str

@auth_router.post("/login", summary="User login (provide JWT)")
async def user_login(response: Response, token_data: TokenLoginRequest = Body(...)):
    # Validate + set cookie for browser UX (/docs, /admin)
    await jwt_verifier.decode(token_data.token.strip())
    set_auth_cookie(response, token_data.token.strip())
    return {"status": "ok"}

@auth_router.post("/logout", summary="User logout")
async def user_logout(response: Response):
    clear_auth_cookie(response)
    return {"status": "ok"}

@auth_router.post("/admin-login", summary="Admin login (email+password via LM or env fallback)")
async def admin_login(response: Response, login_data: AdminLoginRequest = Body(...)):
    email = login_data.email
    password = login_data.password
    if not password:
        raise HTTPException(status_code=400, detail="Password required")

    # --- Option A (prod): exchange with LM to get RS256 JWT (plug your LM call here) ---
    # lm_token = await exchange_with_lm(email, password)  # returns RS256 token with ROLE_SUPER_ADMIN
    # await jwt_verifier.decode(lm_token)
    # set_auth_cookie(response, lm_token)

    # --- Option B (local/dev fallback): accept env ADMIN_* and mint HS256 token ---
    admin_email = os.getenv("ADMIN_EMAIL", "admin@example.com")
    admin_password = os.getenv("ADMIN_PASSWORD", "admin123")
    if not (secrets.compare_digest(email, admin_email) and secrets.compare_digest(password, admin_password)):
        raise HTTPException(status_code=401, detail="Invalid admin credentials")

    # Create a small HS256 token for local usage
    import time
    payload = {
        "sub": email,
        "email": email,
        "roles": ["ROLE_SUPER_ADMIN"],
        "iss": jwt_verifier.issuer,
        "aud": os.getenv("ALLOWED_APP_CODES", "KWAS,KOA,DDN,FWH,KA").split(","),
        "iat": int(time.time()),
        "exp": int(time.time()) + int(os.getenv("ADMIN_TOKEN_TTL_SEC", "86400"))
    }
    hs_secret = os.getenv("JWT_SECRET_KEY")
    if not hs_secret:
        raise HTTPException(status_code=500, detail="JWT_SECRET_KEY must be set for HS256 admin dev login")
    token = jwt.encode(payload, hs_secret, algorithm="HS256")
    set_auth_cookie(response, token)

    # (legacy) clear old cookie name if present
    response.delete_cookie(key="admin_session", path="/", domain=_cookie_cfg()["domain"])
    return {"status": "ok", "roles": payload["roles"]}

@auth_router.post("/admin-logout", summary="Admin logout")
async def admin_logout(response: Response):
    clear_auth_cookie(response)
    return {"status": "ok"}

@auth_router.get("/status", summary="Authentication status")
async def auth_status(user: Dict[str, Any] = Depends(get_current_user)):
    return {"authenticated": True, "sub": user.get("sub"), "email": user.get("email"), "roles": user.get("roles", [])}

@auth_router.get("/roles", summary="Current roles (for UI)")
async def auth_roles(user: Dict[str, Any] = Depends(get_current_user)):
    return {"user_id": user.get("sub") or user.get("email"), "roles": user.get("roles", [])}
