"""Create the challenge baseline and Phase 1 tables."""

from alembic import op

revision = "0001_phase1_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # Idempotent so databases created by the old SQL bootstrap can be adopted.
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("""
    CREATE TABLE IF NOT EXISTS customers (
      id text PRIMARY KEY, display_name text NOT NULL, plan text NOT NULL,
      demo boolean NOT NULL DEFAULT true
    );
    ALTER TABLE customers ADD COLUMN IF NOT EXISTS external_id text;
    ALTER TABLE customers ADD COLUMN IF NOT EXISTS nome text;
    ALTER TABLE customers ADD COLUMN IF NOT EXISTS contato text;
    UPDATE customers SET external_id=id WHERE external_id IS NULL;
    UPDATE customers SET nome=display_name WHERE nome IS NULL;
    ALTER TABLE customers ALTER COLUMN external_id SET NOT NULL;
    ALTER TABLE customers ALTER COLUMN nome SET NOT NULL;
    CREATE UNIQUE INDEX IF NOT EXISTS uq_customers_external_id ON customers(external_id);

    CREATE TABLE IF NOT EXISTS machine_models (
      id bigserial PRIMARY KEY, name text UNIQUE NOT NULL, is_active boolean NOT NULL DEFAULT true,
      created_at timestamptz NOT NULL DEFAULT now()
    );
    CREATE TABLE IF NOT EXISTS terminals (
      id text PRIMARY KEY, customer_id text REFERENCES customers(id), model text NOT NULL,
      connection_status text NOT NULL, last_error text, updated_at timestamptz DEFAULT now()
    );
    ALTER TABLE terminals ADD COLUMN IF NOT EXISTS model_id bigint REFERENCES machine_models(id);
    ALTER TABLE terminals ADD COLUMN IF NOT EXISTS status text;
    ALTER TABLE terminals ADD COLUMN IF NOT EXISTS last_seen_at timestamptz;
    UPDATE terminals SET status=connection_status WHERE status IS NULL;

    CREATE TABLE IF NOT EXISTS receivables (
      id text PRIMARY KEY, customer_id text REFERENCES customers(id), sale_date date NOT NULL,
      expected_date date NOT NULL, amount numeric(12,2) NOT NULL,
      currency text NOT NULL DEFAULT 'BRL', status text NOT NULL
    );
    CREATE TABLE IF NOT EXISTS users (
      id bigserial PRIMARY KEY, username text NOT NULL, password_hash text NOT NULL,
      role text NOT NULL CHECK (role IN ('admin','tecnico')),
      display_name text NOT NULL, is_active boolean NOT NULL DEFAULT true,
      created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
    );
    CREATE UNIQUE INDEX IF NOT EXISTS uq_users_username_lower ON users(lower(username));
    CREATE TABLE IF NOT EXISTS technician_presence (
      user_id bigint PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
      status text NOT NULL DEFAULT 'offline' CHECK (status IN ('online','pausa','offline')),
      last_seen_at timestamptz, last_assigned_at timestamptz
    );
    CREATE TABLE IF NOT EXISTS audit_logs (
      id bigserial PRIMARY KEY, actor_id bigint REFERENCES users(id) ON DELETE SET NULL,
      action text NOT NULL, entity text NOT NULL, entity_id text,
      diff jsonb NOT NULL DEFAULT '{}'::jsonb, created_at timestamptz NOT NULL DEFAULT now()
    );
    CREATE TABLE IF NOT EXISTS documents (
      id bigserial PRIMARY KEY, url text UNIQUE NOT NULL, title text NOT NULL, country text NOT NULL,
      language text NOT NULL, content_hash text NOT NULL, fetched_at timestamptz NOT NULL DEFAULT now(),
      embedding_model text NOT NULL
    );
    CREATE TABLE IF NOT EXISTS chunks (
      id bigserial PRIMARY KEY, document_id bigint NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
      position integer NOT NULL, content text NOT NULL, embedding vector(1536) NOT NULL,
      UNIQUE(document_id, position)
    );
    CREATE TABLE IF NOT EXISTS requests (
      id uuid PRIMARY KEY, customer_id text REFERENCES customers(id), route text NOT NULL,
      status text NOT NULL, latency_ms integer NOT NULL, agents jsonb NOT NULL,
      created_at timestamptz DEFAULT now()
    );
    CREATE TABLE IF NOT EXISTS usage_daily (
      day date NOT NULL, kind text NOT NULL, calls integer NOT NULL DEFAULT 0,
      input_tokens bigint NOT NULL DEFAULT 0, output_tokens bigint NOT NULL DEFAULT 0,
      PRIMARY KEY(day,kind)
    );
    -- Preserved legacy challenge tables; Phase 1 does not expand their model.
    CREATE TABLE IF NOT EXISTS handoffs (
      token text PRIMARY KEY, customer_id text NOT NULL REFERENCES customers(id), summary text NOT NULL,
      created_at timestamptz DEFAULT now(), expires_at timestamptz NOT NULL
    );
    CREATE TABLE IF NOT EXISTS tickets (
      id text PRIMARY KEY, handoff_token text UNIQUE NOT NULL REFERENCES handoffs(token),
      customer_id text NOT NULL REFERENCES customers(id), summary text NOT NULL,
      status text NOT NULL DEFAULT 'open_demo', created_at timestamptz DEFAULT now()
    );
    """)


def downgrade():
    pass
