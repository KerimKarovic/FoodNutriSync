from fastapi import APIRouter, FastAPI, HTTPException, Depends, Path, Query, Request, File, UploadFile, Security
from fastapi.middleware.cors import CORSMiddleware
from fastapi.templating import Jinja2Templates
from fastapi.responses import JSONResponse, RedirectResponse
import pandas as pd
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
import time
import os
import io
from datetime import datetime
from .database import get_session
from .services.bls_service import BLSService
from .schemas import BLSUploadResponse
from .exceptions import BLSNotFoundError, BLSValidationError
from .auth import get_current_user, require_admin, require_bls_reader, jwt_auth, extract_token_from_request, docs_bearer, verify_admin_credentials
from .logging_config import setup_logging
import chardet
from fastapi.security import HTTPBearer
from fastapi.openapi.utils import get_openapi
from .exceptions import BLSNotFoundError, BLSValidationError
from app import auth

# Setup logging first
app_logger = setup_logging()

APP_VERSION = "1.4.0"
app = FastAPI(
    title="NutriSync", 
    version=APP_VERSION,
    openapi_tags=[
        {"name": "Authentication", "description": "JWT authentication endpoints"},
        {"name": "BLS", "description": "BLS nutrition data endpoints"},
        {"name": "Admin", "description": "Admin data management endpoints"},
        {"name": "System", "description": "Health and system endpoints"}
    ]
)

app_start_time = time.time()
templates = Jinja2Templates(directory="app/templates")
bls_service = BLSService()

# CORS
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
    allow_headers=["Authorization", "Content-Type"]
)

@app.on_event("startup")
async def startup_event():
    """Application startup tasks"""
    try:
        # Log initialization status
        if jwt_auth.public_key:
            app_logger.info("JWT authentication initialized with PEM key")
        else:
            app_logger.warning("JWT authentication initialized without keys (development mode)")
        
    except Exception as e:
        app_logger.error(f"Startup failed: {e}")
        raise

@app.on_event("shutdown") 
async def shutdown_event():
    """Application shutdown tasks"""
    try:
        app_logger.info("Application shutdown completed")
        
    except Exception as e:
        app_logger.error(f"Shutdown error: {e}")

# Health endpoints
@app.get("/health", tags=["System"], summary="Application health check", description="Returns comprehensive application health status including uptime, version, and system information")
@app.get("/health/live", tags=["System"], summary="Liveness probe", description="Kubernetes liveness probe endpoint - confirms application is running with detailed status")
async def health_live():
    """Liveness probe - detailed application status"""
    uptime_seconds = time.time() - app_start_time
    
    return {
        "status": "healthy",
        "service": "FoodNutriSync BLS API",
        "version": APP_VERSION,
        "uptime_seconds": round(uptime_seconds, 2),
        "uptime_human": f"{int(uptime_seconds // 3600)}h {int((uptime_seconds % 3600) // 60)}m {int(uptime_seconds % 60)}s",
        "timestamp": datetime.now().isoformat(),
        "environment": os.getenv("ENVIRONMENT", "unknown"),
        "jwt_auth_status": jwt_auth.get_status(),
        "checks": {
            "application": "healthy",
            "jwt_keys": "loaded" if jwt_auth.public_key else "missing"
        }
    }

@app.get("/health/ready", tags=["System"], summary="Readiness probe", description="Kubernetes readiness probe endpoint - confirms application and database connectivity with detailed diagnostics")
async def ready(session: AsyncSession = Depends(get_session)):
    """Readiness check with comprehensive database and service status"""
    # Short-circuit for tests
    if os.getenv("TESTING") == "1":
        return {
            "status": "ready",
            "service": "FoodNutriSync BLS API",
            "version": APP_VERSION,
            "environment": "testing",
            "timestamp": datetime.now().isoformat(),
            "checks": {
                "database": "bypassed_for_testing",
                "application": "ready"
            }
        }
    
    db_status = "unknown"
    db_response_time = 0
    db_error = None
    
    try:
        start_time = time.time()
        await session.execute(text("SELECT 1"))
        db_response_time = round((time.time() - start_time) * 1000, 2)  # ms
        db_status = "connected"
    except Exception as e:
        db_status = "failed"
        db_error = str(e)
        return JSONResponse({
            "status": "not_ready",
            "service": "FoodNutriSync BLS API",
            "version": APP_VERSION,
            "timestamp": datetime.now().isoformat(),
            "environment": os.getenv("ENVIRONMENT", "unknown"),
            "checks": {
                "database": "failed",
                "application": "ready",
                "jwt_auth": "loaded" if jwt_auth.get_status()['keys_loaded'] > 0 else "missing"
            },
            "database": {
                "status": db_status,
                "error": db_error,
                "response_time_ms": db_response_time
            }
        }, status_code=503)
    
    uptime_seconds = time.time() - app_start_time
    
    return {
        "status": "ready",
        "service": "FoodNutriSync BLS API", 
        "version": APP_VERSION,
        "uptime_seconds": round(uptime_seconds, 2),
        "timestamp": datetime.now().isoformat(),
        "environment": os.getenv("ENVIRONMENT", "unknown"),
        "checks": {
            "database": "connected",
            "application": "ready",
            "jwt_auth": "loaded" if jwt_auth.public_key else "missing"
        },
        "database": {
            "status": db_status,
            "response_time_ms": db_response_time,
            "connection_pool": "active"
        },
        "jwt_auth_status": jwt_auth.get_status()
    }

