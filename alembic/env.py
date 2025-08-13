import os
from logging.config import fileConfig
from alembic import context
from sqlalchemy import engine_from_config, pool
from dotenv import load_dotenv

# Load environment variables first
load_dotenv()

# Import models to ensure metadata is loaded
from app import models
from app.database import Base

# Alembic Config object
config = context.config

# Setup logging if config file exists
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Target metadata for autogenerate support
target_metadata = Base.metadata

# Get database URL with fallback and async->sync conversion
db_url = (
    os.getenv("ALEMBIC_DATABASE_URL") or 
    (os.getenv("DATABASE_URL") or "").replace("+asyncpg", "+psycopg2")
)

if not db_url:
    raise RuntimeError("ALEMBIC_DATABASE_URL or DATABASE_URL must be set")


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
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
    """Run migrations in 'online' mode."""
    connectable = engine_from_config(
        {"sqlalchemy.url": db_url},
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        future=True,
    )
    
    with connectable.connect() as connection:
        context.configure(
            connection=connection, 
            target_metadata=target_metadata, 
            compare_type=True
        )
        
        with context.begin_transaction():
            context.run_migrations()


# Run appropriate migration mode
if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

