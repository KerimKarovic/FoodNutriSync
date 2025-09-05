from __future__ import annotations

import io
import os
import time
from datetime import datetime
from pathlib import Path

import pandas as pd
from fastapi import (
    APIRouter, Depends, FastAPI, File, HTTPException,
    Path as FPath, Query, Request, Security, UploadFile,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.exceptions import BLSNotFoundError, BLSValidationError
from app.schemas import BLSUploadResponse
from app.services.bls_service import BLSService
from app.auth import (
    auth_router,
    get_current_user,
    require_bls_reader,
    get_current_admin_cookie,   # NEW
    require_admin_cookie,       # NEW
)

APP_VERSION = os.getenv("APP_VERSION", "1.0.0")
ENV = os.getenv("ENVIRONMENT", "development").lower()

app = FastAPI(title="FoodNutriSync BLS API", version=APP_VERSION, docs_url=None, redoc_url=None, openapi_url=None)

# CORS
allowed = (
    ["https://your-frontend-domain.com", "https://admin-portal.company.com"]
    if ENV == "production"
    else ["http://localhost:3000", "http://localhost:5173", "http://127.0.0.1:3000"]
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

# Templates
BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=os.getenv("TEMPLATES_DIR") or str(BASE_DIR / "templates"))

bls_service = BLSService()
_started = time.time()

# Health
@app.get("/health/live", tags=["System"])
async def health_live():
    return {"status": "up", "service": "FoodNutriSync BLS API", "version": APP_VERSION, "timestamp": datetime.now().isoformat()}

@app.get("/health", tags=["System"])
async def health():
    key_ok = bool(os.getenv("LICENSEMANAGER_PUBLIC_KEY_PEM") or os.getenv("LICENSEMANAGER_PUBLIC_KEY_URL"))
    return {
        "status": "healthy", "service": "FoodNutriSync BLS API", "version": APP_VERSION,
        "environment": ENV, "uptime_seconds": round(time.time() - _started, 2),
        "jwt_key_configured": key_ok, "timestamp": datetime.now().isoformat(),
    }

@app.get("/health/ready", tags=["System"])
async def health_ready(session: AsyncSession = Depends(get_session)):
    db_ok = True
    try:
        await session.execute(text("SELECT 1"))
    except Exception:
        db_ok = False
    key_ok = bool(os.getenv("LICENSEMANAGER_PUBLIC_KEY_PEM") or os.getenv("LICENSEMANAGER_PUBLIC_KEY_URL"))
    return {"status": "ready" if (db_ok and key_ok) else "degraded", "checks": {"database": db_ok, "jwt_key": key_ok}}

# BLS Data (ROLE_INTEGRATION or Admin)
bls_router = APIRouter(prefix="/bls", tags=["BLS Data"])

@bls_router.get("/search", 
                summary="Search BLS entries by name", 
                description="Search by German name (ILIKE).",
                openapi_extra={"security": [{"HTTPBearer": []}]})
async def bls_search(
    q: str = Query(..., min_length=1, description="Search term"),
    limit: int = Query(10, ge=1, le=100, description="Max results"),
    user = Security(require_bls_reader),
    session: AsyncSession = Depends(get_session),
):
    try:
        return await bls_service.search_by_name(session, name=q, limit=limit)
    except Exception as e:
        raise HTTPException(500, f"Search failed: {e}")

@bls_router.get("/{bls_number}", 
                summary="Get BLS entry by number", 
                description="7-character BLS number (letter + 6 digits).",
                openapi_extra={"security": [{"HTTPBearer": []}]})
async def get_bls_by_number(
    bls_number: str = FPath(..., regex=r"^[B-Y]\d{6}$"),
    user = Security(require_bls_reader),
    session: AsyncSession = Depends(get_session),
):
    try:
        return await bls_service.get_by_bls_number(session, bls_number)
    except BLSNotFoundError:
        raise HTTPException(404, "BLS entry not found")
    except BLSValidationError as e:
        raise HTTPException(422, str(e))

app.include_router(bls_router)

# Admin (Admin-only, COOKIE ONLY)
admin_router = APIRouter(prefix="/admin", tags=["Admin"])

@admin_router.put("/upload-bls",
                summary="Upload BLS dataset",
                description="Full dataset replacement (TXT/TSV). Requires admin UI session (cookie).",
                openapi_extra={"security": []})
async def upload_bls_dataset(
    file: UploadFile = File(...),
    user = Depends(require_admin_cookie),
    session: AsyncSession = Depends(get_session),
) -> BLSUploadResponse:
    if not file or not (file.filename and file.filename.lower().endswith(".txt")):
        raise HTTPException(400, "Only .txt files are supported")

    raw = await file.read()
    if not raw:
        raise HTTPException(422, "Empty file")

    # Robust decode (UTF-8/16/CP1252)
    text = None
    for enc in ("utf-8-sig", "utf-8", "utf-16", "utf-16-le", "utf-16-be", "cp1252", "iso-8859-1", "latin1"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        text = raw.decode("utf-8", errors="replace")

    # Parse as tab-separated TXT (Python engine tolerant)
    df = pd.read_csv(io.StringIO(text), sep="\t", engine="python", dtype=str, na_filter=False, on_bad_lines="skip", quoting=3)

    # Normalize headers/cells
    def _norm(s):
        return s.replace("\ufeff", "").replace("\xa0", " ").strip() if isinstance(s, str) else s
    df.columns = [_norm(c) for c in df.columns]
    df = df.map(_norm)
    if "SBLS" not in df.columns and len(df.columns) > 0:
        df.rename(columns={df.columns[0]: "SBLS"}, inplace=True)

    return await bls_service.upload_data(session, df, file.filename or "upload.txt")

@app.get("/admin", include_in_schema=False)
@app.get("/admin/", include_in_schema=False)
async def admin_dashboard(request: Request):
    try:
        user = await get_current_admin_cookie(request)  # <-- cookie-only
    except HTTPException:
        return RedirectResponse(url="/login?next=/admin", status_code=302)
    ctx = {"user": {"user_id": user.get("sub") or user.get("email") or "unknown", "roles": user.get("roles", [])}}
    return templates.TemplateResponse("admin.html", {"request": request, **ctx})

@app.get("/login", include_in_schema=False)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

app.include_router(admin_router)
app.include_router(auth_router, prefix="/auth", tags=["Authentication"])

# Swagger (public; operations remain role-guarded)
def _build_openapi(app: FastAPI):
    from fastapi.openapi.utils import get_openapi
    schema = get_openapi(title=app.title, version=app.version, routes=app.routes)
    schema.setdefault("components", {}).setdefault("securitySchemes", {})["HTTPBearer"] = {
        "type": "http", "scheme": "bearer", "bearerFormat": "JWT",
        "description": "Read-only tokens (ROLE_INTEGRATION). Admin routes use the httpOnly cookie from /auth/admin-login.",
    }
    # Remove global security - will be set per-operation instead
    app.openapi_schema = schema
    return schema

app.openapi = lambda: _build_openapi(app)

@app.get("/openapi.json", include_in_schema=False)
async def openapi_json():
    return app.openapi()

@app.get("/docs", include_in_schema=False)
def swagger_ui():
    from fastapi.openapi.docs import get_swagger_ui_html

    base = get_swagger_ui_html(
        openapi_url="/openapi.json",
        title="FoodNutriSync API",
        swagger_ui_parameters={"persistAuthorization": True},
    )

    # get the original HTML as text
    body = base.body
    if isinstance(body, (bytes, bytearray)):
        html = body.decode("utf-8")
    else:
        html = str(body)  # already a string in some versions

    # inject the Admin button
    inject = """
    <style>
      #adminButton{
        position:fixed; top:12px; right:12px; z-index:1000;
        padding:8px 12px; border-radius:8px; text-decoration:none;
        background:#111827; color:#fff; font-family:ui-sans-serif,system-ui,Segoe UI,Roboto,Helvetica,Arial,sans-serif;
        box-shadow:0 2px 6px rgba(0,0,0,.15)
      }
      #adminButton:hover{ filter:brightness(1.1) }
    </style>
    <a id="adminButton" href="/admin">⛭ Admin Dashboard</a>
    """
    html = html.replace("</body>", inject + "</body>")

    # IMPORTANT: don't reuse base.headers (it contains the old Content-Length)
    return HTMLResponse(content=html, status_code=base.status_code, media_type="text/html")

@app.get("/", include_in_schema=False)
async def root():
    return RedirectResponse(url="/docs", status_code=302)
