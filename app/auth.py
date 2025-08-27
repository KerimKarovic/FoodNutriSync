import jwt
import httpx
import asyncio
from fastapi import HTTPException, status, Depends, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional, List, Dict, Any
import os
from datetime import datetime, timedelta
import json
import logging

logger = logging.getLogger("foodnutrisync.auth")
security = HTTPBearer(auto_error=False)

class JWTAuth:
    def __init__(self):
        self.public_key_url = os.getenv("LICENSEMANAGER_PUBLIC_KEY_URL")
        self.issuer = os.getenv("LICENSEMANAGER_ISS")
        self.audience = os.getenv("LICENSEMANAGER_AUDIENCE")
        self.algorithm = os.getenv("JWT_ALGORITHM", "RS256")
        self.clock_skew = int(os.getenv("JWT_CLOCK_SKEW_SECONDS", "300"))
        self.refresh_minutes = int(os.getenv("LM_JWKS_REFRESH_MINUTES", "1440"))
        self.cookie_name = os.getenv("AUTH_COOKIE_NAME", "lm_token")
        
        # Key storage
        self._keys: Dict[str, str] = {}  # kid -> key mapping for JWKS
        self._single_key: Optional[str] = None  # For single PEM
        self._key_type: Optional[str] = None  # "jwks", "pem", or "development"
        self._last_refresh: Optional[datetime] = None
        self._refresh_task: Optional[asyncio.Task] = None
        self._retry_attempted: bool = False
    
    async def start_background_refresh(self):
        """Start background key refresh task"""
        if self._refresh_task is None or self._refresh_task.done():
            self._refresh_task = asyncio.create_task(self._background_refresh_loop())
            logger.info("Started background key refresh task")
    
    async def stop_background_refresh(self):
        """Stop background key refresh task"""
        if self._refresh_task and not self._refresh_task.done():
            self._refresh_task.cancel()
            try:
                await self._refresh_task
            except asyncio.CancelledError:
                pass
            logger.info("Stopped background key refresh task")
    
    async def _background_refresh_loop(self):
        """Background task for periodic key refresh"""
        while True:
            try:
                await asyncio.sleep(self.refresh_minutes * 60)
                await self._fetch_keys()
                logger.info("Background key refresh completed successfully")
            except asyncio.CancelledError:
                logger.info("Background refresh task cancelled")
                break
            except Exception as e:
                logger.error(f"Background key refresh failed: {e}")
                # Continue the loop even on errors
    
    async def get_keys_with_retry(self, kid: Optional[str] = None) -> str:
        """Get key with refresh-then-retry logic"""
        # Try to get key from cache first
        key = self._get_cached_key(kid)
        if key:
            return key
        
        # Key not found or cache empty - refresh and retry once
        logger.info(f"Key not found (kid: {kid}), refreshing keys...")
        await self._fetch_keys()
        
        key = self._get_cached_key(kid)
        if not key:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Public key not available after refresh (kid: {kid})"
            )
        
        return key
    
    def _get_cached_key(self, kid: Optional[str] = None) -> Optional[str]:
        """Get key from cache based on key type and kid"""
        if self._key_type == "jwks":
            if kid and kid in self._keys:
                return self._keys[kid]
            elif not kid and self._keys:
                # Return first available key if no kid specified
                return next(iter(self._keys.values()))
        elif self._key_type in ["pem", "development"]:
            return self._single_key
        return None
    
    async def _fetch_keys(self) -> None:
        """Fetch keys from License Manager with static key support"""
        
        # Try static PEM key first
        static_pem = os.getenv("LICENSEMANAGER_PUBLIC_KEY_PEM")
        if static_pem:
            self._single_key = static_pem.strip()
            self._key_type = "pem"
            self._last_refresh = datetime.now()
            logger.info("Loaded static PEM key from environment")
            return
        
        # Original URL logic continues...
        if not self.public_key_url:
            if os.getenv("ENVIRONMENT") == "development":
                logger.warning("No public key configured - using development mode")
                self._single_key = "development_mode"
                self._key_type = "development"
                self._last_refresh = datetime.now()
                return
            else:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="No public key configured"
                )
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(self.public_key_url)
                response.raise_for_status()
                
                content = response.text.strip()
                
                # Detect if it's JWKS or PEM
                if content.startswith('{'):
                    # JWKS format
                    await self._parse_jwks(content)
                    self._key_type = "jwks"
                    logger.info(f"Loaded JWKS with {len(self._keys)} keys")
                else:
                    # PEM format
                    self._single_key = content
                    self._key_type = "pem"
                    logger.info("Loaded single PEM key")
                
                self._last_refresh = datetime.now()
                
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.error(f"License Manager endpoint not found: {self.public_key_url}")
                logger.error("Please check the LICENSEMANAGER_PUBLIC_KEY_URL configuration")
                
                # In development, continue without keys
                if os.getenv("ENVIRONMENT") == "development":
                    logger.warning("Continuing in development mode without License Manager")
                    self._single_key = "development_mode"
                    self._key_type = "development"
                    self._last_refresh = datetime.now()
                    return
                else:
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail=f"License Manager endpoint not found: {self.public_key_url}"
                    )
            else:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"License Manager error: {e.response.status_code}"
                )
        except httpx.RequestError as e:
            logger.error(f"Failed to fetch public key: {e}")
            
            # In development, continue without keys
            if os.getenv("ENVIRONMENT") == "development":
                logger.warning("Network error - continuing in development mode")
                self._single_key = "development_mode"
                self._key_type = "development"
                self._last_refresh = datetime.now()
                return
            else:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Cannot reach License Manager: {e}"
                )
        except Exception as e:
            logger.error(f"Key parsing failed: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Invalid key format: {e}"
            )
    
    async def _parse_jwks(self, jwks_content: str) -> None:
        """Parse JWKS and extract keys"""
        try:
            jwks = json.loads(jwks_content)
            keys = jwks.get("keys", [])
            
            self._keys.clear()
            
            for key_data in keys:
                kid = key_data.get("kid")
                if not kid:
                    continue
                
                # Convert JWK to PEM (simplified - you might need python-jose for full JWK support)
                # For now, assume the JWKS contains PEM in 'x5c' or similar
                if "x5c" in key_data and key_data["x5c"]:
                    # X.509 certificate chain
                    cert = key_data["x5c"][0]
                    pem_key = f"-----BEGIN CERTIFICATE-----\n{cert}\n-----END CERTIFICATE-----"
                    self._keys[kid] = pem_key
                
        except Exception as e:
            raise ValueError(f"Invalid JWKS format: {e}")
    
    async def validate_token(self, token: str) -> dict:
        """Enhanced JWT token validation with comprehensive checks"""
        try:
            # Development mode bypass
            if os.getenv("ENVIRONMENT") == "development" and self._key_type == "development":
                logger.warning("Development mode - bypassing JWT validation")
                return {
                    "sub": "dev_user",
                    "roles": ["Admin", "BLS-Data-Reader", "Integration"],
                    "exp": 9999999999
                }
            
            # Decode header to get kid and algorithm
            unverified_header = jwt.get_unverified_header(token)
            kid = unverified_header.get("kid")
            alg = unverified_header.get("alg")
            
            # Enforce algorithm allowlist - CRITICAL SECURITY
            allowed_algorithms = ["RS256"]
            if alg not in allowed_algorithms:
                logger.warning(f"Rejected token with unsupported algorithm: {alg}")
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail=f"Unsupported algorithm: {alg}. Only {allowed_algorithms} allowed."
                )
            
            # Get appropriate key with retry logic
            public_key = await self.get_keys_with_retry(kid)
            
            # Enhanced validation options
            options = {
                "verify_signature": True,
                "verify_exp": True,
                "verify_nbf": True,
                "verify_iat": True,
                "verify_aud": bool(self.audience),
                "verify_iss": bool(self.issuer),
                "require_exp": True,
                "require_iat": True,
                "require_nbf": False,  # Not all tokens have nbf
            }
            
            # Decode and validate JWT with all checks
            payload = jwt.decode(
                token,
                public_key,
                algorithms=["RS256"],
                issuer=self.issuer if self.issuer else None,
                audience=self.audience if self.audience else None,
                options=options,
                leeway=timedelta(seconds=self.clock_skew)
            )
            
            # Additional payload validation
            if not payload.get("sub"):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Token missing required 'sub' claim"
                )
            
            logger.debug(f"Token validated successfully for user: {payload.get('sub')}")
            return payload
            
        except jwt.ExpiredSignatureError:
            logger.warning("Token validation failed: expired signature")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token has expired"
            )
        except jwt.InvalidIssuerError:
            logger.warning(f"Token validation failed: invalid issuer")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token issuer"
            )
        except jwt.InvalidAudienceError:
            logger.warning(f"Token validation failed: invalid audience")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token audience"
            )
        except jwt.InvalidSignatureError as e:
            # Implement refresh-then-retry logic for signature errors
            if not self._retry_attempted:
                logger.info("Signature validation failed, attempting key refresh...")
                self._retry_attempted = True
                try:
                    await self._fetch_keys()
                    # Retry validation once with fresh keys
                    public_key = await self.get_keys_with_retry(kid)
                    payload = jwt.decode(
                        token,
                        public_key,
                        algorithms=["RS256"],
                        issuer=self.issuer if self.issuer else None,
                        audience=self.audience if self.audience else None,
                        options=options,
                        leeway=timedelta(seconds=self.clock_skew)
                    )
                    self._retry_attempted = False
                    logger.info("Token validated successfully after key refresh")
                    return payload
                except Exception as retry_error:
                    self._retry_attempted = False
                    logger.error(f"Token validation failed even after key refresh: {retry_error}")
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="Invalid token signature"
                    )
            else:
                self._retry_attempted = False
                logger.warning("Token validation failed: invalid signature (after retry)")
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid token signature"
                )
        except jwt.InvalidTokenError as e:
            logger.warning(f"Token validation failed: {e}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Invalid token: {e}"
            )
        except Exception as e:
            logger.error(f"Unexpected error during token validation: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Token validation error"
            )
        finally:
            # Reset retry flag
            self._retry_attempted = False
    
    def get_health_status(self) -> dict:
        """Get comprehensive key management health status"""
        return {
            "key_loaded": bool(self._keys or self._single_key),
            "key_type": self._key_type,
            "last_refresh": self._last_refresh.isoformat() if self._last_refresh else None,
            "next_refresh": (self._last_refresh + timedelta(minutes=self.refresh_minutes)).isoformat() 
                        if self._last_refresh else None,
            "keys_count": len(self._keys) if self._key_type == "jwks" else (1 if self._single_key else 0),
            "refresh_interval_minutes": self.refresh_minutes,
            "clock_skew_seconds": self.clock_skew
        }

