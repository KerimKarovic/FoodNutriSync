import pandas as pd
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert  # Use PostgreSQL-specific insert
from typing import List, Dict, Tuple, Optional
import re
import io

from ..models import BLSNutrition
from ..schemas import BLSNutrientResponse, BLSSearchResponse, BLSUploadResponse, BulkImportResponse, ArticleImportResult
from ..exceptions import BLSValidationError, BLSNotFoundError, FileUploadError


class BLSService:
    """Business logic for BLS nutrition data operations"""
    
    BLS_PATTERN = re.compile(r'^[B-Y]\d{6}$')  # 1 letter + 6 digits = 7 total
    
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

    async def search_by_name(self, session: AsyncSession, name: str, limit: int = 10) -> BLSSearchResponse:
        """Search BLS entries by German name"""
        # Use trigram similarity search
        stmt = (
            select(BLSNutrition)
            .where(BLSNutrition.name_german.ilike(f"%{name}%"))
            .limit(limit)
        )
        
        result = await session.execute(stmt)
        items = result.scalars().all()
        
        return BLSSearchResponse(
            results=[BLSNutrientResponse.from_orm_obj(item) for item in items],
            count=len(items)
        )
    
    async def upload_data(self, session: AsyncSession, df: pd.DataFrame, filename: str) -> BLSUploadResponse:
        """Process and upload BLS data from DataFrame"""
        validator = BLSDataValidator()
        valid_records, errors = validator.validate_dataframe(df, filename)
        
        if not valid_records:
            return BLSUploadResponse(added=0, updated=0, failed=len(errors), errors=errors[:10])
        
        # Process in batches to avoid parameter limits
        batch_size = 1000  # Adjust based on column count
        added_total = 0
        updated_total = 0
        
        for i in range(0, len(valid_records), batch_size):
            batch = valid_records[i:i + batch_size]
            added, updated = await self._bulk_upsert_with_counts(session, batch)
            added_total += added
            updated_total += updated
        
        return BLSUploadResponse(
            added=added_total,
            updated=updated_total,
            failed=len(errors),
            errors=errors[:10]
        )
    
    async def _bulk_upsert_with_counts(self, session: AsyncSession, records: List[dict]) -> Tuple[int, int]:
        """Perform bulk upsert with accurate insert/update counts"""
        # First, try insert with DO NOTHING to count actual inserts
        stmt_insert = insert(BLSNutrition).values(records)
        insert_stmt = stmt_insert.on_conflict_do_nothing(index_elements=['SBLS'])
        insert_stmt = insert_stmt.returning(BLSNutrition.SBLS)
        
        insert_result = await session.execute(insert_stmt)
        inserted_ids = [row[0] for row in insert_result.fetchall()]
        inserted_count = len(inserted_ids)
        
        # Then update existing records (those not inserted)
        existing_records = [r for r in records if r['SBLS'] not in inserted_ids]
        updated_count = 0
        
        if existing_records:
            stmt_update = insert(BLSNutrition).values(existing_records)
            update_stmt = stmt_update.on_conflict_do_update(
                index_elements=['SBLS'],
                set_={col.name: stmt_update.excluded[col.name] 
                      for col in BLSNutrition.__table__.columns 
                      if col.name != 'SBLS'}
            )
            await session.execute(update_stmt)
            updated_count = len(existing_records)
        
        await session.commit()
        return inserted_count, updated_count

    async def bulk_import_articles(self, session: AsyncSession, df: pd.DataFrame) -> BulkImportResponse:
        """Process bulk import for articles with BLS numbers - optimized batch lookup"""
        results = []
        successful = 0
        failed = 0
        
        # Extract all unique BLS numbers for batch lookup
        bls_numbers = df['bls_number'].dropna().astype(str).str.strip().unique().tolist()
        
        # Batch fetch all BLS records at once
        bls_lookup = await self._batch_get_bls_records(session, bls_numbers)
        
        for row_num, row in enumerate(df.itertuples(index=False), start=1):
            try:
                article_id = str(getattr(row, 'article_id', '')).strip()
                bls_number = str(getattr(row, 'bls_number', '')).strip()
                
                if not article_id:
                    results.append(ArticleImportResult(
                        article_id=f"Row_{row_num}",
                        bls_number=bls_number,
                        status="failed",
                        error="Missing article_id"
                    ))
                    failed += 1
                    continue
                
                if not bls_number:
                    results.append(ArticleImportResult(
                        article_id=article_id,
                        bls_number="",
                        status="failed",
                        error="Missing bls_number"
                    ))
                    failed += 1
                    continue
                
                # Validate BLS format
                if not self.BLS_PATTERN.match(bls_number):
                    results.append(ArticleImportResult(
                        article_id=article_id,
                        bls_number=bls_number,
                        status="failed",
                        error=f"Invalid BLS format: {bls_number}"
                    ))
                    failed += 1
                    continue
                
                # Look up from batch-fetched data
                bls_data = bls_lookup.get(bls_number)
                if not bls_data:
                    results.append(ArticleImportResult(
                        article_id=article_id,
                        bls_number=bls_number,
                        status="failed",
                        error=f"BLS number {bls_number} not found"
                    ))
                    failed += 1
                    continue
                
                results.append(ArticleImportResult(
                    article_id=article_id,
                    bls_number=bls_number,
                    status="success",
                    nutrients=bls_data.nutrients
                ))
                successful += 1
                
            except Exception as e:
                results.append(ArticleImportResult(
                    article_id=article_id if 'article_id' in locals() else f"Row_{row_num}",
                    bls_number=bls_number if 'bls_number' in locals() else "",
                    status="failed",
                    error=f"Unexpected error: {str(e)}"
                ))
                failed += 1
        
        return BulkImportResponse(
            processed=len(df),
            successful=successful,
            failed=failed,
            results=results
        )
    
    async def _batch_get_bls_records(self, session: AsyncSession, bls_numbers: List[str]) -> Dict[str, BLSNutrientResponse]:
        """Batch fetch BLS records to avoid N+1 queries"""
        if not bls_numbers:
            return {}
        
        stmt = select(BLSNutrition).where(BLSNutrition.SBLS.in_(bls_numbers))
        result = await session.execute(stmt)
        records = result.scalars().all()
        
        return {
            record.SBLS: BLSNutrientResponse.from_orm_obj(record) 
            for record in records
        }


