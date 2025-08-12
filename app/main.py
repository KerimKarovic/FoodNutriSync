from fastapi import FastAPI, HTTPException, Depends, Query, UploadFile, File, Request
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert
import pandas as pd
from io import BytesIO
import re
import time
from typing import AsyncGenerator

from app.database import SessionLocal
from app.models import BLSNutrition
from app.schemas import BLSNutrientResponse, BLSSearchResponse, BLSUploadResponse
from app.logging_config import setup_logging, app_logger

# Initialize logging
setup_logging()

app = FastAPI(title="FoodNutriSync", version="1.0.0")
templates = Jinja2Templates(directory="app/templates")

async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session

def get_client_ip(request: Request) -> str:
    """Extract client IP from request"""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"

@app.get("/")
async def root():
    app_logger.logger.info("Root endpoint accessed")
    return {
        "ok": True, 
        "version": "1.0.0",
        "endpoints": ["/bls/{bls_number}", "/bls/search", "/admin/upload-bls", "/admin"]
    }

@app.get("/admin", response_class=HTMLResponse)
async def admin_page(request: Request):
    client_ip = get_client_ip(request)
    app_logger.logger.info(f"Admin page accessed from {client_ip}")
    return templates.TemplateResponse("upload.html", {"request": request})

@app.get("/bls/search", response_model=BLSSearchResponse)
async def search_bls(
    request: Request,
    name: str, 
    limit: int = Query(50, ge=1, le=100),
    session: AsyncSession = Depends(get_session)
):
    start_time = time.time()
    client_ip = get_client_ip(request)
    
    try:
        rows = (await session.execute(
            select(BLSNutrition)
            .where(BLSNutrition.name_german.ilike(f"%{name}%"))
            .limit(limit)
        )).scalars().all()
        
        results = [BLSNutrientResponse.from_orm_obj(row) for row in rows]
        duration_ms = (time.time() - start_time) * 1000
        
        app_logger.log_api_query(
            endpoint="/bls/search",
            params={"name": name, "limit": limit},
            result_count=len(results),
            duration_ms=duration_ms,
            user_ip=client_ip
        )
        
        return BLSSearchResponse(results=results, count=len(results))
        
    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        app_logger.logger.error(f"Search query failed: {str(e)}", extra={
            'extra_data': {
                'event_type': 'api_error',
                'endpoint': '/bls/search',
                'error': str(e),
                'duration_ms': duration_ms,
                'user_ip': client_ip
            }
        })
        raise HTTPException(500, f"Search failed: {str(e)}")

@app.get("/bls/{bls_number}", response_model=BLSNutrientResponse)
async def get_bls(
    request: Request,
    bls_number: str, 
    session: AsyncSession = Depends(get_session)
):
    start_time = time.time()
    client_ip = get_client_ip(request)
    bls_number = bls_number.upper()
    
    try:
        row = (await session.execute(
            select(BLSNutrition).where(BLSNutrition.bls_number == bls_number)
        )).scalar_one_or_none()
        
        duration_ms = (time.time() - start_time) * 1000
        
        if not row:
            app_logger.log_api_query(
                endpoint=f"/bls/{bls_number}",
                params={"bls_number": bls_number},
                result_count=0,
                duration_ms=duration_ms,
                user_ip=client_ip
            )
            raise HTTPException(404, f"BLS number '{bls_number}' not found")
        
        app_logger.log_api_query(
            endpoint=f"/bls/{bls_number}",
            params={"bls_number": bls_number},
            result_count=1,
            duration_ms=duration_ms,
            user_ip=client_ip
        )
        
        return BLSNutrientResponse.from_orm_obj(row)
        
    except HTTPException:
        raise
    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        app_logger.logger.error(f"BLS lookup failed: {str(e)}", extra={
            'extra_data': {
                'event_type': 'api_error',
                'endpoint': f'/bls/{bls_number}',
                'error': str(e),
                'duration_ms': duration_ms,
                'user_ip': client_ip
            }
        })
        raise HTTPException(500, f"Lookup failed: {str(e)}")

@app.post("/admin/upload-bls", response_model=BLSUploadResponse)
async def upload_bls(
    request: Request,
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_session)
):
    start_time = time.time()
    client_ip = get_client_ip(request)
    
    if not file.filename or not file.filename.endswith(('.csv', '.xlsx', '.xls')):
        raise HTTPException(400, "File must be CSV or Excel format")
    
    try:
        content = await file.read()
        file_size = len(content)
        
        app_logger.log_upload_start(
            filename=file.filename,
            file_size=file_size,
            user_ip=client_ip
        )
        
        if file.filename.endswith('.csv'):
            df = pd.read_csv(BytesIO(content))
        else:
            df = pd.read_excel(BytesIO(content))
        
        result = await process_bls_data(df, session, file.filename)
        duration_ms = (time.time() - start_time) * 1000
        
        app_logger.log_upload_success(
            filename=file.filename,
            added=result.added,
            updated=result.updated,
            failed=result.failed,
            duration_ms=duration_ms
        )
        
        return result
        
    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        app_logger.log_upload_error(
            filename=file.filename,
            error=str(e),
            duration_ms=duration_ms
        )
        raise HTTPException(500, f"Error processing file: {str(e)}")

