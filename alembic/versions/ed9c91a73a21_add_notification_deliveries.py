"""add notification deliveries

Revision ID: ed9c91a73a21
Revises: d8f3c6a92b11
Create Date: 2026-05-09 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "ed9c91a73a21"
down_revision: Union[str, Sequence[str], None] = "d8f3c6a92b11"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "notification_deliveries",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("audit_job_id", sa.UUID(), nullable=True),
        sa.Column("alert_id", sa.UUID(), nullable=True),
        sa.Column("idempotency_key", sa.Text(), nullable=False),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("channel", sa.Text(), nullable=False),
        sa.Column("target", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('pending', 'sending', 'delivered', 'failed')",
            name="ck_notification_deliveries_status",
        ),
        sa.CheckConstraint(
            "channel IN ('slack', 'email', 'completion_webhook')",
            name="ck_notification_deliveries_channel",
        ),
        sa.CheckConstraint(
            "event_type IN ('alert_created', 'audit_completed')",
            name="ck_notification_deliveries_event_type",
        ),
        sa.CheckConstraint(
            "attempts >= 0 AND attempts <= 5",
            name="ck_notification_deliveries_attempts_range",
        ),
        sa.CheckConstraint(
            "alert_id IS NOT NULL OR audit_job_id IS NOT NULL",
            name="ck_notification_deliveries_parent_present",
        ),
        sa.ForeignKeyConstraint(["alert_id"], ["alerts.id"]),
        sa.ForeignKeyConstraint(["audit_job_id"], ["audit_jobs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_notification_deliveries_idempotency_key",
        "notification_deliveries",
        ["idempotency_key"],
        unique=True,
    )
    op.create_index(
        "ix_notification_deliveries_audit_status_created",
        "notification_deliveries",
        ["audit_job_id", "status", "created_at"],
    )
    op.create_index(
        "ix_notification_deliveries_alert_channel",
        "notification_deliveries",
        ["alert_id", "channel"],
    )


def downgrade() -> None:
    op.drop_index(
        "uq_notification_deliveries_idempotency_key",
        table_name="notification_deliveries",
    )
    op.drop_index(
        "ix_notification_deliveries_alert_channel",
        table_name="notification_deliveries",
    )
    op.drop_index(
        "ix_notification_deliveries_audit_status_created",
        table_name="notification_deliveries",
    )
    op.drop_table("notification_deliveries")