# BLS endpoints - PUT SEARCH FIRST!
@app.get("/bls/search", 
        tags=["BLS Data"], 
        dependencies=[Depends(require_bls_reader), Security(docs_bearer)],
        summary="Search BLS entries by name",
        description="Search BLS nutrition database by German food name and retrieve matching products with full nutrient data")
async def search_bls(
    name: str = Query(..., min_length=1, max_length=1000, description="German food name to search for"),
    limit: int = Query(10, ge=1, le=100, description="Maximum number of results to return"),
    session: AsyncSession = Depends(get_session)
):
    """Search BLS entries by German name"""
    results = await bls_service.search_by_name(session, name, limit)
    return results

@app.get("/bls/{bls_number}", 
        tags=["BLS Data"], 
        dependencies=[Depends(require_bls_reader), Security(docs_bearer)],
        summary="Get BLS entry by number",
        description="Retrieve complete nutrition data for a specific BLS food item using its unique 7-character identifier")
async def get_bls(
    bls_number: str = Path(..., regex=r"^[A-Z]\d{6}$", description="7-character BLS number (1 letter + 6 digits)"),
    session: AsyncSession = Depends(get_session)
):
    """Get BLS entry by number"""
    try:
        result = await bls_service.get_by_bls_number(session, bls_number)
        return result
    except BLSNotFoundError:
        raise HTTPException(404, "BLS entry not found")
    except BLSValidationError:
        raise HTTPException(422, "Invalid BLS number format")

# Admin router with auth protection
admin_router = APIRouter(prefix="/admin", tags=["Admin"])

@admin_router.put("/upload-bls", 
                summary="Upload BLS dataset", 
                description="Upload with admin username/password")
async def upload_bls_data(
    file: UploadFile = File(...),
    admin_user: dict = Depends(verify_admin_credentials),  # Changed from require_admin
    session: AsyncSession = Depends(get_session)
):
    """Upload BLS dataset file - FULL DATASET REPLACEMENT"""
    if not file.size:
        raise HTTPException(422, "Empty file not allowed")
    
    if file.content_type not in ["text/plain", "text/csv", "application/octet-stream"]:
        raise HTTPException(400, "Invalid file type")
    
    try:
        # Read file content
        content = await file.read()
        
        # Detect encoding
        detected = chardet.detect(content)
        encoding = detected.get('encoding', 'utf-8')
        
        # Convert to DataFrame
        df = pd.read_csv(io.StringIO(content.decode(encoding or 'utf-8')), sep='\t')
        
        # Process upload using BLS service
        result = await bls_service.upload_data(session, df, file.filename or "unknown_file.txt")
        
        return result
        
    except Exception as e:
        app_logger.error(f"Upload failed: {str(e)}")
        raise HTTPException(500, f"Upload failed: {str(e)}")

app.include_router(admin_router)

@app.get("/admin", include_in_schema=False)
async def admin_dashboard(request: Request):
    """Admin dashboard with redirect to login if not authenticated"""
    try:
        # Check for admin session cookie
        admin_session = request.cookies.get("admin_session")
        
        if admin_session and admin_session.startswith("admin:"):
            email = admin_session.split(":", 1)[1]
            
            # Verify the email matches our admin email
            admin_email = os.getenv("ADMIN_EMAIL", "admin@example.com")
            if email == admin_email:
                return templates.TemplateResponse("admin.html", {
                    "request": request,
                    "user": {"user_id": email, "roles": ["Admin"]}
                })
        
        # No valid session - redirect to login
        return RedirectResponse(url="/login?next=/admin", status_code=302)
        
    except Exception:
        # Any auth error -> redirect to login
        return RedirectResponse(url="/login?next=/admin", status_code=302)

@app.get("/login", include_in_schema=False)
async def login_page(request: Request):
    """Login page"""
    return templates.TemplateResponse("login.html", {"request": request})

app.include_router(auth.router, prefix="", tags=["Authentication"])

@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Handle errors"""
    app_logger.error(f"Error on {request.url.path}: {str(exc)}")
    
    detail = "Internal server error" if os.getenv("ENVIRONMENT") == "production" else str(exc)
    
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error", "detail": detail}
    )

def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    openapi_schema = get_openapi(
        title="FoodNutriSync API",
        version=APP_VERSION,
        description="BLS Nutrition Data API with JWT Authentication",
        routes=app.routes,
    )
    openapi_schema["components"]["securitySchemes"] = {
        "BearerAuth": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
            "description": "JWT token for ROLE_INTEGRATION users"
        },
        "BasicAuth": {
            "type": "http",
            "scheme": "basic",
            "description": "Username/password for admin endpoints"
        }
    }
    app.openapi_schema = openapi_schema
    return app.openapi_schema

# Clear the schema cache to force regeneration
app.openapi_schema = None
app.openapi = custom_openapi

@app.get("/docs", include_in_schema=False, dependencies=[Depends(get_current_user)])
async def get_docs():
    """Protected Swagger UI"""
    from fastapi.openapi.docs import get_swagger_ui_html
    return get_swagger_ui_html(
        openapi_url="/openapi.json", 
        title="FoodNutriSync API",
        swagger_ui_parameters={"persistAuthorization": True}
    )

@app.get("/openapi.json", include_in_schema=False, dependencies=[Depends(get_current_user)])
async def get_openapi_schema():
    """Protected OpenAPI schema"""
    return app.openapi()
