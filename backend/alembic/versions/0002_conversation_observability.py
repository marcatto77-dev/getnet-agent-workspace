"""Persist conversations, messages and agent execution telemetry."""

from alembic import op

revision = "0002_conversation_observability"
down_revision = "0001_phase1_schema"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
    CREATE TABLE conversations (
      id uuid PRIMARY KEY,
      customer_id text NOT NULL REFERENCES customers(id),
      status text NOT NULL DEFAULT 'ai' CHECK (status IN ('ai','waiting','with_technician','closed')),
      started_at timestamptz NOT NULL DEFAULT now(),
      closed_at timestamptz,
      CHECK ((status='closed' AND closed_at IS NOT NULL) OR (status<>'closed' AND closed_at IS NULL))
    );
    CREATE UNIQUE INDEX uq_conversations_active_customer
      ON conversations(customer_id) WHERE status <> 'closed';
    CREATE INDEX ix_conversations_started_at ON conversations(started_at DESC);
    CREATE INDEX ix_conversations_customer_status ON conversations(customer_id,status);

    CREATE TABLE messages (
      id uuid PRIMARY KEY,
      conversation_id uuid NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
      sender_type text NOT NULL CHECK (sender_type IN ('customer','ai','technician','system')),
      sender_id text,
      content text NOT NULL,
      created_at timestamptz NOT NULL DEFAULT now()
    );
    CREATE INDEX ix_messages_conversation_created ON messages(conversation_id,created_at);
    CREATE INDEX ix_messages_created_at ON messages(created_at DESC);

    CREATE TABLE agent_runs (
      id uuid PRIMARY KEY,
      request_id uuid UNIQUE NOT NULL,
      conversation_id uuid NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
      user_id text NOT NULL,
      route text NOT NULL,
      agents_used jsonb NOT NULL DEFAULT '[]'::jsonb,
      status text NOT NULL,
      latency_ms integer NOT NULL,
      tokens jsonb NOT NULL DEFAULT '{}'::jsonb,
      cost numeric(12,6),
      error text,
      created_at timestamptz NOT NULL DEFAULT now()
    );
    CREATE INDEX ix_agent_runs_created_at ON agent_runs(created_at DESC);
    CREATE INDEX ix_agent_runs_user_id ON agent_runs(user_id,created_at DESC);
    CREATE INDEX ix_agent_runs_route ON agent_runs(route,created_at DESC);
    CREATE INDEX ix_agent_runs_status ON agent_runs(status,created_at DESC);

    CREATE TABLE tool_calls (
      id bigserial PRIMARY KEY,
      agent_run_id uuid NOT NULL REFERENCES agent_runs(id) ON DELETE CASCADE,
      tool_name text NOT NULL,
      input_summary text NOT NULL,
      output_summary text NOT NULL,
      success boolean NOT NULL,
      latency_ms integer NOT NULL,
      created_at timestamptz NOT NULL DEFAULT now()
    );
    CREATE INDEX ix_tool_calls_run_created ON tool_calls(agent_run_id,created_at);
    CREATE INDEX ix_tool_calls_created_at ON tool_calls(created_at DESC);
    CREATE INDEX ix_tool_calls_success ON tool_calls(success,created_at DESC);
    """)


def downgrade():
    op.execute("DROP TABLE IF EXISTS tool_calls")
    op.execute("DROP TABLE IF EXISTS agent_runs")
    op.execute("DROP TABLE IF EXISTS messages")
    op.execute("DROP TABLE IF EXISTS conversations")
