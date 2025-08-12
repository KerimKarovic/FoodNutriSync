from fastapi import FastAPI, HTTPException, Depends, Query, UploadFile, File, Request, Path
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession
import pandas as pd
from io import BytesIO
import time
from typing import AsyncGenerator

from app.database import SessionLocal
from app.schemas import BLSNutrientResponse, BLSSearchResponse, BLSUploadResponse
from app.services.bls_service import BLSService
from app.exceptions import BLSNotFoundError, BLSValidationError, FileUploadError
from app.logging_config import setup_logging, app_logger
from fastapi.middleware.cors import CORSMiddleware

# Initialize logging
setup_logging()

app = FastAPI(title="FoodNutriSync", version="1.0.0")
templates = Jinja2Templates(directory="app/templates")

# Service instances
bls_service = BLSService()

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:8000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session


def get_client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    return fwd.split(",")[0].strip() if fwd else (request.client.host if request.client else "unknown")


@app.get("/")
async def root():
    return {"message": "FoodNutriSync API", "version": "1.0.0"}


@app.get(
    "/bls/search",
    response_model=BLSSearchResponse,
    response_model_exclude_none=True,
    tags=["BLS"],
    summary="Search by German food name"
)
async def search_bls(
    request: Request,
    name: str = Query("", description="German food name to search"),
    limit: int = Query(50, ge=1, le=100, description="Maximum results to return"),
    session: AsyncSession = Depends(get_session)
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
            user_ip=client_ip
        )
        
        return result
    except Exception as e:
        app_logger.logger.error(f"Search failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")


@app.get(
    "/bls/{bls_number}",
    response_model=BLSNutrientResponse,
    response_model_exclude_none=True,
    tags=["BLS"],
    summary="Lookup a food by BLS number"
)
async def get_bls_by_number(
    request: Request,
    bls_number: str = Path(
        ...,
        pattern=r"^[B-Y]\d{6}$",
        description="BLS number (e.g., B123456)"
    ),
    session: AsyncSession = Depends(get_session)
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
            user_ip=client_ip
        )
        
        return result
    except BLSNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except BLSValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        app_logger.logger.error(f"Lookup failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Lookup failed: {str(e)}")


@app.post(
    "/admin/upload-bls",
    response_model=BLSUploadResponse,
    tags=["Admin"],
    summary="Upload BLS CSV/Excel"
)
async def upload_bls(
    request: Request,
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_session)
):
    start_time = time.time()
    client_ip = get_client_ip(request)
    filename = file.filename or "unknown_file"

    # Enhanced file type validation
    kind = (file.content_type or "").lower()
    is_csv = kind in {"text/csv", "application/csv"} or (filename.endswith(".csv"))
    is_excel = kind in {
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/vnd.ms-excel",
    } or (filename.endswith((".xlsx", ".xls")))
    
    if not (is_csv or is_excel):
        raise HTTPException(400, "File must be CSV or Excel format")

    # Size validation
    content = await file.read()
    MAX_UPLOAD = 10 * 1024 * 1024  # 10MB
    if len(content) > MAX_UPLOAD:
        raise HTTPException(413, "File too large (max 10MB)")

    try:
        app_logger.log_upload_start(
            filename=filename,
            file_size=len(content),
            user_ip=client_ip
        )
        
        # Parse file
        if is_csv:
            df = pd.read_csv(BytesIO(content))
        else:
            df = pd.read_excel(BytesIO(content))
        
        # Process data
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
        
    except (BLSValidationError, FileUploadError) as e:
        duration_ms = (time.time() - start_time) * 1000
        app_logger.log_upload_error(
            filename=filename,
            error=str(e),
            duration_ms=duration_ms
        )
        raise HTTPException(400, str(e))
    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        app_logger.log_upload_error(
            filename=filename,
            error=str(e),
            duration_ms=duration_ms
        )
        raise HTTPException(500, f"Error processing file: {str(e)}")


@app.get("/health", tags=["System"])
async def health():
    return {"status": "ok"}

@app.get("/admin", response_class=HTMLResponse)
async def admin_page(request: Request):
    return templates.TemplateResponse("upload.html", {"request": request})



