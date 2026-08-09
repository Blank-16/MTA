"""initial schema

Revision ID: 0001
Revises:
Create Date: 2025-01-01 00:00:00
"""

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')

    op.execute("""
        CREATE TABLE guidelines (
            id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            content         TEXT NOT NULL,
            embedding       VECTOR(1536) NOT NULL,
            source          TEXT NOT NULL,
            section         TEXT NOT NULL,
            jurisdiction    TEXT NOT NULL DEFAULT 'global',
            confidence_tier TEXT NOT NULL CHECK (confidence_tier IN ('high', 'moderate', 'low')),
            last_reviewed   DATE NOT NULL DEFAULT CURRENT_DATE,
            metadata        JSONB DEFAULT '{}'::jsonb,
            created_at      TIMESTAMPTZ DEFAULT NOW()
        )
    """)

    # HNSW index: faster approximate nearest-neighbour than IVFFlat for < 1M vectors
    op.execute("""
        CREATE INDEX idx_guidelines_embedding ON guidelines
        USING hnsw (embedding vector_cosine_ops)
        WITH (m = 16, ef_construction = 64)
    """)

    op.execute("""
        CREATE TABLE triage_sessions (
            id                UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            session_token     TEXT UNIQUE NOT NULL,
            user_id           UUID,
            created_at        TIMESTAMPTZ DEFAULT NOW(),
            ended_at          TIMESTAMPTZ,
            escalated         BOOLEAN DEFAULT FALSE,
            escalation_reason TEXT,
            restriction_hits  JSONB DEFAULT '[]'::jsonb,
            audit_trail       JSONB DEFAULT '[]'::jsonb
        )
    """)

    op.execute("""
        CREATE TABLE triage_messages (
            id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            session_id      UUID NOT NULL REFERENCES triage_sessions(id) ON DELETE CASCADE,
            role            TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
            content         TEXT NOT NULL,
            citations       JSONB DEFAULT '[]'::jsonb,
            confidence      TEXT CHECK (confidence IN ('high', 'moderate', 'low')),
            model_version   TEXT,
            restriction_log JSONB DEFAULT '{}'::jsonb,
            created_at      TIMESTAMPTZ DEFAULT NOW()
        )
    """)

    # Index for fast per-session message lookup
    op.execute("CREATE INDEX idx_triage_messages_session ON triage_messages (session_id, created_at DESC)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_triage_messages_session")
    op.execute("DROP TABLE IF EXISTS triage_messages")
    op.execute("DROP TABLE IF EXISTS triage_sessions")
    op.execute("DROP INDEX IF EXISTS idx_guidelines_embedding")
    op.execute("DROP TABLE IF EXISTS guidelines")

# Note: Migration for GIN index on restriction_log jsonb column lives in a
# separate file to keep initial schema lean. Add when admin stats queries become slow:
# CREATE INDEX idx_messages_restriction_log ON triage_messages USING gin (restriction_log);
