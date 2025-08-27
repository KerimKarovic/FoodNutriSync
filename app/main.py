from fastapi import FastAPI, HTTPException, Depends, Path, Query, Request, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.templating import Jinja2Templates
from fastapi.responses import JSONResponse, RedirectResponse
import pandas as pd
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from typing import AsyncGenerator
import time
import os
import io
from datetime import datetime
from .database import SessionLocal, get_session
from .services.bls_service import BLSService
from .schemas import BLSSearchResponse, BLSUploadResponse
from .exceptions import BLSNotFoundError, BLSValidationError, FileUploadError
from .logging_config import setup_logging, app_logger
from .auth import get_current_user, require_admin, require_bls_reader, jwt_auth
import chardet
from . import auth
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.middleware.gzip import GZipMiddleware
import secrets
from fastapi.exceptions import RequestValidationError

APP_VERSION = "1.4.0"
app = FastAPI(title="NutriSync", version=APP_VERSION)

@app.on_event("startup")
async def startup_logging():
    setup_logging()
    
    # Initialize JWT keys on startup
    try:
        await jwt_auth._fetch_keys()
        await jwt_auth.start_background_refresh()
        app_logger.logger.info("JWT authentication initialized successfully")
        
        # Log key status for debugging
        health = jwt_auth.get_health_status()
        app_logger.logger.info(f"Key management status: {health}")
        
    except Exception as e:
        app_logger.logger.error(f"Failed to initialize JWT authentication: {e}")
        # Don't fail startup - let it continue for development mode

@app.on_event("shutdown")
async def shutdown_cleanup():
    """Clean shutdown of background tasks"""
    try:
        await jwt_auth.stop_background_refresh()
        app_logger.logger.info("JWT background tasks stopped cleanly")
    except Exception as e:
        app_logger.logger.error(f"Error during shutdown cleanup: {e}")

app_start_time = time.time()

# Templates setup
templates = Jinja2Templates(directory="app/templates")

# Service instances
bls_service = BLSService()

# Security middleware stack
app.add_middleware(GZipMiddleware, minimum_size=1000)

# Trusted hosts for production
if os.getenv("ENVIRONMENT") == "production":
    allowed_hosts = [
        "your-api-domain.com",
        "*.company.com",
        "127.0.0.1",  # Health checks
        "localhost"   # Health checks
    ]
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts)

# Production CORS setup
if os.getenv("ENVIRONMENT") == "production":
    allowed_origins = [
        "https://your-frontend-domain.com",
        "https://admin-portal.company.com"
    ]
else:
    allowed_origins = [
        "http://localhost:3000",
        "http://localhost:8080",
        "http://127.0.0.1:3000"
    ]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
    expose_headers=["X-Request-ID"]
)

# Security headers middleware (simplified)
@app.middleware("http")
async def security_headers(request: Request, call_next):
    """Add essential security headers"""
    response = await call_next(request)
    
    # Generate request ID for tracing
    request_id = secrets.token_hex(8)
    response.headers["X-Request-ID"] = request_id
    
    # Essential security headers
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    
    # HSTS for production HTTPS
    if os.getenv("ENVIRONMENT") == "production":
        response.headers["Strict-Transport-Security"] = "max-age=31536000"
    
    return response

def get_client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    return fwd.split(",")[0].strip() if fwd else (request.client.host if request.client else "unknown")


@app.get(
    "/bls/search",
    response_model=BLSSearchResponse,
    response_model_exclude_none=True,
    tags=["BLS"],
    summary="Search by German food name"
)
async def search_bls(
    request: Request,
    name: str = Query(..., min_length=1, max_length=100, description="German food name"),
    limit: int = Query(50, ge=1, le=100, description="Maximum results"),
    session: AsyncSession = Depends(get_session),
    current_user: dict = Depends(require_bls_reader)
):
    start_time = time.time()
    client_ip = get_client_ip(request)
    
    try:
        result = await bls_service.search_by_name(session, name, limit)
        
        duration_ms = (time.time() - start_time) * 1000
        app_logger.log_api_query(
            endpoint='/bls/search',
            params={'name': name, 'limit': limit},
            result_count=len(result.results),
            duration_ms=duration_ms,
            user_ip=client_ip,
            user_id=current_user.get("user_id"),  # Add user tracking
            user_roles=current_user.get("roles", [])
        )
        
        return result
    except Exception as e:
        app_logger.logger.error(f"Search failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")