class BLSDataValidator:
    """Validates BLS data for upload"""
    
    BLS_PATTERN = re.compile(r'^[B-Y]\d{6}$')
    
    # Actual BLS file column order (what we receive)
    BLS_FILE_COLUMNS = [
        'SBLS', 'ST', 'STE', 'GCAL', 'GJ', 'GCALZB', 'GJZB', 'ZW', 'ZE', 'ZF', 'ZK', 'ZB', 'ZM', 'ZO', 'ZA',
        'VA', 'VAR', 'VAC', 'VD', 'VE', 'VEAT', 'VK', 'VB1', 'VB2', 'VB3', 'VB3A', 'VB5', 'VB6', 'VB7', 'VB9G', 'VB12', 'VC',
        'MNA', 'MK', 'MCA', 'MMG', 'MP', 'MS', 'MCL', 'MFE', 'MZN', 'MCU', 'MMN', 'MF', 'MJ',
        'KAM', 'KAS', 'KAX', 'KA', 'KMT', 'KMF', 'KMG', 'KM', 'KDS', 'KDM', 'KDL', 'KD', 'KMD',
        'KPOR', 'KPON', 'KPG', 'KPS', 'KP', 'KBP', 'KBH', 'KBU', 'KBC', 'KBL', 'KBW', 'KBN',
        'EILE', 'ELEU', 'ELYS', 'EMET', 'ECYS', 'EPHE', 'ETYR', 'ETHR', 'ETRP', 'EVAL', 'EARG', 'EHIS', 'EEA',
        'EALA', 'EASP', 'EGLU', 'EGLY', 'EPRO', 'ESER', 'ENA', 'EH', 'EP',
        'F40', 'F60', 'F80', 'F100', 'F120', 'F140', 'F150', 'F160', 'F170', 'F180', 'F200', 'F220', 'F240', 'FS',
        'F141', 'F151', 'F161', 'F171', 'F181', 'F201', 'F221', 'F241', 'FU',
        'F162', 'F164', 'F182', 'F183', 'F184', 'F193', 'F202', 'F203', 'F204', 'F205',
        'F222', 'F223', 'F224', 'F225', 'F226', 'FP', 'FK', 'FM', 'FL', 'FO3', 'FO6', 'FG', 'FC',
        'GFPS', 'GKB', 'GMKO', 'GP'
    ]
    
    # Your DB column order (what we need to map to)
    DB_COLUMNS = [
        'SBLS', 'ST', 'GCAL', 'GJ', 'GCALZB', 'GJZB', 'ZW', 'ZE', 'ZF', 'ZK', 'ZB', 'ZM', 'ZO', 'ZA',
        'VA', 'VAR', 'VAC', 'VD', 'VE', 'VEAT', 'VK', 'VB1', 'VB2', 'VB3', 'VB3A', 'VB5', 'VB6', 'VB7', 'VB9G', 'VB12', 'VC',
        'MNA', 'MK', 'MCA', 'MMG', 'MP', 'MS', 'MCL', 'MFE', 'MZN', 'MCU', 'MMN', 'MF', 'MJ',
        'KAM', 'KAS', 'KAX', 'KA', 'KMT', 'KMF', 'KMG', 'KM', 'KDS', 'KDM', 'KDL', 'KD', 'KMD',
        'KPOR', 'KPON', 'KPG', 'KPS', 'KP', 'KBP', 'KBH', 'KBU', 'KBC', 'KBL', 'KBW', 'KBN',
        'EILE', 'ELEU', 'ELYS', 'EMET', 'ECYS', 'EPHE', 'ETYR', 'ETHR', 'ETRP', 'EVAL', 'EARG', 'EHIS', 'EEA',
        'EALA', 'EASP', 'EGLU', 'EGLY', 'EPRO', 'ESER', 'ENA', 'EH', 'EP',
        'F40', 'F60', 'F80', 'F100', 'F120', 'F140', 'F150', 'F160', 'F170', 'F180', 'F200', 'F220', 'F240', 'FS',
        'F141', 'F151', 'F161', 'F171', 'F181', 'F201', 'F221', 'F241', 'FU',
        'F162', 'F164', 'F182', 'F183', 'F184', 'F193', 'F202', 'F203', 'F204', 'F205',
        'F222', 'F223', 'F224', 'F225', 'F226', 'FP', 'FK', 'FM', 'FL', 'FO3', 'FO6', 'FG', 'FC',
        'GFPS', 'GKB', 'GMKO', 'GP', 'STE'
    ]
    
    def validate_dataframe(self, df: pd.DataFrame, filename: str) -> tuple[List[dict], List[str]]:
        """Validate entire DataFrame and return valid records and errors"""
        valid_records = []
        errors = []
        
        for i, (_, row) in enumerate(df.iterrows()):
            try:
                record = self._validate_row(row, i)
                if record:
                    valid_records.append(record)
            except BLSValidationError as e:
                errors.append(str(e))
        
        return valid_records, errors
    
    def _validate_row(self, row: pd.Series, index: int) -> Optional[dict]:
        """Validate a single row and return processed data"""
        # Extract and validate BLS number
        bls_number = self._extract_bls_number(row)
        if not bls_number:
            raise BLSValidationError(f"Row {index + 1}: Missing or invalid BLS number")
        
        # Extract and validate German name (ST - column 1)
        name_german = self._extract_german_name(row)
        if not name_german:
            raise BLSValidationError(f"Row {index + 1}: Missing German name")
        
        if len(name_german) > 255:
            raise BLSValidationError(f"Row {index + 1}: German name too long (max 255 chars)")
        
        # Extract English name (STE - column 2) 
        name_english = self._extract_english_name(row)
        
        record = {
            'SBLS': bls_number,      # Use actual DB column name
            'ST': name_german,       # Use actual DB column name
            'STE': name_english,     # Use actual DB column name
            **self._extract_nutrients(row)
        }
        
        return record
    
    def _extract_bls_number(self, row: pd.Series) -> Optional[str]:
        """Extract and validate BLS number from row"""
        # Try different possible column names
        bls_value = None
        for col_name in ['SBLS', 'bls_number']:
            if col_name in row.index:
                bls_value = row[col_name]
                break
        
        if bls_value is None and len(row) > 0:
            bls_value = row.iloc[0]  # Fallback to first column
        
        if pd.isna(bls_value):
            return None
        
        bls_value = str(bls_value).strip()
        result = self.BLS_PATTERN.match(bls_value)
        return bls_value if result else None
    
    def _extract_german_name(self, row: pd.Series) -> Optional[str]:
        """Extract German name from row (ST column)"""
        # Try different possible column names
        for col_name in ['ST', 'name_german']:
            if col_name in row.index:
                value = row[col_name]
                if pd.notna(value) and str(value).strip():
                    return str(value).strip()
        return None
    
    def _extract_english_name(self, row: pd.Series) -> Optional[str]:
        """Extract English name from row (STE column)"""
        value = row.get('STE') if 'STE' in row.index else (row.iloc[2] if len(row) > 2 else None)
        if pd.notna(value) and str(value).strip():
            return str(value).strip()
        return None
    
    def _extract_nutrients(self, row: pd.Series) -> dict:
        """Extract nutrient values from row using column names"""
        nutrients = {}
        
        # Now we can directly access by column name since we have headers
        for col_name in self.DB_COLUMNS:
            if col_name in ['SBLS', 'ST', 'STE']:  # Skip the main identifier columns
                continue
                
            if col_name in row.index:
                value = row[col_name]
                if pd.notna(value) and str(value).strip() != '':
                    try:
                        # Handle German number format properly
                        str_value = str(value).strip()
                        if str_value:  # Only process non-empty strings
                            # German format: 1.234,56 -> 1234.56
                            # Check if it contains both . and , (German format)
                            if '.' in str_value and ',' in str_value:
                                # Remove thousand separator (.) and replace decimal comma with dot
                                str_value = str_value.replace('.', '').replace(',', '.')
                            else:
                                # Simple comma to dot replacement for decimal only
                                str_value = str_value.replace(',', '.')
                            
                            float_val = float(str_value)
                            if float_val >= 0:  # Only accept non-negative values
                                nutrients[col_name] = float(float_val)  # Ensure Python float type
                    except (ValueError, TypeError):
                        continue
        
        return nutrients





