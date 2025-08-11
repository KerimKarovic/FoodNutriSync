from fastapi import FastAPI, HTTPException, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import SessionLocal
from app.models import BLSNutrition
from typing import AsyncGenerator

app = FastAPI(title="FoodNutriSync")

async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session

@app.get("/bls/{bls_number}")
async def get_bls(bls_number: str, session: AsyncSession = Depends(get_session)):
    row = (await session.execute(
        select(BLSNutrition).where(BLSNutrition.bls_number == bls_number)
    )).scalar_one_or_none()
    if not row:
        raise HTTPException(404, "Not found")

    # Build a dict of nutrient fields dynamically (all columns except keys)
    keys = {"bls_number", "name_german"}
    data = {"bls_number": row.bls_number, "name_german": row.name_german}
    for col in row.__table__.columns:
        if col.name not in keys:
            data[col.name] = getattr(row, col.name.lower())  # attribute is lowercase
    return data

@app.get("/")
async def root():
    return {"ok": True}
