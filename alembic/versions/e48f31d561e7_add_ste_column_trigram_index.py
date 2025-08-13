"""Add STE column + trigram index

Revision ID: e48f31d561e7
Revises: 44e4250f8faa
Create Date: 2025-08-13 12:32:02.327112

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e48f31d561e7'
down_revision: Union[str, Sequence[str], None] = '44e4250f8faa'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


from alembic import op

def upgrade():
    op.execute('ALTER TABLE bls_nutrition ADD COLUMN IF NOT EXISTS "STE" TEXT;')
    op.execute('CREATE EXTENSION IF NOT EXISTS pg_trgm;')
    op.execute('CREATE INDEX IF NOT EXISTS ix_blsnutrition_STE_trgm '
               'ON bls_nutrition USING gin ("STE" gin_trgm_ops);')


def downgrade() -> None:
    """Downgrade schema."""
    pass
