"""Expiring per-tab authenticated presence, independent from technician availability."""

from alembic import op

revision = "0015_presence_leases"
down_revision = "0014_rag_review"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
    CREATE TABLE user_presence_sessions (
      user_id integer NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      session_id uuid NOT NULL,
      token_version integer NOT NULL,
      last_seen_at timestamptz NOT NULL DEFAULT now(),
      PRIMARY KEY (user_id,session_id)
    );
    CREATE INDEX user_presence_seen_idx ON user_presence_sessions(last_seen_at);
    """)


def downgrade():
    op.execute("DROP TABLE user_presence_sessions")