# Global instance
jwt_auth = JWTAuth()

def extract_token_from_request(request: Request) -> Optional[str]:
    """Enhanced token extraction: Cookie-first, then Authorization header"""
    # Try cookie first (for admin UI) - more secure
    cookie_name = os.getenv("AUTH_COOKIE_NAME", "lm_token")
    token = request.cookies.get(cookie_name)
    
    if token:
        logger.debug("Token extracted from cookie")
        return token
    
    # Fallback to Authorization header (for ERP/API clients)
    auth_header = request.headers.get("authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header[7:]  # Remove "Bearer " prefix
        logger.debug("Token extracted from Authorization header")
        return token
    
    logger.debug("No token found in cookie or Authorization header")
    return None

async def get_current_user(request: Request):
    """Enhanced dependency to get current authenticated user"""
    # Development bypass
    if os.getenv("ENVIRONMENT") == "development":
        return {
            "user_id": "dev_user",
            "roles": ["Integration", "BLS-Data-Reader", "Admin", "Super Admin"],
            "payload": {"sub": "dev_user", "roles": ["Integration", "BLS-Data-Reader", "Admin", "Super Admin"]}
        }
    
    # Extract token from cookie or header
    token = extract_token_from_request(request)
    
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required"
        )
    
    # Validate token
    payload = await jwt_auth.validate_token(token)
    
    # Extract user info
    user_id = payload.get("sub")
    user_roles = payload.get("roles", [])
    
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload"
        )
    
    return {
        "user_id": user_id,
        "roles": user_roles,
        "payload": payload
    }

def require_role(required_role: str):
    """Generic role validation dependency factory"""
    async def role_dependency(current_user: dict = Depends(get_current_user)):
        # Development bypass
        if os.getenv("ENVIRONMENT") == "development":
            return current_user
        
        user_roles = current_user.get("roles", [])
        
        if required_role not in user_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{required_role}' required"
            )
        
        return current_user
    
    return role_dependency

# Updated role-specific dependencies
async def require_admin(current_user: dict = Depends(get_current_user)):
    """Require Admin or Super Admin role"""
    if os.getenv("ENVIRONMENT") == "development":
        return current_user
    
    user_roles = current_user.get("roles", [])
    admin_roles = ["Admin", "Super Admin"]
    
    if not any(role in user_roles for role in admin_roles):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required"
        )
    
    return current_user

# New integration role dependency
require_integration = require_role("Integration")
require_super_admin = require_role("Super Admin")
