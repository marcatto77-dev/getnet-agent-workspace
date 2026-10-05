"""Record explicit administrative decisions for suspicious RAG documents."""

from alembic import op

revision = "0014_rag_review"
down_revision = "0013_service_center_compat"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
    ALTER TABLE rag_documents ADD COLUMN review_decision text
      CHECK (review_decision IN ('approved','rejected'));
    ALTER TABLE rag_documents ADD COLUMN reviewed_by integer REFERENCES users(id);
    ALTER TABLE rag_documents ADD COLUMN reviewed_at timestamptz;
    ALTER TABLE rag_documents ADD COLUMN review_reason text;
    CREATE INDEX ix_rag_documents_review ON rag_documents(review_required,status_embedding);
    UPDATE rag_documents SET status_embedding='pending'
      WHERE review_required=true AND status_embedding='indexed';
    DELETE FROM chunks WHERE rag_document_id IN
      (SELECT id FROM rag_documents WHERE review_required=true);
    CREATE TABLE login_rate_limits (
      key_hash varchar(64) PRIMARY KEY,
      window_started_at timestamptz NOT NULL,
      attempts integer NOT NULL DEFAULT 0,
      locked_until timestamptz,
      lockouts integer NOT NULL DEFAULT 0,
      updated_at timestamptz NOT NULL DEFAULT now()
    );
    CREATE TABLE request_rate_limits (
      key_hash varchar(64) PRIMARY KEY,
      window_started_at timestamptz NOT NULL,
      attempts integer NOT NULL DEFAULT 0,
      updated_at timestamptz NOT NULL DEFAULT now()
    );
    """)


def downgrade():
    op.execute("""
    DROP TABLE IF EXISTS request_rate_limits;
    DROP TABLE IF EXISTS login_rate_limits;
    DROP INDEX IF EXISTS ix_rag_documents_review;
    ALTER TABLE rag_documents DROP COLUMN IF EXISTS review_reason;
    ALTER TABLE rag_documents DROP COLUMN IF EXISTS reviewed_at;
    ALTER TABLE rag_documents DROP COLUMN IF EXISTS reviewed_by;
    ALTER TABLE rag_documents DROP COLUMN IF EXISTS review_decision;
    """)
