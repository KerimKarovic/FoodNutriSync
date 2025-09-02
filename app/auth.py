import asyncio
from datetime import datetime
from fastapi import HTTPException, Depends, Request, APIRouter, Response, Body, Security
from fastapi.security import HTTPBasic, HTTPBasicCredentials, HTTPBearer
from starlette import status
import jwt
import os
import logging
from typing import Optional, Literal, Union
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa, ec, ed25519, ed448
import secrets

logger = logging.getLogger(__name__)
security = HTTPBearer(auto_error=False)
bearer_scheme = HTTPBearer(auto_error=False, scheme_name="BearerAuth")

# Add docs-only bearer scheme
docs_bearer = HTTPBearer(auto_error=False, scheme_name="BearerAuth")

# Add basic auth for admin endpoints
admin_basic_auth = HTTPBasic()

def verify_admin_credentials(credentials: HTTPBasicCredentials = Depends(admin_basic_auth)):
    """Verify admin email/password"""
    admin_email = os.getenv("ADMIN_EMAIL", "admin@example.com")
    admin_password = os.getenv("ADMIN_PASSWORD", "admin123")
    
    is_correct_email = secrets.compare_digest(credentials.username, admin_email)
    is_correct_password = secrets.compare_digest(credentials.password, admin_password)
    
    if not (is_correct_email and is_correct_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid admin credentials",
            headers={"WWW-Authenticate": "Basic"},
        )
    
    return {"user_id": credentials.username, "roles": ["Admin"]}

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
    
    def get_status(self) -> dict:
        """Get JWT auth status"""
        return {
            "key_loaded": self.public_key is not None,
            "key_type": self.key_type,
            "last_refresh": self.last_refresh.isoformat() if self.last_refresh else None,
            "algorithm": self.algorithm,
            "issuer": self.issuer,
            "audience": self.audience
        }
    
    async def validate_token(self, token: str) -> dict:
        """Validate JWT token with PEM key"""
        try:
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
    """Extract JWT token from request (cookie or Authorization header)"""
    # First try Authorization header (for Swagger UI)
    auth_header = request.headers.get("authorization")
    if auth_header and auth_header.startswith("Bearer "):
        return auth_header[7:]  # Remove "Bearer " prefix
    
    # Fallback to cookie (for web UI)
    cookie_name = os.getenv("AUTH_COOKIE_NAME", "lm_token")
    return request.cookies.get(cookie_name)

async def get_current_user(request: Request):
    """Get current user from JWT token"""
    # Bypass auth in test environment
    if os.getenv("TESTING") == "1" or os.getenv("ENVIRONMENT") == "development":
        return {
            "user_id": "test_user",
            "roles": ["Admin", "BLS-Data-Reader"],
            "email": "test@example.com"
        }
    
    # Extract token from either Authorization header or cookie
    token = extract_token_from_request(request)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required"
        )
    
    payload = await jwt_auth.validate_token(token)
    user_id = payload.get("sub")
    
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token"
        )
    
    # Log the authentication for debugging
    logger.info(f"User authenticated: {user_id} via {'header' if request.headers.get('authorization') else 'cookie'}")
    
    return {
        "user_id": user_id,
        "roles": payload.get("roles", []),
        "email": payload.get("email"),
        "customer_id": payload.get("customerId"),
        "customer_code": payload.get("customerCode")
    }

async def require_admin(current_user: dict = Depends(get_current_user)):
    """Require Super-Admin role - ONLY for admin functions (upload/management)"""
    user_roles = current_user.get("roles", [])
    
    # Only super admin roles allowed for admin functions
    super_admin_roles = ["ROLE_SUPER_ADMIN", "Super-Admin", "Admin"]
    
    if not any(role in user_roles for role in super_admin_roles):
        logger.warning(f"Admin access denied - User: {current_user.get('user_id')}, Roles: {user_roles}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Super-Admin role required for admin functions. Current roles: {user_roles}"
        )
    
    logger.info(f"Admin access granted - User: {current_user.get('user_id')}, Roles: {user_roles}")
    return current_user

