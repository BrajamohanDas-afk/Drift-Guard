"""add latest version fk to documents

Revision ID: 9d2d6d6a4c3b
Revises: 3ac45cd3e0fe
Create Date: 2026-03-28 05:30:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "9d2d6d6a4c3b"
down_revision: Union[str, Sequence[str], None] = "3ac45cd3e0fe"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_foreign_key(
        "fk_documents_latest_version_id_document_versions",
        "documents",
        "document_versions",
        ["latest_version_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_documents_latest_version_id_document_versions",
        "documents",
        type_="foreignkey",
    )