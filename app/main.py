from fastapi import FastAPI, HTTPException, Depends, Path, Query, Request, File, UploadFile
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
from .schemas import BLSSearchResponse, BLSUploadResponse
from .exceptions import BLSNotFoundError, BLSValidationError
from .auth import get_current_user, require_admin, require_bls_reader, get_client_ip, jwt_auth
from .logging_config import setup_logging
import chardet

from app import auth

# Setup logging first
app_logger = setup_logging()

APP_VERSION = "1.4.0"
app = FastAPI(title="FoodNutriSync", version=APP_VERSION)

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
        # Start JWT background tasks
        await jwt_auth.start_background_refresh()
        
        # Log initialization status
        app_logger.info("JWT authentication initialized successfully")
        status = jwt_auth.get_status()
        app_logger.info(f"Key management status: {status}")
        
    except Exception as e:
        app_logger.error(f"Startup failed: {e}")
        raise

@app.on_event("shutdown") 
async def shutdown_event():
    """Application shutdown tasks"""
    try:
        # Stop JWT background tasks
        await jwt_auth.stop_background_refresh()
        app_logger.info("JWT background tasks stopped cleanly")
        
    except Exception as e:
        app_logger.error(f"Shutdown error: {e}")

@app.get("/bls/search", response_model=BLSSearchResponse, tags=["BLS"])
async def search_bls(
    request: Request,
    name: str = Query(..., min_length=1, max_length=100),
    limit: int = Query(50, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
    current_user: dict = Depends(require_bls_reader)
):
    start_time = time.time()
    client_ip = get_client_ip(request)
    
    try:
        result = await bls_service.search_by_name(session, name, limit)
        
        duration_ms = (time.time() - start_time) * 1000
        app_logger.info(f"BLS search: {name} by {current_user.get('user_id')} - {len(result.results)} results in {duration_ms:.0f}ms")
        
        return result
    except Exception as e:
        app_logger.error(f"Search failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")

@app.get("/bls/{bls_number}", tags=["BLS"])
async def get_bls_by_number(
    request: Request,
    bls_number: str = Path(..., regex=r"^[A-Z]\d{6}$"),
    session: AsyncSession = Depends(get_session),
    current_user: dict = Depends(require_bls_reader)
):
    start_time = time.time()
    
    try:
        result = await bls_service.get_by_bls_number(session, bls_number)
        
        duration_ms = (time.time() - start_time) * 1000
        app_logger.info(f"BLS lookup: {bls_number} by {current_user.get('user_id')} in {duration_ms:.0f}ms")
        
        return result
    except BLSNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        app_logger.error(f"Lookup failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Lookup failed: {str(e)}")

@app.put("/admin/bls-dataset", response_model=BLSUploadResponse, tags=["Admin"])
async def replace_bls_dataset(
    request: Request,
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
    current_user: dict = Depends(require_admin)
):
    start_time = time.time()
    filename = file.filename or "unknown_file"

    # Validate file
    if not filename.endswith(".txt"):
        raise HTTPException(400, "File must be TXT format")

    content = await file.read()
    if len(content) > 200 * 1024 * 1024:  # 200MB
        raise HTTPException(413, "File too large")

    try:
        # Detect encoding
        detected = chardet.detect(content)
        encoding = detected.get('encoding') or 'utf-8'
        
        try:
            content_str = content.decode(encoding)
        except UnicodeDecodeError:
            # Try fallback encodings
            for fallback in ['windows-1252', 'iso-8859-1']:
                try:
                    content_str = content.decode(fallback)
                    break
                except UnicodeDecodeError:
                    continue
            else:
                raise HTTPException(400, "Unable to decode file")
        
        # Parse data
        df = pd.read_csv(io.StringIO(content_str), sep='\t', dtype=str)
        df = df.dropna(subset=['SBLS'])
        df = df[df['SBLS'].astype(str).str.strip() != '']
        
        app_logger.info(f"BLS dataset upload by {current_user.get('user_id')}: {len(df)} records")
        
        # Process upload
        result = await bls_service.upload_data(session, df, filename)
        
        duration_ms = (time.time() - start_time) * 1000
        app_logger.info(f"Upload complete: {result.added} added, {result.updated} updated in {duration_ms:.0f}ms")
        
        return result
        
    except Exception as e:
        app_logger.error(f"Upload failed: {str(e)}")
        raise HTTPException(500, f"Upload failed: {str(e)}")

@app.get("/health", tags=["System"])
async def health(session: AsyncSession = Depends(get_session)):
    """Health check"""
    start_time = time.time()
    uptime_seconds = int(time.time() - app_start_time)
    
    health_response = {
        "status": "ok",
        "version": APP_VERSION,
        "uptime_s": uptime_seconds,
        "timestamp": datetime.utcnow().isoformat() + "Z"
    }
    
    try:
        # Database check
        result = await session.execute(text("SELECT COUNT(*) FROM bls_data LIMIT 1"))
        record_count = result.scalar()
        
        health_response["database"] = {
            "status": "ok",
            "record_count": record_count
        }
        
    except Exception as e:
        health_response["status"] = "error"
        health_response["error"] = str(e)
        app_logger.error(f"Health check failed: {str(e)}")
    
    return health_response

@app.get("/health/ready", tags=["System"])
async def readiness_check(session: AsyncSession = Depends(get_session)):
    """Readiness probe"""
    try:
        await session.execute(text("SELECT 1"))
        return {"status": "ready"}
    except Exception as e:
        raise HTTPException(503, f"Not ready: {str(e)}")

@app.get("/health/live", tags=["System"])
async def liveness_check():
    """Liveness probe"""
    return {"status": "alive"}

@app.get("/admin", include_in_schema=False)
async def admin_dashboard(request: Request):
    """Admin dashboard"""
    if os.getenv("ENVIRONMENT") == "development":
        return templates.TemplateResponse("admin.html", {"request": request})
    
    # Check auth in production
    auth_header = request.headers.get("authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        return RedirectResponse(url="/login", status_code=302)
    
    try:
        token = auth_header[7:]
        from .auth import jwt_auth
        payload = await jwt_auth.validate_token(token)
        
        if "Admin" not in payload.get("roles", []):
            return RedirectResponse(url="/login", status_code=302)
        
        return templates.TemplateResponse("admin.html", {"request": request})
    except:
        return RedirectResponse(url="/login", status_code=302)

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
