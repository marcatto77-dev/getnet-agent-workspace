"""Persist terminal selection and clarification state for customer conversations."""
from alembic import op

revision = "0008_phase11_customer_portal"
down_revision = "0007_phase10_customer_accounts"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
    ALTER TABLE conversations ADD COLUMN IF NOT EXISTS selected_terminal_id text REFERENCES terminals(id) ON DELETE SET NULL;
    ALTER TABLE conversations ADD COLUMN IF NOT EXISTS pending_terminal_selection boolean NOT NULL DEFAULT false;
    CREATE INDEX IF NOT EXISTS ix_conversations_selected_terminal ON conversations(selected_terminal_id);
    """)


def downgrade():
    op.execute("""
    DROP INDEX IF EXISTS ix_conversations_selected_terminal;
    ALTER TABLE conversations DROP COLUMN IF EXISTS pending_terminal_selection;
    ALTER TABLE conversations DROP COLUMN IF EXISTS selected_terminal_id;
    """)
