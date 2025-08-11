import os
from logging.config import fileConfig
from alembic import context
from sqlalchemy import engine_from_config, pool
from dotenv import load_dotenv
from app import models

load_dotenv()

from app.database import Base
# ensure metadata is loaded

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# Get a sync URL for Alembic
db_url = os.getenv("ALEMBIC_DATABASE_URL") or (os.getenv("DATABASE_URL") or "").replace("+asyncpg", "+psycopg2")
if not db_url:
    raise RuntimeError("ALEMBIC_DATABASE_URL or DATABASE_URL must be set")

def run_migrations_offline() -> None:
    context.configure(
        url=db_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online() -> None:
    # Pass URL directly to avoid ConfigParser interpolation issues
    connectable = engine_from_config(
        {"sqlalchemy.url": db_url},
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        future=True,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
