"""add path to documents

Revision ID: 3ac45cd3e0fe
Revises: 04c74d378803
Create Date: 2026-03-27 03:50:54.304279

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3ac45cd3e0fe'
down_revision: Union[str, Sequence[str], None] = '04c74d378803'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('documents', sa.Column('path', sa.Text(), nullable=True))
    op.create_index(
        'ix_documents_source_path_active',
        'documents',
        ['source_id', 'path'],
        unique=True,
        postgresql_where=sa.text(
            'source_id IS NOT NULL AND path IS NOT NULL AND is_deleted = false'
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_documents_source_path_active', table_name='documents')
    op.drop_column('documents', 'path')
