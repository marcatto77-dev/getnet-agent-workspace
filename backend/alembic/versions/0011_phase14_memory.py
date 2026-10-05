"""Conversation memory and degraded-RAG state."""
from alembic import op

revision = "0011_phase14_memory"
down_revision = "0010_phase13_security"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
    ALTER TABLE conversations ADD COLUMN IF NOT EXISTS memory_summary text NOT NULL DEFAULT '';
    ALTER TABLE conversations ADD COLUMN IF NOT EXISTS memory_message_count integer NOT NULL DEFAULT 0;
    CREATE TABLE IF NOT EXISTS app_runtime_state (
      key text PRIMARY KEY,
      value jsonb NOT NULL DEFAULT '{}'::jsonb,
      updated_at timestamptz NOT NULL DEFAULT now()
    );
    """)


def downgrade():
    op.execute("DROP TABLE IF EXISTS app_runtime_state")
    op.execute("ALTER TABLE conversations DROP COLUMN IF EXISTS memory_message_count")
    op.execute("ALTER TABLE conversations DROP COLUMN IF EXISTS memory_summary")
