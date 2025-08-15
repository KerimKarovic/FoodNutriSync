import jwt
import httpx
from fastapi import HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional, List
import os
from datetime import datetime


security = HTTPBearer(auto_error=False)

class JWTAuth:
    def __init__(self):
        self.public_key_url = os.getenv("LICENSEMANAGER_PUBLIC_KEY_URL")
        self.issuer = os.getenv("LICENSEMANAGER_ISSUER")
        self.algorithm = os.getenv("JWT_ALGORITHM", "RS256")
        self.allowed_roles = os.getenv("ALLOWED_ROLES", "").split(",") if os.getenv("ALLOWED_ROLES") else []
        self._public_key = None
        self._key_last_fetched = None
    
    async def get_public_key(self) -> str:
        """Fetch and cache public key from LicenseManager"""
        if not self.public_key_url:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="LICENSEMANAGER_PUBLIC_KEY_URL not configured"
            )
            
        # Cache key for 1 hour
        if (self._public_key and self._key_last_fetched and 
            (datetime.now() - self._key_last_fetched).seconds < 3600):
            return self._public_key
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(self.public_key_url)
                response.raise_for_status()
                self._public_key = response.text
                self._key_last_fetched = datetime.now()
                return self._public_key
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Unable to fetch public key: {str(e)}"
            )
    
    async def validate_token(self, token: str) -> dict:
        """Validate JWT token and return payload"""
        try:
            public_key = await self.get_public_key()
            
            # Decode and validate JWT
            payload = jwt.decode(
                token,
                public_key,
                algorithms=[self.algorithm],
                issuer=self.issuer
            )
            
            return payload
            
        except jwt.ExpiredSignatureError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token has expired"
            )
        except jwt.InvalidTokenError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token"
            )
    
    def check_role_permission(self, user_roles: List[str], required_roles: Optional[List[str]] = None) -> bool:
        """Check if user has required role"""
        if required_roles is None:
            required_roles = self.allowed_roles
        
        return any(role in required_roles for role in user_roles)

jwt_auth = JWTAuth()

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Dependency to get current authenticated user"""
    # Development bypass for local testing
    if os.getenv("ENVIRONMENT") == "development":
        return {
            "user_id": "dev_admin",
            "roles": ["Admin", "BLS-Data-Reader"],
            "payload": {"sub": "dev_admin", "roles": ["Admin", "BLS-Data-Reader"]}
        }
    
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required"
        )
    
    token = credentials.credentials
    payload = await jwt_auth.validate_token(token)
    
    # Extract user info from payload
    user_id = payload.get("sub")
    user_roles = payload.get("roles", [])
    
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload"
        )
    
    # Check if user has allowed role
    if not jwt_auth.check_role_permission(user_roles):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions"
        )
    
    return {
        "user_id": user_id,
        "roles": user_roles,
        "payload": payload
    }

# Optional: Role-specific dependencies
async def require_admin(current_user: dict = Depends(get_current_user)):
    """Require admin role"""
    # Development bypass
    if os.getenv("ENVIRONMENT") == "development":
        return {
            "user_id": "dev_admin",
            "roles": ["Admin", "BLS-Data-Reader"],
            "payload": {"sub": "dev_admin", "roles": ["Admin", "BLS-Data-Reader"]}
        }
    
    if "Admin" not in current_user["roles"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required"
        )
    return current_user
