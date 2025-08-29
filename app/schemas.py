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
        nutrients = {}
        
        # Get all attributes from the SQLAlchemy model
        for column in obj.__table__.columns:
            # Get the SQLAlchemy attribute name (not the database column name)
            attr_name = None
            for attr in dir(obj.__class__):
                if hasattr(obj.__class__, attr):
                    class_attr = getattr(obj.__class__, attr)
                    if hasattr(class_attr, 'property') and hasattr(class_attr.property, 'columns'):
                        if class_attr.property.columns[0] is column:
                            attr_name = attr
                            break
            
            # Skip identification columns and get nutrient values
            if attr_name and attr_name not in ['bls_number', 'name_german', 'name_english']:
                value = getattr(obj, attr_name, None)
                if value is not None:
                    try:
                        nutrients[column.name] = float(value)
                    except (ValueError, TypeError):
                        continue
        
        return cls(
            bls_number=obj.bls_number,
            name_german=obj.name_german,
            name_english=obj.name_english,
            nutrients=nutrients
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

