"""add preview_uri to layers

Revision ID: 94b35cb3e2df
Revises: ef62d4b56782
Create Date: 2026-09-12 17:03:44.843568

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '94b35cb3e2df'
down_revision: Union[str, Sequence[str], None] = 'ef62d4b56782'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('layers', sa.Column('preview_uri', sa.String(length=1024), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('layers', 'preview_uri')
