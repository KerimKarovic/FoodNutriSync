from fastapi import HTTPException, Depends, Request, APIRouter, Response, Body
from fastapi.security import HTTPBearer
from starlette import status
import jwt
import os
import logging
from typing import Optional, Literal, Union
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa, ec, ed25519, ed448
import asyncio
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)
security = HTTPBearer(auto_error=False)

# Type alias for allowed public key types
AllowedPublicKeyTypes = Union[rsa.RSAPublicKey, ec.EllipticCurvePublicKey, ed25519.Ed25519PublicKey, ed448.Ed448PublicKey]

class JWTAuth:
    def __init__(self):
        self.algorithm = os.getenv("JWT_ALGORITHM", "RS256")
        self.issuer = os.getenv("LICENSEMANAGER_ISS")
        self.audience = os.getenv("LICENSEMANAGER_AUDIENCE")
        self.clock_skew = int(os.getenv("JWT_CLOCK_SKEW_SECONDS", "300"))
        self.refresh_interval = int(os.getenv("LM_JWKS_REFRESH_MINUTES", "1440"))
        
        # Key management
        self.public_key: Optional[AllowedPublicKeyTypes] = None
        self.last_refresh: Optional[datetime] = None
        self.refresh_task: Optional[asyncio.Task] = None
        self.key_type = "pem"
        
        self._load_pem_key()
    
    def _load_pem_key(self):
        """Load PEM key from environment variable"""
        pem_key = os.getenv("LICENSEMANAGER_PUBLIC_KEY_PEM")
        if pem_key:
            try:
                loaded_key = serialization.load_pem_public_key(pem_key.encode('utf-8'))
                
                if isinstance(loaded_key, (rsa.RSAPublicKey, ec.EllipticCurvePublicKey, ed25519.Ed25519PublicKey, ed448.Ed448PublicKey)):
                    self.public_key = loaded_key
                    self.last_refresh = datetime.now()
                    logger.info("Loaded static PEM key from environment")
                else:
                    logger.error(f"Unsupported key type: {type(loaded_key)}")
                    
            except Exception as e:
                logger.error(f"Failed to load PEM key: {e}")
    
    async def start_background_refresh(self):
        """Start background key refresh task"""
        if self.refresh_task is None:
            self.refresh_task = asyncio.create_task(self._background_refresh_loop())
            logger.info("Started background key refresh task")
    
    async def stop_background_refresh(self):
        """Stop background key refresh task"""
        if self.refresh_task:
            self.refresh_task.cancel()
            try:
                await self.refresh_task
            except asyncio.CancelledError:
                logger.info("Background refresh task cancelled")
            self.refresh_task = None
            logger.info("Stopped background key refresh task")
    
    async def _background_refresh_loop(self):
        """Background task to refresh keys periodically"""
        while True:
            try:
                await asyncio.sleep(self.refresh_interval * 60)
                logger.debug("Key refresh check - PEM key is static")
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in background refresh: {e}")
    
    def get_status(self) -> dict:
        """Get key management status"""
        next_refresh = None
        if self.last_refresh:
            next_refresh = (self.last_refresh + timedelta(minutes=self.refresh_interval)).isoformat()
        
        return {
            'key_loaded': self.public_key is not None,
            'key_type': self.key_type,
            'last_refresh': self.last_refresh.isoformat() if self.last_refresh else None,
            'next_refresh': next_refresh,
            'keys_count': 1 if self.public_key else 0,
            'refresh_interval_minutes': self.refresh_interval,
            'clock_skew_seconds': self.clock_skew
        }
    
    async def validate_token(self, token: str) -> dict:
        """Validate JWT token with PEM key"""
        try:
            # Development bypass
            if os.getenv("ENVIRONMENT") == "development":
                return {
                    "sub": "dev_user",
                    "roles": ["Admin", "BLS-Data-Reader"]
                }
            
            if not self.public_key:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Public key not available"
                )
            
            # Decode and validate JWT
            payload = jwt.decode(
                token,
                self.public_key,
                algorithms=[self.algorithm],
                issuer=self.issuer,
                audience=self.audience,
                leeway=self.clock_skew
            )
            
            return payload
            
        except jwt.ExpiredSignatureError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token has expired"
            )
        except jwt.InvalidTokenError as e:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token"
            )

# Global instance
jwt_auth = JWTAuth()

