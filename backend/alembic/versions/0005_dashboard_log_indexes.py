"""Add indexes for administrative logs and dashboard queries."""

from alembic import op

revision = "0005_dashboard_log_indexes"
down_revision = "0004_rag_documents"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
    CREATE INDEX IF NOT EXISTS ix_tool_calls_name_created
      ON tool_calls(tool_name,created_at DESC);
    CREATE INDEX IF NOT EXISTS ix_handoffs_created_status
      ON handoffs(created_at DESC,status);
    CREATE INDEX IF NOT EXISTS ix_handoffs_technician_created
      ON handoffs(technician_id,created_at DESC);
    CREATE INDEX IF NOT EXISTS ix_messages_sender_created
      ON messages(sender_type,created_at DESC);
    """)


def downgrade():
    op.execute("""
    DROP INDEX IF EXISTS ix_messages_sender_created;
    DROP INDEX IF EXISTS ix_handoffs_technician_created;
    DROP INDEX IF EXISTS ix_handoffs_created_status;
    DROP INDEX IF EXISTS ix_tool_calls_name_created;
    """)
