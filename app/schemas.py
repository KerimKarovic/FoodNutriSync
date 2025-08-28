from pydantic import BaseModel
from typing import Optional, List, Dict

class BLSSearchResult(BaseModel):
    """Single BLS search result"""
    sbls: str
    name: str
    enerc: Optional[float] = None  # Energy content
    
    class Config:
        from_attributes = True

class BLSNutrientResponse(BaseModel):
    """Full BLS nutrient data response"""
    bls_number: str
    name_german: str
    name_english: Optional[str] = None
    nutrients: Dict[str, Optional[float]] = {}
    
    @classmethod
    def from_orm_obj(cls, obj):
        """Convert SQLAlchemy model to response"""
        return cls(
            bls_number=obj.bls_number,
            name_german=obj.name_german,
            name_english=obj.name_english,
            nutrients={}  # Add nutrient extraction logic here
        )
    
    class Config:
        from_attributes = True

class BLSSearchResponse(BaseModel):
    """Search results with metadata"""
    results: List[BLSNutrientResponse]
    count: int

class BLSUploadResponse(BaseModel):
    """Response from BLS data upload"""
    added: int
    updated: int
    failed: int
    errors: List[str]

