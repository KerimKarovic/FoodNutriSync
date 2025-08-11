# app/models.py
from sqlalchemy import Column, String
from sqlalchemy.dialects.postgresql import JSONB
from app.database import Base

class BLSNutrition(Base):
    __tablename__ = "bls_nutrition"

    bls_number = Column(String, primary_key=True)      # e.g., M401600
    name_german = Column(String, nullable=True)
    nutrients = Column(JSONB, nullable=False, default=dict)
