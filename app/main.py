from io import BytesIO
import io
import csv
from fastapi import FastAPI, HTTPException, Depends, Query, Request, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
import pandas as pd
from sqlalchemy.ext.asyncio import AsyncSession
from typing import AsyncGenerator
import time

from .database import SessionLocal
from .services.bls_service import BLSService
from .schemas import BLSSearchResponse, BLSUploadResponse, BulkImportResponse
from .exceptions import BLSNotFoundError, BLSValidationError, FileUploadError
from .logging_config import app_logger
from .auth import get_current_user, require_admin

app = FastAPI(title="NutriSync", version="1.0.0")
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
    return {"message": "NutriSync API", "version": "1.0.0"}


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
    session: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user)  # Add authentication
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


@app.get("/bls/{bls_number}", tags=["BLS"])
async def get_bls_by_number(
    request: Request,
    bls_number: str,
    session: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user)  # Add authentication
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
    summary="Upload BLS .txt"
)
async def upload_bls(
    request: Request,
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
    current_user: dict = Depends(require_admin)  # Require admin role
):
    start_time = time.time()
    client_ip = get_client_ip(request)
    filename = file.filename or "unknown_file"

    # File type validation - only TXT
    if not filename.endswith(".txt"):
        raise HTTPException(400, "File must be TXT format")

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
        
        # Parse TXT file with multiple encoding attempts
        df = None
        encodings_to_try = [
            'utf-8-sig',  # UTF-8 with BOM
            'utf-8',      # Standard UTF-8
            'utf-16',     # UTF-16 with BOM
            'utf-16-le',  # UTF-16 Little Endian
            'utf-16-be',  # UTF-16 Big Endian
            'iso-8859-1', # Latin-1
            'windows-1252', # Windows encoding
            'cp1252'      # Code page 1252
        ]
        
        for encoding in encodings_to_try:
            try:
                df = pd.read_table(
                    BytesIO(content), 
                    decimal=',', 
                    sep='\t', 
                    encoding=encoding, 
                    header=0,
                    skipinitialspace=True,
                    on_bad_lines='skip'  # Skip problematic lines
                )
                print(f"DEBUG: Successfully read with encoding: {encoding}")
                print(f"DEBUG: Columns after reading: {list(df.columns)}")
                break
            except (UnicodeDecodeError, pd.errors.EmptyDataError, UnicodeError) as e:
                print(f"DEBUG: Failed with encoding {encoding}: {e}")
                continue
        
        if df is None:
            raise HTTPException(400, "Could not decode file with any supported encoding")
        
        # Clean column names (remove BOM if present)
        df.columns = [col.lstrip('ÿþ').strip() for col in df.columns]
        print(f"DEBUG: Cleaned columns: {list(df.columns)}")
        
        # Remove empty rows - filter out rows where SBLS is NaN or empty
        initial_count = len(df)
        df = df.dropna(subset=['SBLS'])  # Remove rows with NaN SBLS
        df = df[df['SBLS'].astype(str).str.strip() != '']  # Remove rows with empty SBLS
        print(f"DEBUG: Filtered {initial_count} -> {len(df)} rows (removed {initial_count - len(df)} empty rows)")
        
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


def detect_csv_delimiter(content: str, filename: str) -> str:
    """Detect CSV delimiter based on file extension and content"""
    if filename.endswith('.txt'):
        # Assume tab-delimited for .txt files
        return '\t'
    elif filename.endswith('.csv'):
        # Use sniffer for .csv files
        try:
            sniffer = csv.Sniffer()
            delimiter = sniffer.sniff(content[:1024]).delimiter
            return delimiter
        except:
            return ';'  # Default fallback
    return ';'  # Default fallback

@app.post(
    "/admin/bulk-import-articles",
    response_model=BulkImportResponse,
    tags=["Admin"],
    summary="Bulk import nutrition data for articles"
)
async def bulk_import_articles(
    request: Request,
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
    current_user: dict = Depends(require_admin)  # Require admin role
):
    start_time = time.time()
    client_ip = get_client_ip(request)
    filename = file.filename or "unknown_file"

    # File type validation - CSV only
    if not filename.endswith((".csv", ".txt")):
        raise HTTPException(400, "File must be CSV or TXT format")

    # Size validation
    content = await file.read()
    MAX_UPLOAD = 5 * 1024 * 1024  # 5MB for article lists
    if len(content) > MAX_UPLOAD:
        raise HTTPException(413, "File too large (max 5MB)")

    try:
        content_str = content.decode('utf-8')
        delimiter = detect_csv_delimiter(content_str, filename)
        
        # Parse CSV with detected delimiter
        df = pd.read_csv(io.StringIO(content_str), sep=delimiter)
        
        # Validate required columns
        required_columns = ['article_id', 'bls_number']
        missing_columns = [col for col in required_columns if col not in df.columns]
        if missing_columns:
            raise HTTPException(400, f"Missing required columns: {missing_columns}")
        
        # Remove empty rows
        initial_count = len(df)
        df = df.dropna(subset=['article_id', 'bls_number'])
        df = df[(df['article_id'].astype(str).str.strip() != '') & 
                (df['bls_number'].astype(str).str.strip() != '')]
        
        app_logger.info(f"Processing {len(df)} articles (filtered from {initial_count})")
        
        # Process bulk import
        result = await bls_service.bulk_import_articles(session, df)
        
        duration_ms = (time.time() - start_time) * 1000
        app_logger.log_upload_success(
            filename=filename,
            added=result.successful,
            updated=0,
            failed=result.failed,
            duration_ms=duration_ms
        )
        
        return result
        
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