@app.get("/bls/{bls_number}", tags=["BLS"])
async def get_bls_by_number(
    request: Request,
    bls_number: str = Path(..., regex=r"^[A-Z]\d{6}$", description="BLS number (e.g., B123456)"),
    session: AsyncSession = Depends(get_session),
    current_user: dict = Depends(require_bls_reader)
):
    start_time = time.time()
    client_ip = get_client_ip(request)
    
    try:
        result = await bls_service.get_by_bls_number(session, bls_number)
        
        duration_ms = (time.time() - start_time) * 1000
        app_logger.log_api_query(
            endpoint='/bls/{bls_number}',
            params={'bls_number': bls_number},
            result_count=1,
            duration_ms=duration_ms,
            user_ip=client_ip,
            user_id=current_user.get("user_id"),  # Add user tracking
            user_roles=current_user.get("roles", [])
        )
        
        return result
    except BLSNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except BLSValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        app_logger.logger.error(f"Lookup failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Lookup failed: {str(e)}")


@app.put(
    "/admin/bls-dataset",
    response_model=BLSUploadResponse,
    tags=["Admin"],
    summary="Replace BLS Dataset (Full Replacement)"
)
async def replace_bls_dataset(
    request: Request,
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
    current_user: dict = Depends(require_admin)  # Keep admin requirement
):
    start_time = time.time()
    client_ip = get_client_ip(request)
    filename = file.filename or "unknown_file"

    # File type validation - TXT ONLY
    if not filename.endswith(".txt"):
        raise HTTPException(400, "File must be TXT format (tab-separated)")

    # Size validation
    content = await file.read()
    MAX_UPLOAD = 200 * 1024 * 1024  # 200MB
    if len(content) > MAX_UPLOAD:
        raise HTTPException(413, "File too large (max 200MB)")

    try:
        # Detect encoding
        detected = chardet.detect(content)
        encoding = detected.get('encoding') or 'utf-8'
        
        # Handle common BOM cases
        if content.startswith(b'\xff\xfe'):
            encoding = 'utf-16-le'
        elif content.startswith(b'\xfe\xff'):
            encoding = 'utf-16-be'
        elif content.startswith(b'\xef\xbb\xbf'):
            encoding = 'utf-8-sig'
        
        # Decode with detected encoding
        try:
            content_str = content.decode(encoding)
        except UnicodeDecodeError:
            # Fallback encodings for German BLS files
            for fallback_encoding in ['windows-1252', 'iso-8859-1', 'cp1252']:
                try:
                    content_str = content.decode(fallback_encoding)
                    break
                except UnicodeDecodeError:
                    continue
            else:
                raise HTTPException(400, f"Unable to decode file. Detected encoding: {encoding}")
        
        # Parse as tab-separated file
        df = pd.read_csv(io.StringIO(content_str), sep='\t', dtype=str)
        
        # Remove empty rows
        initial_count = len(df)
        df = df.dropna(subset=['SBLS'])
        df = df[df['SBLS'].astype(str).str.strip() != '']
        
        # Log full replacement operation
        app_logger.logger.warning(
            f"FULL BLS DATASET REPLACEMENT initiated by {current_user.get('user_id', 'unknown')}",
            extra={
                'extra_data': {
                    'event_type': 'full_dataset_replacement',
                    'filename': filename,
                    'encoding': encoding,
                    'user_id': current_user.get('user_id'),
                    'records_to_process': len(df)
                }
            }
        )
        
        # Process data with full replacement
        result = await bls_service.upload_data(session, df, filename)
        
        duration_ms = (time.time() - start_time) * 1000
        app_logger.log_upload_success(
            filename=filename,
            added=result.added,
            updated=result.updated,
            failed=result.failed,
            duration_ms=duration_ms
        )
        
        return result
        
    except Exception as e:
        app_logger.logger.error(f"BLS dataset replacement failed: {str(e)}")
        raise HTTPException(500, f"Upload failed: {str(e)}")



