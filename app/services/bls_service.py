from typing import Optional, List
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert
import pandas as pd
import re

from app.models import BLSNutrition
from app.schemas import BLSNutrientResponse, BLSSearchResponse, BLSUploadResponse
from app.exceptions import BLSNotFoundError, BLSValidationError


class BLSService:
    """Business logic for BLS nutrition data operations"""
    
    BLS_PATTERN = re.compile(r'^[B-Y]\d{6}$')
    
    async def get_by_bls_number(self, session: AsyncSession, bls_number: str) -> BLSNutrientResponse:
        """Get nutrition data by BLS number"""
        if not self.BLS_PATTERN.match(bls_number):
            raise BLSValidationError(f"Invalid BLS number format: {bls_number}")
        
        stmt = select(BLSNutrition).where(BLSNutrition.bls_number == bls_number)
        result = await session.execute(stmt)
        bls_item = result.scalar_one_or_none()
        
        if not bls_item:
            raise BLSNotFoundError(f"BLS number {bls_number} not found")
        
        return BLSNutrientResponse.from_orm_obj(bls_item)
    
    async def search_by_name(self, session: AsyncSession, name: str, limit: int = 50) -> BLSSearchResponse:
        """Search BLS entries by German name"""
        if not name or not name.strip():
            return BLSSearchResponse(results=[], count=0)
        
        search_term = f"%{name.strip().lower()}%"
        stmt = (
            select(BLSNutrition)
            .where(BLSNutrition.name_german.ilike(search_term))
            .limit(limit)
        )
        
        result = await session.execute(stmt)
        items = result.scalars().all()
        
        results = [BLSNutrientResponse.from_orm_obj(item) for item in items]
        return BLSSearchResponse(results=results, count=len(results))
    
    async def upload_data(self, session: AsyncSession, df: pd.DataFrame, filename: str) -> BLSUploadResponse:
        """Process and upload BLS data from DataFrame"""
        validator = BLSDataValidator()
        valid_records, errors = validator.validate_dataframe(df, filename)
        
        added_count = 0
        if valid_records:
            added_count = await self._bulk_upsert(session, valid_records)
        
        return BLSUploadResponse(
            added=added_count,
            updated=0,  # Simplified for now
            failed=len(errors),
            errors=errors[:10]
        )
    
    async def _bulk_upsert(self, session: AsyncSession, records: List[dict]) -> int:
        """Perform bulk upsert operation"""
        stmt = insert(BLSNutrition).values(records)
        upsert_stmt = stmt.on_conflict_do_update(
            index_elements=['bls_number'],
            set_={col.name: stmt.excluded[col.name] 
                  for col in BLSNutrition.__table__.columns 
                  if col.name != 'bls_number'}
        )
        
        await session.execute(upsert_stmt)
        await session.commit()
        return len(records)


class BLSDataValidator:
    """Validates BLS data for upload"""
    
    BLS_PATTERN = re.compile(r'^[B-Y]\d{6}$')
    
    def validate_dataframe(self, df: pd.DataFrame, filename: str) -> tuple[List[dict], List[str]]:
        """Validate entire DataFrame and return valid records and errors"""
        valid_records = []
        errors = []
        
        for i, (index, row) in enumerate(df.iterrows()):
            try:
                record = self._validate_row(row, i)
                if record:
                    valid_records.append(record)
            except BLSValidationError as e:
                errors.append(str(e))
        
        return valid_records, errors
    
    def _validate_row(self, row: pd.Series, index: int) -> Optional[dict]:
        """Validate a single row and return processed data"""
        # Extract BLS number
        bls_number = self._extract_bls_number(row)
        if not bls_number:
            raise BLSValidationError(f"Row {index + 1}: Missing or invalid BLS number")
        
        # Extract German name
        name_german = self._extract_name(row)
        if not name_german:
            raise BLSValidationError(f"Row {index + 1}: Missing German name")
        
        if len(name_german) > 255:
            raise BLSValidationError(f"Row {index + 1}: Name too long (max 255 chars)")
        
        # Extract nutrients
        nutrients = self._extract_nutrients(row)
        
        return {
            'bls_number': bls_number,
            'name_german': name_german,
            **nutrients
        }
    
    def _extract_bls_number(self, row: pd.Series) -> Optional[str]:
        """Extract and validate BLS number from row"""
        bls_value = row.get('SBLS')
        if pd.isna(bls_value) or not isinstance(bls_value, str):
            return None
        
        bls_value = str(bls_value).strip()
        if self.BLS_PATTERN.match(bls_value):
            return bls_value
        return None
    
    def _extract_name(self, row: pd.Series) -> Optional[str]:
        """Extract German name from row"""
        for col in ['STE', 'ST', 'name_german']:
            if col in row.index:
                value = row.get(col)
                if pd.notna(value) and str(value).strip():
                    return str(value).strip()
        return None
    
    def _extract_nutrients(self, row: pd.Series) -> dict:
        """Extract nutrient values from row"""
        nutrients = {}
        excluded_cols = {'SBLS', 'ST', 'STE', 'bls_number', 'name_german'}
        
        for col in row.index:
            if col not in excluded_cols:
                value = row.get(col)
                if pd.notna(value) and value != '':
                    try:
                        float_val = float(str(value).replace(',', '.'))
                        if float_val >= 0:
                            nutrients[col.lower()] = float_val
                    except (ValueError, TypeError):
                        continue
        
        return nutrients


