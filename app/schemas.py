from pydantic import BaseModel, Field
from typing import Dict, Any, Optional, List

class BLSNutrientResponse(BaseModel):
    bls_number: str
    name_german: str
    nutrients: Dict[str, Optional[float]] = Field(default_factory=dict)
    
    @classmethod
    def from_orm_obj(cls, orm_obj):
        nutrients = {}
        for column in orm_obj.__table__.columns:
            if column.name not in ['SBLS', 'ST']:  # Use DB column names for exclusion
                value = getattr(orm_obj, column.name.lower(), None)
                if value is not None:
                    # Return UPPERCASE nutrient keys (BLS standard)
                    nutrients[column.name] = value
        
        return cls(
            bls_number=orm_obj.bls_number,  # Use Python attribute name
            name_german=orm_obj.name_german,  # Use Python attribute name
            nutrients=nutrients
        )

class BLSSearchResponse(BaseModel):
    results: list[BLSNutrientResponse]
    count: int

class BLSUploadResponse(BaseModel):
    added: int
    updated: int
    failed: int
    errors: list[str] = Field(default_factory=list)

class ArticleImportResult(BaseModel):
    article_id: str
    bls_number: str
    status: str  # "success" or "failed"
    nutrients: Optional[Dict[str, Optional[float]]] = None
    error: Optional[str] = None

class BulkImportResponse(BaseModel):
    processed: int
    successful: int
    failed: int
    results: List[ArticleImportResult]
