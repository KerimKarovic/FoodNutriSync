import pandas as pd
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert  # Use PostgreSQL-specific insert
from typing import List, Dict, Tuple, Optional
import re
import io

from ..models import BLSNutrition
from ..schemas import BLSNutrientResponse, BLSSearchResponse, BLSUploadResponse  # Remove BulkImportResponse, ArticleImportResult
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
        """Process and upload BLS data from DataFrame - FULL DATASET REPLACEMENT"""
        validator = BLSDataValidator()
        valid_records, errors = validator.validate_dataframe(df, filename)
        
        if not valid_records:
            return BLSUploadResponse(added=0, updated=0, failed=len(errors), errors=errors[:10])
        
        try:
            # STEP 1: Clear all existing BLS data
            await session.execute(text("DELETE FROM bls_nutrition"))
            await session.commit()  # Commit the delete immediately
            
            # STEP 2: Insert new data in batches
            estimated_cols_per_record = 140
            safe_batch_size = min(100, 25000 // estimated_cols_per_record)
            
            total_added = 0
            
            for i in range(0, len(valid_records), safe_batch_size):
                batch = valid_records[i:i + safe_batch_size]
                added = await self._bulk_insert_new_data(session, batch)
                total_added += added
            
            return BLSUploadResponse(
                added=total_added,
                updated=0,  # No updates in full replacement mode
                failed=len(errors),
                errors=errors[:10]
            )
            
        except Exception as e:
            await session.rollback()
            raise

    async def _bulk_insert_new_data(self, session: AsyncSession, records: List[dict]) -> int:
        """Insert new records after full table clear"""
        if not records:
            return 0

        table = BLSNutrition.__table__
        db_cols = {c.name for c in table.c}
        
        filtered_records = []
        for record in records:
            filtered_record = {k: v for k, v in record.items() if k in db_cols}
            if filtered_record and 'SBLS' in filtered_record:
                filtered_records.append(filtered_record)
        
        if not filtered_records:
            return 0

        # Simple insert - no conflict handling needed after DELETE
        stmt = insert(table).values(filtered_records)
        await session.execute(stmt)
        await session.commit()  # Commit each batch
        
        return len(filtered_records)

    # Removed bulk_import_articles and _batch_get_bls_records methods


class BLSDataValidator:
    """Validates BLS data for upload"""
    
    BLS_PATTERN = re.compile(r'^[B-Y]\d{6}$')
    
    # REMOVE: BLS_FILE_COLUMNS and DB_COLUMNS - no longer needed with correct schema
    
    def validate_dataframe(self, df: pd.DataFrame, filename: str) -> Tuple[List[dict], List[str]]:
        """Validate DataFrame and return valid records + errors"""
        valid_records = []
        errors = []
        
        for row_num, (idx, row) in enumerate(df.iterrows(), start=1):
            try:
                # Validate BLS number
                bls_number = str(row.get('SBLS', '')).strip()
                if not bls_number or not self.BLS_PATTERN.match(bls_number):
                    errors.append(f"Row {row_num}: Invalid BLS number '{bls_number}'")
                    continue
                
                # Build record with only columns that exist in input
                record = {'SBLS': bls_number}
                has_valid_data = False
                
                # Add German name if present and not empty
                if 'ST' in row.index and pd.notna(row['ST']) and str(row['ST']).strip():
                    record['ST'] = str(row['ST']).strip()
                    has_valid_data = True
                
                # Add English name if present and not empty
                if 'STE' in row.index and pd.notna(row['STE']) and str(row['STE']).strip():
                    record['STE'] = str(row['STE']).strip()
                    has_valid_data = True
                
                # Extract only numeric nutrients that exist in input
                nutrients = self._extract_nutrients(row)
                if nutrients:
                    record.update(nutrients)
                    has_valid_data = True
                
                # Only include records that have at least some valid data beyond SBLS
                if has_valid_data:
                    valid_records.append(record)
                else:
                    errors.append(f"Row {row_num}: No valid data beyond BLS number")
                
            except Exception as e:
                errors.append(f"Row {row_num}: {str(e)}")
        
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
        """Extract nutrient values from row, handling German number format"""
        nutrients = {}
        
        # Define known numeric columns to avoid string column contamination
        numeric_columns = {
            'GCAL', 'GJ', 'GCALZB', 'GJZB', 'ZW', 'ZE', 'ZF', 'ZK', 'ZB', 'ZM', 'ZO', 'ZA',
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
        }
        
        for col_name in numeric_columns:
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
































