# app/main.py
from __future__ import annotations

import io
import os
import time
from datetime import datetime
from pathlib import Path

import pandas as pd
from fastapi import (
    APIRouter,
    Depends,
    FastAPI,
    File,
    HTTPException,
    Path as FPath,
    Query,
    Request,
    Security,
    UploadFile,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# -------------------------------------------------------------------
# Local imports (service path fallback to support your current layout)
# -------------------------------------------------------------------
from app.database import get_session
from app.exceptions import BLSNotFoundError, BLSValidationError
from app.schemas import BLSUploadResponse

try:
    # common layout: app/services/bls_service.py
    from app.services.bls_service import BLSService
except Exception:
    # fallback: app/bls_service.py
    from app.bls_service import BLSService  # type: ignore

# Auth utilities (JWT-based, from your updated auth.py)
from app.auth import (
    auth_router,
    docs_bearer,
    get_current_user,
    require_admin,
    require_bls_reader,
)

# Optional logging config if present
try:
    from app.logging_config import setup_logging  # type: ignore
except Exception:
    setup_logging = None  # pragma: no cover

APP_VERSION = os.getenv("APP_VERSION", "1.0.0")
ENV = os.getenv("ENVIRONMENT", "development").lower()

# -------------------------------------------------
# FastAPI app (docs/openapi made public on purpose)
# -------------------------------------------------
app = FastAPI(
    title="FoodNutriSync BLS API",
    version=APP_VERSION,
    docs_url=None,       # we serve /docs manually (public)
    redoc_url=None,
    openapi_url=None,    # we serve /openapi.json manually (public)
)

# ----------------
# CORS middleware
# ----------------
if ENV == "production":
    allowed_origins = [
        # add your production frontends here
        "https://your-frontend-domain.com",
        "https://admin-portal.company.com",
    ]
else:
    allowed_origins = [
        "http://localhost:3000",
        "http://localhost:5173",
        "http://127.0.0.1:3000",
    ]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

# -----------------
# Jinja2 templates
# -----------------
BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = os.getenv("TEMPLATES_DIR") or str(BASE_DIR / "templates")
templates = Jinja2Templates(directory=TEMPLATES_DIR)

# -------------
# App services
# -------------
bls_service = BLSService()
_app_started_at = time.time()

# --------
# Startup
# --------
@app.on_event("startup")
async def on_startup() -> None:
    if setup_logging:
        setup_logging()


# -------------------------
# Health / readiness (public)
# -------------------------
@app.get("/health/live", tags=["System"], summary="Liveness probe")
async def health_live() -> dict:
    return {
        "status": "up",
        "service": "FoodNutriSync BLS API",
        "version": APP_VERSION,
        "timestamp": datetime.now().isoformat(),
    }


@app.get("/health", tags=["System"], summary="Application health check")
async def health() -> dict:
    uptime_seconds = time.time() - _app_started_at
    key_configured = bool(
        os.getenv("LICENSEMANAGER_PUBLIC_KEY_PEM")
        or os.getenv("LICENSEMANAGER_PUBLIC_KEY_URL")
    )
    return {
        "status": "healthy",
        "service": "FoodNutriSync BLS API",
        "version": APP_VERSION,
        "environment": ENV,
        "uptime_seconds": round(uptime_seconds, 2),
        "jwt_key_configured": key_configured,
        "timestamp": datetime.now().isoformat(),
    }


@app.get("/health/ready", tags=["System"], summary="Readiness probe")
async def health_ready(session: AsyncSession = Depends(get_session)) -> dict:
    db_ok = False
    try:
        await session.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        db_ok = False

    key_configured = bool(
        os.getenv("LICENSEMANAGER_PUBLIC_KEY_PEM")
        or os.getenv("LICENSEMANAGER_PUBLIC_KEY_URL")
    )
    return {
        "status": "ready" if (db_ok and key_configured) else "degraded",
        "checks": {
            "database": "ok" if db_ok else "fail",
            "jwt_key": "configured" if key_configured else "missing",
        },
        "timestamp": datetime.now().isoformat(),
        "version": APP_VERSION,
    }


# -----------------------------------------
# BLS Data (ROLE_INTEGRATION or Admin only)
# -----------------------------------------
bls_router = APIRouter(prefix="/bls", tags=["BLS Data"])

@bls_router.get(
    "/search",
    summary="Search BLS entries by name",
    description="Search by German name (ILIKE).",
)
async def bls_search(
    q: str = Query(..., min_length=1, description="Search term"),
    limit: int = Query(10, ge=1, le=100, description="Max results"),
    user = Security(require_bls_reader),    # role gate
    session: AsyncSession = Depends(get_session),
):
    try:
        # Service signature: search_by_name(session, name, limit)
        results = await bls_service.search_by_name(session, name=q, limit=limit)
        return results
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Search failed: {e}")


@bls_router.get(
    "/{bls_number}",
    summary="Get BLS entry by number",
    description="7-character BLS number (letter + 6 digits).",
)
async def get_bls_by_number(
    bls_number: str = FPath(..., regex=r"^[B-Y]\d{6}$"),
    user = Security(require_bls_reader),    # role gate
    session: AsyncSession = Depends(get_session),
):
    try:
        entry = await bls_service.get_by_bls_number(session, bls_number)
        return entry
    except BLSNotFoundError:
        raise HTTPException(status_code=404, detail="BLS entry not found")
    except BLSValidationError as e:
        raise HTTPException(status_code=422, detail=str(e))


app.include_router(bls_router)


# -------------------------------
# Admin (Admin-only: JWT role gate)
# -------------------------------
admin_router = APIRouter(prefix="/admin", tags=["Admin"])

@admin_router.put(
    "/upload-bls",
    summary="Upload BLS dataset",
    description="Full dataset replacement (TXT/TSV). Admin only.",
)
async def upload_bls_dataset(
    file: UploadFile = File(...),
    user = Security(require_admin),                     # ADMIN ROLE REQUIRED
    session: AsyncSession = Depends(get_session),
) -> BLSUploadResponse:
    if not file:
        raise HTTPException(status_code=422, detail="File is required")

    if file.content_type not in {"text/plain", "text/csv", "application/octet-stream"}:
        # Frontend enforces .txt; accept common text/csv content-types
        raise HTTPException(status_code=400, detail="Invalid content-type")

    try:
        payload = await file.read()
        if not payload:
            raise HTTPException(status_code=422, detail="Empty file")

        # Handle encoding more robustly - try UTF-8 first, then fallback to latin-1
        try:
            content = payload.decode("utf-8")
        except UnicodeDecodeError:
            try:
                content = payload.decode("latin-1")
            except UnicodeDecodeError:
                content = payload.decode("utf-8", errors="replace")

        # The data file is tab-separated
        df = pd.read_csv(io.StringIO(content), sep="\t")

        # Full replace via service: upload_data(session, df, filename)
        result: BLSUploadResponse = await bls_service.upload_data(session, df, file.filename or "unknown_file.txt")
        return result

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Upload failed: {e}")


@app.get("/admin", include_in_schema=False)
@app.get("/admin/", include_in_schema=False)
async def admin_dashboard(request: Request):
    """
    Admin dashboard. Requires admin-role JWT (cookie or Authorization header).
    If unauthenticated or not admin -> redirect to /login.
    """
    try:
        user = await get_current_user(request)
        await require_admin(user)  # raises if not admin
    except HTTPException:
        return RedirectResponse(url="/login?next=/admin", status_code=302)

    ctx_user = {
        "user_id": user.get("sub") or user.get("email") or "unknown",
        "roles": user.get("roles", []),
    }
    return templates.TemplateResponse("admin.html", {"request": request, "user": ctx_user})


@app.get("/login", include_in_schema=False)
async def login_page(request: Request):
    """Public login page for admins (posts to /auth/admin-login)."""
    return templates.TemplateResponse("login.html", {"request": request})


app.include_router(admin_router)


# --------------------------------------
# Authentication router (from app/auth)
# --------------------------------------
app.include_router(auth_router, prefix="/auth", tags=["Authentication"])


# ----------------------------------
# OpenAPI & Swagger (public access)
# ----------------------------------
def _build_openapi(app: FastAPI):
    from fastapi.openapi.utils import get_openapi

    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        routes=app.routes,
    )
    # Single JWT security scheme
    openapi_schema.setdefault("components", {}).setdefault("securitySchemes", {})["BearerAuth"] = {
        "type": "http",
        "scheme": "bearer",
        "bearerFormat": "JWT",
        "description": "Provide a JWT issued by License Manager (cookie or header).",
    }
    app.openapi_schema = openapi_schema
    return app.openapi_schema

