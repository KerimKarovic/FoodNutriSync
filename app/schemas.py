from pydantic import BaseModel, Field
from typing import Dict, Any, Optional

class BLSNutrientResponse(BaseModel):
    bls_number: str
    name_german: str
    nutrients: Dict[str, Optional[float]] = Field(default_factory=dict)
    
    @classmethod
    def from_orm_obj(cls, orm_obj):
        nutrients = {}
        for column in orm_obj.__table__.columns:
            if column.name not in ['bls_number', 'name_german']:
                value = getattr(orm_obj, column.name.lower(), None)
                if value is not None:
                    # Return UPPERCASE nutrient keys (BLS standard)
                    nutrients[column.name] = value
        
        return cls(
            bls_number=orm_obj.bls_number,
            name_german=orm_obj.name_german,
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

