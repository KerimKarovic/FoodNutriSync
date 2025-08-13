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
    
    async def search_by_name(self, session: AsyncSession, name: str, limit: int = 50) -> BLSSearchResponse:
        """Search BLS entries by German name"""
        if not name or not name.strip():
            return BLSSearchResponse(results=[], count=0)
        
        search_term = f"%{name.strip().lower()}%"
        stmt = select(BLSNutrition).where(BLSNutrition.name_german.ilike(search_term)).limit(limit)
        
        result = await session.execute(stmt)
        items = result.scalars().all()
        
        results = [BLSNutrientResponse.from_orm_obj(item) for item in items]
        return BLSSearchResponse(results=results, count=len(results))
    
    async def upload_data(self, session: AsyncSession, df: pd.DataFrame, filename: str) -> BLSUploadResponse:
        """Process and upload BLS data from DataFrame"""
        validator = BLSDataValidator()
        valid_records, errors = validator.validate_dataframe(df, filename)
        
        added_count = await self._bulk_upsert(session, valid_records) if valid_records else 0
        
        return BLSUploadResponse(
            added=added_count,
            updated=0,  # Simplified for now
            failed=len(errors),
            errors=errors[:10]  # Limit error messages
        )
    
    async def _bulk_upsert(self, session: AsyncSession, records: List[dict]) -> int:
        """Perform bulk upsert operation"""
        print(f"DEBUG: About to insert {len(records)} records")
        for i, record in enumerate(records[:2]):  # Show first 2 records
            print(f"DEBUG: Record {i}: {record}")
            for key, value in record.items():
                print(f"  {key}: {value} (type: {type(value)})")
        
        stmt = insert(BLSNutrition).values(records)
        upsert_stmt = stmt.on_conflict_do_update(
            index_elements=['SBLS'],  # Use actual DB column name, not 'bls_number'
            set_={col.name: stmt.excluded[col.name] 
                  for col in BLSNutrition.__table__.columns 
                  if col.name != 'SBLS'}  # Exclude primary key column
        )
        
        await session.execute(upsert_stmt)
        await session.commit()
        return len(records)


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
        
        # Debug: Print column names and first few rows
        print(f"DEBUG: DataFrame columns: {list(df.columns)}")
        print(f"DEBUG: DataFrame shape: {df.shape}")
        if len(df) > 0:
            print(f"DEBUG: First row: {df.iloc[0].to_dict()}")
        
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
            
        print(f"DEBUG: BLS value: {bls_value}")
        
        if pd.isna(bls_value):
            return None
        
        bls_value = str(bls_value).strip()
        print(f"DEBUG: Cleaned BLS value: '{bls_value}'")
        result = self.BLS_PATTERN.match(bls_value)
        print(f"DEBUG: Pattern match result: {result}")
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
                                print(f"DEBUG: Added nutrient {col_name} = {float_val} (type: {type(float_val)})")
                    except (ValueError, TypeError) as e:
                        print(f"DEBUG: Failed to convert {col_name} = '{value}': {e}")
                        continue
        
        return nutrients





