app.openapi = lambda: _build_openapi(app)


@app.get("/openapi.json", include_in_schema=False)
async def openapi_json():
    return app.openapi()


@app.get("/docs", include_in_schema=False)
async def swagger_ui():
    from fastapi.openapi.docs import get_swagger_ui_html
    
    custom_html = """
    <!DOCTYPE html>
    <html>
    <head>
        <link type="text/css" rel="stylesheet" href="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui.css">
        <title>FoodNutriSync API</title>
        <style>
            .admin-button {
                position: fixed;
                top: 20px;
                right: 20px;
                background: linear-gradient(135deg, #007bff 0%, #0056b3 100%);
                color: white;
                padding: 12px 24px;
                border: none;
                border-radius: 6px;
                cursor: pointer;
                font-weight: bold;
                text-decoration: none;
                z-index: 9999;
                box-shadow: 0 2px 10px rgba(0,123,255,0.3);
                transition: all 0.3s ease;
            }
            .admin-button:hover {
                background: linear-gradient(135deg, #0056b3 0%, #004085 100%);
                transform: translateY(-2px);
                box-shadow: 0 4px 15px rgba(0,123,255,0.4);
            }
        </style>
    </head>
    <body>
        <a href="/admin" target="_blank" class="admin-button">🔧 Admin Dashboard</a>
        <div id="swagger-ui"></div>
        <script src="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-bundle.js"></script>
        <script>
            SwaggerUIBundle({
                url: '/openapi.json',
                dom_id: '#swagger-ui',
                presets: [
                    SwaggerUIBundle.presets.apis,
                    SwaggerUIBundle.presets.standalone
                ],
                persistAuthorization: true,
                displayRequestDuration: true,
                layout: "BaseLayout"
            });
        </script>
    </body>
    </html>
    """
    
    from fastapi.responses import HTMLResponse
    return HTMLResponse(content=custom_html)


# -----------------------
# Root → docs (public)
# -----------------------
@app.get("/", include_in_schema=False)
async def root():
    return RedirectResponse(url="/docs", status_code=302)
