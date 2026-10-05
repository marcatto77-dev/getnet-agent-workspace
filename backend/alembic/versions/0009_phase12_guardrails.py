"""Persist guardrail decisions and add query indexes."""
from alembic import op

revision = "0009_phase12_guardrails"
down_revision = "0008_phase11_customer_portal"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
    CREATE TABLE IF NOT EXISTS guardrail_events (
      id bigserial PRIMARY KEY,
      request_id uuid NOT NULL,
      conversation_id uuid REFERENCES conversations(id) ON DELETE SET NULL,
      layer varchar(40) NOT NULL,
      rule varchar(100) NOT NULL,
      action varchar(10) NOT NULL CHECK (action IN ('block','redact','allow')),
      severity varchar(20) NOT NULL,
      sample text NOT NULL DEFAULT '',
      created_at timestamptz NOT NULL DEFAULT now()
    );
    CREATE INDEX IF NOT EXISTS ix_guardrail_events_created ON guardrail_events(created_at DESC);
    CREATE INDEX IF NOT EXISTS ix_guardrail_events_request ON guardrail_events(request_id);
    CREATE INDEX IF NOT EXISTS ix_guardrail_events_rule ON guardrail_events(rule,action,created_at DESC);
    """)


def downgrade():
    op.execute("DROP TABLE IF EXISTS guardrail_events")