@app.get("/health", tags=["System"])
async def health(session: AsyncSession = Depends(get_session)):
    """Comprehensive health check"""
    start_time = time.time()
    uptime_seconds = int(time.time() - app_start_time)
    
    health_response = {
        "status": "ok",
        "version": APP_VERSION,
        "uptime_s": uptime_seconds,
        "environment": os.getenv("ENVIRONMENT", "development"),
        "timestamp": datetime.utcnow().isoformat() + "Z"
    }
    
    try:
        # Database check
        db_start = time.time()
        result = await session.execute(text("SELECT COUNT(*) FROM bls_data LIMIT 1"))
        record_count = result.scalar()
        db_latency = round((time.time() - db_start) * 1000)
        
        health_response["database"] = {
            "status": "ok",
            "latency_ms": db_latency,
            "record_count": record_count
        }
        
        # JWT Auth check
        auth_health = jwt_auth.get_health_status()
        health_response["authentication"] = {
            "status": "ok" if auth_health["keys_loaded"] else "degraded",
            "key_type": auth_health["key_type"]
        }
        
    except Exception as e:
        health_response["status"] = "error"
        health_response["error"] = str(e)
        app_logger.logger.error(f"Health check failed: {str(e)}")
    
    return health_response

@app.get("/health/ready", tags=["System"])
async def readiness_check(session: AsyncSession = Depends(get_session)):
    """Simple readiness probe"""
    try:
        await session.execute(text("SELECT 1"))
        return {"status": "ready"}
    except Exception as e:
        raise HTTPException(503, f"Not ready: {str(e)}")

@app.get("/health/live", tags=["System"])
async def liveness_check():
    """Simple liveness probe"""
    return {"status": "alive"}

@app.get("/admin", include_in_schema=False)
async def admin_dashboard(request: Request):
    """Serve the admin dashboard HTML page or redirect to login"""
    # Check if we're in development mode
    if os.getenv("ENVIRONMENT") == "development":
        return templates.TemplateResponse("admin.html", {"request": request})
    
    # In production, check for JWT token
    auth_header = request.headers.get("authorization")
    if not auth_header:
        # No auth header, redirect to login
        return RedirectResponse(url="/login", status_code=302)
    
    try:
        # Try to validate the token
        from fastapi.security import HTTPAuthorizationCredentials
        from app.auth import jwt_auth
        
        # Extract token from "Bearer <token>"
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
            payload = await jwt_auth.validate_token(token)
            user_roles = payload.get("roles", [])
            
            # Check admin role
            if "Admin" not in user_roles:
                return RedirectResponse(url="/login", status_code=302)
            
            # User is authenticated and has admin role
            return templates.TemplateResponse("admin.html", {"request": request})
        else:
            # Invalid auth header format
            return RedirectResponse(url="/login", status_code=302)
            
    except Exception:
        # Token validation failed, redirect to login
        return RedirectResponse(url="/login", status_code=302)

@app.get("/login", include_in_schema=False)
async def login_page(request: Request):
    """Serve the login page"""
    return templates.TemplateResponse("login.html", {"request": request})

app.include_router(auth.router, prefix="", tags=["Authentication"])

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle validation errors gracefully"""
    app_logger.logger.warning(f"Validation error on {request.url.path}: {exc.errors()}")
    
    return JSONResponse(
        status_code=422,
        content={
            "error": "Invalid request data",
            "details": exc.errors(),
            "request_id": request.headers.get("X-Request-ID")
        }
    )

@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Handle unexpected errors"""
    app_logger.logger.error(f"Unhandled error on {request.url.path}: {str(exc)}")
    
    # Hide internal errors in production
    detail = "Internal server error" if os.getenv("ENVIRONMENT") == "production" else str(exc)
    
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "detail": detail,
            "request_id": request.headers.get("X-Request-ID")
        }
    )
