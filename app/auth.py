from __future__ import annotations

import os
import time
import secrets
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Request, Response, status
from fastapi.security import HTTPBearer
import jwt  # PyJWT

logger = logging.getLogger(__name__)

auth_router = APIRouter()
bearer = HTTPBearer(auto_error=False)  # used by Swagger & manual Authorization header

# -----------------------------
# Cookie helpers (single source)
# -----------------------------
def _cookie_cfg() -> Dict[str, Any]:
    return {
        "name": os.getenv("AUTH_COOKIE_NAME", "lm_token"),
        "domain": os.getenv("AUTH_COOKIE_DOMAIN") or None,
        "path": os.getenv("AUTH_COOKIE_PATH", "/"),
        "max_age": int(os.getenv("AUTH_COOKIE_MAX_AGE_SECONDS", "86400")),
        "samesite": os.getenv("AUTH_COOKIE_SAMESITE", "strict").lower(),  # strict/lax/none
        "secure": (os.getenv("AUTH_COOKIE_SAMESITE", "strict").lower() == "none")
                  or (os.getenv("ENVIRONMENT", "development").lower() == "production"),
        "httponly": True,
    }

def set_auth_cookie(response: Response, token: str) -> None:
    cfg = _cookie_cfg()
    response.set_cookie(
        key=cfg["name"],
        value=token,
        max_age=cfg["max_age"],
        path=cfg["path"],
        domain=cfg["domain"],
        secure=cfg["secure"],
        httponly=cfg["httponly"],
        samesite=cfg["samesite"],
    )

def clear_auth_cookie(response: Response) -> None:
    cfg = _cookie_cfg()
    response.delete_cookie(key=cfg["name"], path=cfg["path"], domain=cfg["domain"])
    # legacy cleanup (if it ever existed)
    response.delete_cookie(key="admin_session", path="/", domain=cfg["domain"])

# -----------------------------
# JWT verification (HS256 local / RS256 prod)
# -----------------------------
class JWTVerifier:
    def __init__(self) -> None:
        self.issuer = os.getenv("LICENSEMANAGER_ISS", "LM_AUTH")
        self.clock_skew = int(os.getenv("JWT_CLOCK_SKEW_SECONDS", "300"))
        self.exp_leeway = int(os.getenv("JWT_EXP_LEEWAY_SECONDS", "900"))  # extra tolerance
        self._public_key_pem: Optional[bytes] = None

    def _allowed_audiences(self) -> List[str]:
        raw = os.getenv("ALLOWED_APP_CODES", "KWAS,KOA,DDN,FWH,KA")
        return [x.strip() for x in raw.split(",") if x.strip()]

    def _validate_aud(self, payload: Dict[str, Any]) -> None:
        aud = payload.get("aud")
        if not aud:
            raise HTTPException(403, "Token missing audience")
        token_aud = [aud] if isinstance(aud, str) else list(aud)
        if not any(a in self._allowed_audiences() for a in token_aud):
            raise HTTPException(403, f"Invalid audience {token_aud}")

    async def _get_public_pem(self) -> bytes:
        if self._public_key_pem is not None:
            return self._public_key_pem
        pem = os.getenv("LICENSEMANAGER_PUBLIC_KEY_PEM")
        if pem:
            self._public_key_pem = pem.encode("utf-8")
            return self._public_key_pem
        url = os.getenv("LICENSEMANAGER_PUBLIC_KEY_URL")
        if not url:
            raise RuntimeError("Set LICENSEMANAGER_PUBLIC_KEY_PEM or LICENSEMANAGER_PUBLIC_KEY_URL")
        import urllib.request
        with urllib.request.urlopen(url, timeout=10) as r:
            self._public_key_pem = r.read()
        if self._public_key_pem is None:
            raise RuntimeError("Failed to retrieve public key")
        return self._public_key_pem

    async def decode(self, token: str) -> Dict[str, Any]:
        # choose key by alg header
        try:
            header = jwt.get_unverified_header(token)
            alg = header.get("alg")
        except Exception:
            raise HTTPException(401, "Invalid token header")

        if alg == "HS256":
            key = os.getenv("JWT_SECRET_KEY") or os.getenv("DEV_JWT_SECRET_KEY") or "dev-secret"
            if not key:
                raise HTTPException(500, "HS256 used but JWT_SECRET_KEY not set")
            algorithms = ["HS256"]
        elif alg == "RS256":
            key = await self._get_public_pem()  # PyJWT accepts PEM bytes
            algorithms = ["RS256"]
        else:
            raise HTTPException(403, f"Unsupported algorithm {alg}")

        # decode w/o exp/aud → do our own checks (clear messages + extra leeway)
        payload = jwt.decode(
            token,
            key=key,
            algorithms=algorithms,
            issuer=self.issuer,
            options={"verify_aud": False, "verify_exp": False},
            leeway=self.clock_skew,
        )
        self._validate_aud(payload)

        now = int(time.time())
        exp = payload.get("exp")
        if isinstance(exp, (int, float)) and now > int(exp) + self.exp_leeway:
            raise HTTPException(401, "Token expired")

        roles = payload.get("roles") or []
        if not isinstance(roles, list):
            roles = [roles]
        payload["roles"] = roles
        return payload

jwt_verifier = JWTVerifier()

# -----------------------------
# Token extractors
# -----------------------------
def _token_from_header(request: Request) -> Optional[str]:
    auth = request.headers.get("Authorization")
    if auth and auth.lower().startswith("bearer "):
        return auth.split(" ", 1)[1].strip()
    return None

