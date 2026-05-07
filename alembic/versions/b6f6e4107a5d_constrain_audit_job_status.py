"""constrain audit job status

Revision ID: b6f6e4107a5d
Revises: 9d2d6d6a4c3b
Create Date: 2026-05-06 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b6f6e4107a5d"
down_revision: Union[str, Sequence[str], None] = "9d2d6d6a4c3b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

AUDIT_JOB_STATUS_CHECK = "status IN ('pending', 'running', 'completed', 'failed')"


def upgrade() -> None:
    op.execute("UPDATE audit_jobs SET status = 'completed' WHERE status = 'complete'")
    op.execute("UPDATE audit_jobs SET status = 'pending' WHERE status IS NULL")
    op.alter_column(
        "audit_jobs",
        "status",
        existing_type=sa.Text(),
        nullable=False,
        server_default=sa.text("'pending'"),
    )
    op.create_check_constraint(
        "ck_audit_jobs_status",
        "audit_jobs",
        AUDIT_JOB_STATUS_CHECK,
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_audit_jobs_status",
        "audit_jobs",
        type_="check",
    )
    op.alter_column(
        "audit_jobs",
        "status",
        existing_type=sa.Text(),
        nullable=True,
        server_default=None,
    )
