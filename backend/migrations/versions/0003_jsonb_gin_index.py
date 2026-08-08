"""Add GIN index on triage_messages.restriction_log for admin stats queries

Revision ID: 0003
Revises: 0002
Create Date: 2025-01-01 00:02:00
"""
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # GIN index enables fast jsonb key/value lookups used by admin restriction stats
    # CONCURRENTLY: does not lock the table during index creation (important on live DB)
    op.execute(
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_messages_restriction_log "
        "ON triage_messages USING gin (restriction_log)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_messages_restriction_log")