def _token_from_cookie(request: Request) -> Optional[str]:
    return request.cookies.get(_cookie_cfg()["name"])

# -----------------------------
# Current user + role guards
# -----------------------------
async def get_current_user(request: Request) -> Dict[str, Any]:
    """
    General auth for READ endpoints: accept Bearer header or cookie.
    """
    token = _token_from_header(request) or _token_from_cookie(request)
    if not token:
        raise HTTPException(401, "Missing token")
    return await jwt_verifier.decode(token)

def _is_admin(roles: List[str]) -> bool:
    return any(r in {"ROLE_SUPER_ADMIN", "Super-Admin", "Admin", "ROLE_ADMIN"} for r in roles)

def _is_reader(roles: List[str]) -> bool:
    return "ROLE_INTEGRATION" in roles or _is_admin(roles)

# NEW: runtime-looked-up wrappers for test patching
async def _dep_current_user(request: Request):
    # resolves get_current_user at call time (works with test patching)
    return await get_current_user(request)

async def _dep_current_admin_cookie(request: Request):
    return await get_current_admin_cookie(request)

async def require_bls_reader(user: Dict[str, Any] = Depends(_dep_current_user)) -> Dict[str, Any]:
    """
    Integration (ROLE_INTEGRATION) or Admin may read.
    """
    if not _is_reader(user.get("roles", [])):
        raise HTTPException(403, "BLS read permission required")
    return user

# ---- NEW: admin must come from COOKIE ONLY ----
async def get_current_admin_cookie(request: Request) -> Dict[str, Any]:
    """
    Admin auth for WRITE/ADMIN endpoints: **cookie only**.
    This prevents Swagger's Bearer token from unlocking admin routes.
    """
    token = _token_from_cookie(request)
    if not token:
        # differentiate "no admin cookie" from generic 401 to help the UI redirect to /login
        raise HTTPException(status_code=401, detail="Missing admin session")
    payload = await jwt_verifier.decode(token)
    if not _is_admin(payload.get("roles", [])):
        raise HTTPException(status_code=403, detail="Admin role required")
    return payload

async def require_admin_cookie(user: Dict[str, Any] = Depends(_dep_current_admin_cookie)) -> Dict[str, Any]:
    return user

# -----------------------------
# Auth endpoints (JSON bodies)
# -----------------------------
from pydantic import BaseModel

class TokenLoginRequest(BaseModel):
    token: str

class AdminLoginRequest(BaseModel):
    email: str
    password: str

@auth_router.post("/login", summary="User login (provide JWT)")
async def user_login(response: Response, token_data: TokenLoginRequest = Body(...)):
    token = token_data.token.strip()
    try:
        await jwt_verifier.decode(token)  # validate
    except Exception as e:
        # tests sometimes raise plain Exception from mocked decode
        raise HTTPException(status_code=401, detail=str(e) or "Invalid token")
    set_auth_cookie(response, token)  # store for browser/UI
    return {"status": "ok"}

@auth_router.post("/logout", summary="User logout")
async def user_logout(response: Response):
    clear_auth_cookie(response)
    return {"status": "ok"}

@auth_router.post("/admin-login", summary="Admin login (email+password → LM JWT or dev HS256)")
async def admin_login(response: Response, login_data: AdminLoginRequest = Body(...)):
    email = login_data.email.strip()
    password = login_data.password

    # PROD: swap email+password for LM JWT here (RS256 w/ ROLE_SUPER_ADMIN)
    # lm_token = await exchange_with_lm(email, password)
    # await jwt_verifier.decode(lm_token)
    # set_auth_cookie(response, lm_token)
    # return {"status": "ok"}

    # DEV/local fallback
    admin_email = os.getenv("ADMIN_EMAIL", "admin@example.com")
    admin_password = os.getenv("ADMIN_PASSWORD", "admin123")
    if not (secrets.compare_digest(email, admin_email) and secrets.compare_digest(password, admin_password)):
        raise HTTPException(401, "Invalid admin credentials")

    secret = os.getenv("JWT_SECRET_KEY") or os.getenv("DEV_JWT_SECRET_KEY") or "dev-secret"
    if not secret:
        raise HTTPException(500, "JWT_SECRET_KEY must be set for HS256 dev admin login")
    now = int(time.time())
    payload = {
        "sub": email, "email": email, "roles": ["ROLE_SUPER_ADMIN"],
        "iss": jwt_verifier.issuer, "aud": jwt_verifier._allowed_audiences(),
        "iat": now, "exp": now + int(os.getenv("ADMIN_TOKEN_TTL_SEC", "86400")),
    }
    token = jwt.encode(payload, secret, algorithm="HS256")
    set_auth_cookie(response, token)
    # remove any legacy cookie name
    response.delete_cookie(key="admin_session", path="/", domain=_cookie_cfg()["domain"])
    return {"status": "ok", "roles": ["ROLE_SUPER_ADMIN"]}

@auth_router.post("/admin-logout", summary="Admin logout")
async def admin_logout(response: Response):
    clear_auth_cookie(response)
    return {"status": "ok"}

@auth_router.get("/status", summary="Auth status")
async def auth_status(user: Dict[str, Any] = Depends(get_current_user)):
    return {"authenticated": True, "sub": user.get("sub"), "email": user.get("email"), "roles": user.get("roles", [])}

@auth_router.get("/roles", summary="Current roles (for UI)")
async def auth_roles(user: Dict[str, Any] = Depends(get_current_user)):
    return {"user_id": user.get("sub") or user.get("email"), "roles": user.get("roles", [])}
