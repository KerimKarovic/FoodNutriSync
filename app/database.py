# app/database.py
import os
from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from typing import AsyncGenerator

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")  # e.g. postgresql+asyncpg://user:pass@host:5432/db
if not DATABASE_URL:
    raise ValueError("DATABASE_URL environment variable is not set.")

engine = create_async_engine(DATABASE_URL, future=True, echo=False)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

Base = declarative_base()

async def get_session():
    async with SessionLocal() as session:
        yield session
