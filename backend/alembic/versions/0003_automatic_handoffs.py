"""Replace the demo token handoff with automatic technician assignment."""

from alembic import op

revision = "0003_automatic_handoffs"
down_revision = "0002_conversation_observability"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE tickets RENAME TO legacy_tickets")
    op.execute("ALTER TABLE handoffs RENAME TO legacy_handoffs")
    op.execute("""
    CREATE TABLE handoffs (
      id uuid PRIMARY KEY,
      conversation_id uuid NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
      reason text NOT NULL CHECK (reason IN ('cliente_pediu','baixa_confianca','falha_nao_resolvida')),
      summary text NOT NULL,
      status text NOT NULL DEFAULT 'waiting' CHECK (status IN ('waiting','assigned','closed')),
      technician_id bigint REFERENCES users(id) ON DELETE SET NULL,
      created_at timestamptz NOT NULL DEFAULT now(),
      assigned_at timestamptz,
      closed_at timestamptz,
      resolution_note text,
      CHECK ((status='waiting' AND technician_id IS NULL AND assigned_at IS NULL AND closed_at IS NULL)
          OR (status='assigned' AND technician_id IS NOT NULL AND assigned_at IS NOT NULL AND closed_at IS NULL)
          OR (status='closed' AND closed_at IS NOT NULL))
    );
    CREATE UNIQUE INDEX uq_handoffs_active_conversation
      ON handoffs(conversation_id) WHERE status <> 'closed';
    CREATE INDEX ix_handoffs_status_created ON handoffs(status,created_at,id);
    CREATE INDEX ix_handoffs_technician_status ON handoffs(technician_id,status,assigned_at);
    CREATE INDEX ix_handoffs_created_at ON handoffs(created_at DESC);
    """)


def downgrade():
    op.execute("DROP TABLE IF EXISTS handoffs")
    op.execute("ALTER TABLE legacy_handoffs RENAME TO handoffs")
    op.execute("ALTER TABLE legacy_tickets RENAME TO tickets")
