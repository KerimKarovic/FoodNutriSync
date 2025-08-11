# app/init_dummy.py
import asyncio
from app.database import SessionLocal
from app.models import BLSNutrition

async def main():
    async with SessionLocal() as session:
        row = BLSNutrition(
            bls_number="M401600",
            name_german="Edamer, vollfett",
            gcal=330.0,    # energy (kcal)
            epro=25.0,     # protein (g)
            vc=0.0,        # vitamin C (mg) - just a sample
            mna=700.0      # sodium (mg) - sample
        )
        session.add(row)
        await session.commit()
    print("Inserted dummy row.")

if __name__ == "__main__":
    asyncio.run(main())
