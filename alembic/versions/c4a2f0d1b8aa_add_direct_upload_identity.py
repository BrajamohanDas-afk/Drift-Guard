"""add direct upload identity

Revision ID: c4a2f0d1b8aa
Revises: b6f6e4107a5d
Create Date: 2026-05-06 00:05:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c4a2f0d1b8aa"
down_revision: Union[str, Sequence[str], None] = "b6f6e4107a5d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE documents
        SET path = title
        WHERE source_id IS NULL
          AND path IS NULL
        """
    )
    op.create_index(
        "ix_documents_direct_path_active",
        "documents",
        ["path"],
        unique=True,
        postgresql_where=sa.text(
            "source_id IS NULL AND path IS NOT NULL AND is_deleted = false"
        ),
    )


def downgrade() -> None:
    op.drop_index("ix_documents_direct_path_active", table_name="documents")
    op.execute(
        """
        UPDATE documents
        SET path = NULL
        WHERE source_id IS NULL
        """
    )
