CREATE EXTENSION IF NOT EXISTS vector;
CREATE TABLE IF NOT EXISTS schema_versions (version integer PRIMARY KEY, applied_at timestamptz DEFAULT now());
CREATE TABLE IF NOT EXISTS customers (
 id text PRIMARY KEY, display_name text NOT NULL, plan text NOT NULL, demo boolean NOT NULL DEFAULT true
);
CREATE TABLE IF NOT EXISTS terminals (
 id text PRIMARY KEY, customer_id text REFERENCES customers(id), model text NOT NULL,
 connection_status text NOT NULL, last_error text, updated_at timestamptz DEFAULT now()
);
CREATE TABLE IF NOT EXISTS receivables (
 id text PRIMARY KEY, customer_id text REFERENCES customers(id), sale_date date NOT NULL,
 expected_date date NOT NULL, amount numeric(12,2) NOT NULL, currency text NOT NULL DEFAULT 'BRL', status text NOT NULL
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
 status text NOT NULL, latency_ms integer NOT NULL, agents jsonb NOT NULL, created_at timestamptz DEFAULT now()
);
CREATE TABLE IF NOT EXISTS usage_daily (
 day date NOT NULL, kind text NOT NULL, calls integer NOT NULL DEFAULT 0,
 input_tokens bigint NOT NULL DEFAULT 0, output_tokens bigint NOT NULL DEFAULT 0, PRIMARY KEY(day,kind)
);
CREATE TABLE IF NOT EXISTS handoffs (
 token text PRIMARY KEY, customer_id text NOT NULL REFERENCES customers(id), summary text NOT NULL,
 created_at timestamptz DEFAULT now(), expires_at timestamptz NOT NULL
);
CREATE TABLE IF NOT EXISTS tickets (
 id text PRIMARY KEY, handoff_token text UNIQUE NOT NULL REFERENCES handoffs(token),
 customer_id text NOT NULL REFERENCES customers(id), summary text NOT NULL,
 status text NOT NULL DEFAULT 'open_demo', created_at timestamptz DEFAULT now()
);
INSERT INTO schema_versions(version) VALUES (1) ON CONFLICT DO NOTHING;
