"""Update constraints and indexes for PostgreSQL

Revision ID: 44e4250f8faa
Revises: 875fef496f62
Create Date: 2025-08-13 12:22:50.291590

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '44e4250f8faa'
down_revision: Union[str, Sequence[str], None] = '875fef496f62'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    # 0) ensure pg_trgm once
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm;")

    # 1) RENAME existing columns to match BLS physical names (preserves data)
    #    Only rename if the old names exist.
    op.execute("""
    DO $$
    BEGIN
        IF EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_name='bls_nutrition' AND column_name='bls_number'
        ) THEN
            EXECUTE 'ALTER TABLE bls_nutrition RENAME COLUMN bls_number TO "SBLS"';
        END IF;

        IF EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_name='bls_nutrition' AND column_name='name_german'
        ) THEN
            EXECUTE 'ALTER TABLE bls_nutrition RENAME COLUMN name_german TO "ST"';
        END IF;
    END $$;
    """)

    # 2) Add STE (English name) if missing
    op.execute('ALTER TABLE bls_nutrition ADD COLUMN IF NOT EXISTS "STE" TEXT;')

    # 3) Add/ensure the BLS code format check on SBLS
    op.execute("""
    DO $$
    BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM pg_constraint
            WHERE conname='ck_bls_number_format'
              AND conrelid='bls_nutrition'::regclass
        ) THEN
            EXECUTE 'ALTER TABLE bls_nutrition
                     ADD CONSTRAINT ck_bls_number_format
                     CHECK ("SBLS" ~ ''^[B-Y][0-9]{6}$'')';
        END IF;
    END $$;
    """)

    # 4) Drop any btree/legacy indexes autogenerate may have added or that existed before
    op.execute('DROP INDEX IF EXISTS ix_bls_nutrition_SBLS;')
    op.execute('DROP INDEX IF EXISTS ix_bls_nutrition_ST;')
    op.execute('DROP INDEX IF EXISTS ix_bls_nutrition_STE;')
    op.execute('DROP INDEX IF EXISTS bls_name_lower_idx;')
    op.execute('DROP INDEX IF EXISTS ix_bls_nutrition_bls_number;')

    # 5) Create trigram GIN indexes on physical columns ST / STE
    op.execute('CREATE INDEX IF NOT EXISTS ix_blsnutrition_ST_trgm  ON bls_nutrition USING gin ("ST"  gin_trgm_ops);')
    op.execute('CREATE INDEX IF NOT EXISTS ix_blsnutrition_STE_trgm ON bls_nutrition USING gin ("STE" gin_trgm_ops);')


def downgrade():
    # drop trigram indexes
    op.execute('DROP INDEX IF EXISTS ix_blsnutrition_STE_trgm;')
    op.execute('DROP INDEX IF EXISTS ix_blsnutrition_ST_trgm;')

    # drop constraint
    op.execute("""
    DO $$
    BEGIN
        IF EXISTS (
            SELECT 1 FROM pg_constraint
            WHERE conname='ck_bls_number_format'
              AND conrelid='bls_nutrition'::regclass
        ) THEN
            EXECUTE 'ALTER TABLE bls_nutrition DROP CONSTRAINT ck_bls_number_format';
        END IF;
    END $$;
    """)

    # optional: rename back (only if you truly need to revert)
    op.execute("""
    DO $$
    BEGIN
        IF EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_name='bls_nutrition' AND column_name='ST'
        ) THEN
            EXECUTE 'ALTER TABLE bls_nutrition RENAME COLUMN "ST" TO name_german';
        END IF;

        IF EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_name='bls_nutrition' AND column_name='SBLS'
        ) THEN
            EXECUTE 'ALTER TABLE bls_nutrition RENAME COLUMN "SBLS" TO bls_number';
        END IF;

        -- If you must, you can drop STE here:
        -- EXECUTE 'ALTER TABLE bls_nutrition DROP COLUMN IF EXISTS "STE"';
    END $$;
    """)