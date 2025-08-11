# app/init_dummy.py
import asyncio
from sqlalchemy.dialects.postgresql import insert
from app.database import SessionLocal
from app.models import BLSNutrition

async def main():
    # What you'd like to set, using DB column names as seen in Postgres
    wanted = {
        "GCAL": 330.0,
        "EPRO": 25.0,
        "VC": 0.0,
        "MNA": 700.0,
    }

    # Build a safe values dict using the model's actual attribute keys
    # (model keys are often lowercase; DB column names are UPPERCASE)
    values: dict[str, str | float] = {
        "bls_number": "M401600",
        "name_german": "Edamer, vollfett",
    }

    # Maps: DB column name -> SQLA Column; DB column name -> model attribute key
    col_by_dbname = {c.name: c for c in BLSNutrition.__table__.columns}
    key_by_dbname = {c.name: c.name.lower() for c in BLSNutrition.__table__.columns}

    for db_name, val in wanted.items():
        if db_name in key_by_dbname:
            values[key_by_dbname[db_name]] = val  # use model attribute key
        else:
            print(f"[warn] Column {db_name} not found on model; skipping")

    async with SessionLocal() as session:
        stmt = insert(BLSNutrition).values(**values)

        # Build set_ only for columns that really exist on the model
        set_map = {BLSNutrition.name_german: stmt.excluded.name_german}
        for db_name in wanted:
            if db_name in key_by_dbname:
                attr_name = key_by_dbname[db_name]       # e.g., 'gcal' (lowercase)
                set_map[getattr(BLSNutrition, attr_name)] = getattr(stmt.excluded, db_name)

        stmt = stmt.on_conflict_do_update(
            index_elements=[BLSNutrition.bls_number],
            set_=set_map,
        )

        await session.execute(stmt)
        await session.commit()
    print("Upserted dummy row.")

if __name__ == "__main__":
    asyncio.run(main())
