"""Security budgets, RAG review flags and immutable administrative audit."""
from alembic import op

revision = "0010_phase13_security"
down_revision = "0009_phase12_guardrails"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
    ALTER TABLE rag_documents ADD COLUMN IF NOT EXISTS review_required boolean NOT NULL DEFAULT false;
    ALTER TABLE rag_documents ADD COLUMN IF NOT EXISTS poisoning_flags jsonb NOT NULL DEFAULT '[]'::jsonb;
    CREATE TABLE IF NOT EXISTS customer_token_usage_daily (
      customer_id varchar(120) NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
      day date NOT NULL DEFAULT CURRENT_DATE,
      tokens bigint NOT NULL DEFAULT 0 CHECK(tokens >= 0),
      PRIMARY KEY(customer_id,day)
    );
    CREATE OR REPLACE FUNCTION prevent_audit_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN RAISE EXCEPTION 'audit_logs is append-only'; END $$;
    DROP TRIGGER IF EXISTS audit_logs_immutable ON audit_logs;
    CREATE TRIGGER audit_logs_immutable BEFORE UPDATE OR DELETE ON audit_logs
      FOR EACH ROW EXECUTE FUNCTION prevent_audit_mutation();
    """)


def downgrade():
    op.execute("""
    DROP TRIGGER IF EXISTS audit_logs_immutable ON audit_logs;
    DROP FUNCTION IF EXISTS prevent_audit_mutation();
    DROP TABLE IF EXISTS customer_token_usage_daily;
    ALTER TABLE rag_documents DROP COLUMN IF EXISTS poisoning_flags;
    ALTER TABLE rag_documents DROP COLUMN IF EXISTS review_required;
    """)