async def require_bls_reader(current_user: dict = Depends(get_current_user)):
    """Require integration role - for GET endpoints (data access)"""
    user_roles = current_user.get("roles", [])
    
    # Integration roles for data access
    integration_roles = ["ROLE_INTEGRATION"]
    
    # Super admin also gets data access
    admin_roles = ["ROLE_SUPER_ADMIN", "Super-Admin", "Admin"]
    
    allowed_roles = integration_roles + admin_roles
    
    if not any(role in user_roles for role in allowed_roles):
        logger.warning(f"BLS access denied - User: {current_user.get('user_id')}, Roles: {user_roles}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"ROLE_INTEGRATION required for data access. Current roles: {user_roles}"
        )
    
    logger.info(f"BLS access granted - User: {current_user.get('user_id')}, Roles: {user_roles}")
    return current_user

# Auth router
router = APIRouter()

@router.post("/auth/login", 
            summary="User login", 
            description="Authenticate user with JWT token and establish secure session cookie")
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

@router.post("/auth/logout", 
            summary="User logout", 
            description="Clear authentication session and remove secure cookies from browser")
async def logout(request: Request, response: Response):
    """Logout endpoint"""
    cookie_name = os.getenv("AUTH_COOKIE_NAME", "lm_token")
    
    # Clear cookie with multiple configurations to ensure it's removed
    response.delete_cookie(key=cookie_name, path="/")
    response.delete_cookie(key=cookie_name, path="/", domain=None)
    response.delete_cookie(key=cookie_name, path="/", secure=False)
    response.delete_cookie(key=cookie_name, path="/", httponly=True)
    
    logger.info("User logout - JWT cookie cleared")
    return {"status": "success"}

@router.get("/auth/status", 
            summary="Authentication status",
            dependencies=[Security(docs_bearer)])
async def auth_status(current_user: dict = Depends(get_current_user)):
    """Get auth status"""
    return {
        "authenticated": True,
        "user": {
            "user_id": current_user.get("user_id"),
            "roles": current_user.get("roles", [])
        }
    }

@router.post("/auth/admin-login", 
            summary="Admin login", 
            description="Authenticate admin with email/password")
async def admin_login(
    request: Request,
    response: Response,
    login_data: dict = Body(...)
):
    """Admin login endpoint - validates credentials"""
    email = login_data.get("email", "").strip()
    password = login_data.get("password", "").strip()
    
    if not email or not password:
        raise HTTPException(status_code=400, detail="Email and password required")
    
    # Verify admin credentials
    admin_email = os.getenv("ADMIN_EMAIL", "admin@example.com")
    admin_password = os.getenv("ADMIN_PASSWORD", "admin123")
    
    is_correct_email = secrets.compare_digest(email, admin_email)
    is_correct_password = secrets.compare_digest(password, admin_password)
    
    if not (is_correct_email and is_correct_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid admin credentials"
        )
    
    # Set admin session cookie
    response.set_cookie(
        key="admin_session",
        value=f"admin:{email}",
        httponly=True,
        secure=os.getenv("ENVIRONMENT") == "production",
        samesite="strict",
        max_age=24 * 60 * 60,
        path="/"
    )
    
    logger.info(f"Admin login: {email}")
    
    return {
        "status": "success",
        "user": {
            "user_id": email,
            "roles": ["Admin"]
        }
    }

@router.post("/auth/admin-logout", 
            summary="Admin logout", 
            description="Clear admin session and redirect to login")
async def admin_logout(request: Request, response: Response):
    """Admin logout endpoint - clears admin session"""
    # Clear admin session cookie with multiple configurations
    response.delete_cookie(key="admin_session", path="/")
    response.delete_cookie(key="admin_session", path="/", domain=None)
    response.delete_cookie(key="admin_session", path="/", secure=False)
    response.delete_cookie(key="admin_session", path="/", httponly=True)
    
    # Also clear JWT cookie
    cookie_name = os.getenv("AUTH_COOKIE_NAME", "lm_token")
    response.delete_cookie(key=cookie_name, path="/")
    response.delete_cookie(key=cookie_name, path="/", domain=None)
    response.delete_cookie(key=cookie_name, path="/", secure=False)
    response.delete_cookie(key=cookie_name, path="/", httponly=True)
    
    logger.info("Admin logout - all cookies cleared")
    
    return {
        "status": "success",
        "message": "Admin session cleared",
        "redirect": "/login"
    }
