"""users, refresh tokens, RLS append-only audit

Revision ID: 0002
Revises: 0001
Create Date: 2025-01-01 00:01:00
"""

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Users ──────────────────────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE users (
            id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            email           TEXT UNIQUE NOT NULL,
            hashed_password TEXT NOT NULL,
            is_active       BOOLEAN NOT NULL DEFAULT TRUE,
            created_at      TIMESTAMPTZ DEFAULT NOW(),
            last_login      TIMESTAMPTZ
        )
    """)
    op.execute("CREATE INDEX idx_users_email ON users (email)")

    # ── Refresh tokens ─────────────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE refresh_tokens (
            id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            token_hash  TEXT UNIQUE NOT NULL,
            expires_at  TIMESTAMPTZ NOT NULL,
            revoked     BOOLEAN NOT NULL DEFAULT FALSE,
            created_at  TIMESTAMPTZ DEFAULT NOW(),
            user_agent  TEXT,
            ip_address  TEXT
        )
    """)
    op.execute("CREATE INDEX idx_refresh_tokens_user ON refresh_tokens (user_id, revoked)")
    op.execute("CREATE INDEX idx_refresh_tokens_hash ON refresh_tokens (token_hash)")

    # ── Add user_id FK to triage_sessions ──────────────────────────────────────
    op.execute("""
        ALTER TABLE triage_sessions
        ADD CONSTRAINT fk_sessions_user
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
    """)

    # ── Append-only RLS on triage_messages ─────────────────────────────────────
    # Creates a dedicated role that can only INSERT/SELECT — never UPDATE/DELETE.
    # The application connects as this role; only a superuser can mutate audit records.
    op.execute("CREATE ROLE triage_app_role")
    op.execute("DO $$ BEGIN EXECUTE 'GRANT CONNECT ON DATABASE ' || current_database() || ' TO triage_app_role'; END $$")
    op.execute("GRANT USAGE ON SCHEMA public TO triage_app_role")
    op.execute("GRANT SELECT, INSERT ON triage_messages TO triage_app_role")
    op.execute("GRANT SELECT, INSERT, UPDATE ON triage_sessions TO triage_app_role")
    op.execute("GRANT SELECT, INSERT ON guidelines TO triage_app_role")
    op.execute("GRANT SELECT, INSERT ON users TO triage_app_role")
    op.execute("GRANT SELECT, INSERT, UPDATE ON refresh_tokens TO triage_app_role")

    # Row-level security: enables RLS policy enforcement at DB level
    op.execute("ALTER TABLE triage_messages ENABLE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY triage_messages_append_only ON triage_messages
        AS RESTRICTIVE
        FOR ALL
        USING (true)
        WITH CHECK (true)
    """)
    # DELETE is not granted to triage_app_role — enforced at permission level, not policy


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS triage_messages_append_only ON triage_messages")
    op.execute("ALTER TABLE triage_messages DISABLE ROW LEVEL SECURITY")
    op.execute("DROP ROLE IF EXISTS triage_app_role")
    op.execute("ALTER TABLE triage_sessions DROP CONSTRAINT IF EXISTS fk_sessions_user")
    op.execute("DROP TABLE IF EXISTS refresh_tokens")
    op.execute("DROP TABLE IF EXISTS users")