def extract_token_from_request(request: Request) -> Optional[str]:
    """Extract token from Authorization header or cookie"""
    # Try Authorization header first
    auth_header = request.headers.get("authorization")
    if auth_header and auth_header.startswith("Bearer "):
        return auth_header[7:]
    
    # Try cookie
    cookie_name = os.getenv("AUTH_COOKIE_NAME", "lm_token")
    return request.cookies.get(cookie_name)

async def get_current_user(request: Request):
    """Get current authenticated user"""
    # Development bypass
    if os.getenv("ENVIRONMENT") == "development":
        return {
            "user_id": "dev_user",
            "roles": ["Admin", "BLS-Data-Reader"],
            "email": "dev@example.com"
        }
    
    token = extract_token_from_request(request)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required"
        )
    
    payload = await jwt_auth.validate_token(token)
    user_id = payload.get("sub")
    user_roles = payload.get("roles", [])
    
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token"
        )
    
    return {
        "user_id": user_id,
        "roles": user_roles,
        "email": payload.get("email"),
        "customer_id": payload.get("customerId"),
        "customer_code": payload.get("customerCode")
    }

async def require_admin(current_user: dict = Depends(get_current_user)):
    """Require Admin role"""
    if os.getenv("ENVIRONMENT") == "development":
        return current_user
    
    user_roles = current_user.get("roles", [])
    admin_roles = os.getenv("ADMIN_ROLES", "Super-Admin,Admin").split(",")
    
    if not any(role in user_roles for role in admin_roles):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required"
        )
    return current_user

async def require_bls_reader(current_user: dict = Depends(get_current_user)):
    """Require BLS-Data-Reader role or higher"""
    if os.getenv("ENVIRONMENT") == "development":
        return current_user
    
    user_roles = current_user.get("roles", [])
    user_roles_allowed = os.getenv("USER_ROLES", "BLS-Data-Reader,User").split(",")
    admin_roles_allowed = os.getenv("ADMIN_ROLES", "Super-Admin,Admin").split(",")
    allowed_roles = user_roles_allowed + admin_roles_allowed
    
    if not any(role in user_roles for role in allowed_roles):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="BLS-Data-Reader role required"
        )
    return current_user

def get_client_ip(request: Request) -> str:
    """Extract client IP"""
    fwd = request.headers.get("x-forwarded-for")
    return fwd.split(",")[0].strip() if fwd else (request.client.host if request.client else "unknown")

# Auth router
router = APIRouter()

@router.post("/auth/login")
async def login(
    request: Request,
    response: Response,
    token_data: dict = Body(...)
):
    """Login endpoint - validates JWT and sets cookie"""
    jwt_token = token_data.get("token", "").strip()
    
    if not jwt_token:
        raise HTTPException(status_code=400, detail="JWT token required")
    
    # Validate token
    payload = await jwt_auth.validate_token(jwt_token)
    user_id = payload.get("sub")
    
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token")
    
    # Set cookie with proper type
    cookie_name = os.getenv("AUTH_COOKIE_NAME", "lm_token")
    samesite_value = os.getenv("AUTH_COOKIE_SAMESITE", "strict").lower()
    
    # Ensure samesite is a valid literal
    samesite: Literal["strict", "lax", "none"] = "strict"
    if samesite_value in ["strict", "lax", "none"]:
        samesite = samesite_value  # type: ignore
    
    response.set_cookie(
        key=cookie_name,
        value=jwt_token,
        httponly=True,
        secure=os.getenv("ENVIRONMENT") == "production",
        samesite=samesite,
        max_age=24 * 60 * 60,
        path="/"
    )
    
    logger.info(f"User login: {user_id}")
    
    return {
        "status": "success",
        "user": {
            "user_id": user_id,
            "roles": payload.get("roles", [])
        }
    }

@router.post("/auth/logout")
async def logout(request: Request, response: Response):
    """Logout endpoint"""
    cookie_name = os.getenv("AUTH_COOKIE_NAME", "lm_token")
    response.delete_cookie(key=cookie_name, path="/")
    
    logger.info("User logout")
    return {"status": "success"}

@router.get("/auth/status")
async def auth_status(current_user: dict = Depends(get_current_user)):
    """Get auth status"""
    return {
        "authenticated": True,
        "user": {
            "user_id": current_user.get("user_id"),
            "roles": current_user.get("roles", [])
        }
    }
