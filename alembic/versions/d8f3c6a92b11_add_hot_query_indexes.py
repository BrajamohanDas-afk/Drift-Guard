"""add hot query indexes

Revision ID: d8f3c6a92b11
Revises: c4a2f0d1b8aa
Create Date: 2026-05-07 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d8f3c6a92b11"
down_revision: Union[str, Sequence[str], None] = "c4a2f0d1b8aa"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "ix_alerts_resolution_scope_created",
        "alerts",
        ["resolved", "document_id", "severity", "rule_type", "created_at"],
    )
    op.create_index(
        "ix_runbook_scores_document_scored",
        "runbook_scores",
        ["document_id", "scored_at"],
    )
    op.create_index(
        "ix_entities_version_type_value",
        "entities",
        ["document_version_id", "entity_type", "value"],
    )
    op.create_index(
        "ix_audit_jobs_status_started",
        "audit_jobs",
        ["status", "started_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_audit_jobs_status_started", table_name="audit_jobs")
    op.drop_index("ix_entities_version_type_value", table_name="entities")
    op.drop_index(
        "ix_runbook_scores_document_scored",
        table_name="runbook_scores",
    )
    op.drop_index("ix_alerts_resolution_scope_created", table_name="alerts")