@app.get("/admin/logs", response_class=HTMLResponse)
async def logs_page(request: Request):
    """Simple log viewer page"""
    try:
        with open("logs/app.log", "r", encoding="utf-8") as f:
            lines = f.readlines()[-100:]
            log_content = "".join(lines)
    except FileNotFoundError:
        log_content = "No logs found yet."
    
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>FoodNutriSync - Logs</title>
        <style>
            body {{ font-family: monospace; margin: 20px; background: #1a1a1a; color: #00ff00; }}
            .log-container {{ background: #000; padding: 20px; border-radius: 8px; overflow-x: auto; }}
            .header {{ color: #fff; margin-bottom: 20px; }}
            pre {{ white-space: pre-wrap; word-wrap: break-word; }}
        </style>
    </head>
    <body>
        <div class="header">
            <h1>🔍 FoodNutriSync Logs</h1>
            <p><a href="/admin" style="color: #00aaff;">← Back to Admin</a></p>
        </div>
        <div class="log-container">
            <pre>{log_content}</pre>
        </div>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)

async def process_bls_data(df: pd.DataFrame, session: AsyncSession, filename: str) -> BLSUploadResponse:
    added_count = 0
    updated_count = 0
    failed_count = 0
    errors = []
    
    def validate_bls_row(row, index: int) -> tuple[dict | None, str | None]:
        """Validate a single BLS row and return data or error"""
        bls_pattern = re.compile(r'^[B-Y]\d{6}$')
        
        try:
            bls_number = (row.get('SBLS') or row.get('bls_number') or '').strip().upper()
            name_german = (row.get('ST') or row.get('name_german') or '').strip()
            
            if not bls_number:
                error_msg = f"Row {index + 1}: Missing BLS number"
                app_logger.log_validation_error(filename, index + 1, error_msg)
                return None, error_msg
            
            if not bls_pattern.match(bls_number):
                error_msg = f"Row {index + 1}: Invalid BLS number format '{bls_number}'"
                app_logger.log_validation_error(filename, index + 1, error_msg)
                return None, error_msg
            
            if not name_german or name_german == 'nan':
                error_msg = f"Row {index + 1}: Missing German name"
                app_logger.log_validation_error(filename, index + 1, error_msg)
                return None, error_msg
            
            if len(name_german) > 255:
                error_msg = f"Row {index + 1}: Name too long (max 255 chars)"
                app_logger.log_validation_error(filename, index + 1, error_msg)
                return None, error_msg
            
            nutrient_values = {}
            for col in row.index:
                if col not in ['SBLS', 'ST', 'STE', 'bls_number', 'name_german']:
                    value = row.get(col)
                    if pd.notna(value) and value != '':
                        try:
                            s = str(value).replace(',', '.')
                            float_val = float(s)
                            if float_val < 0:
                                continue
                            nutrient_values[col.lower()] = float_val
                        except (ValueError, TypeError):
                            pass
            
            return {
                'bls_number': bls_number,
                'name_german': name_german,
                **nutrient_values
            }, None
            
        except Exception as e:
            error_msg = f"Row {index + 1}: Validation error - {str(e)}"
            app_logger.log_validation_error(filename, index + 1, error_msg)
            return None, error_msg
    
    # Validate and collect valid records
    valid_records = []
    for i, (index, row) in enumerate(df.iterrows()):
        data, error = validate_bls_row(row, i)
        if data:
            valid_records.append(data)
        elif error:
            failed_count += 1
            errors.append(error)
    
    # Bulk upsert valid records
    if valid_records:
        try:
            stmt = insert(BLSNutrition).values(valid_records)
            upsert_stmt = stmt.on_conflict_do_update(
                index_elements=['bls_number'],
                set_={col.name: stmt.excluded[col.name] 
                      for col in BLSNutrition.__table__.columns 
                      if col.name != 'bls_number'}
            )
            
            result = await session.execute(upsert_stmt)
            await session.commit()
            
            # Count operations (simplified - actual counts would need more complex logic)
            added_count = len(valid_records)  # Approximation
            
        except Exception as e:
            await session.rollback()
            app_logger.logger.error(f"Database upsert failed: {str(e)}")
            raise
    
    return BLSUploadResponse(
        added=added_count,
        updated=updated_count,
        failed=failed_count,
        errors=errors[:10]  # Limit error list
    )
