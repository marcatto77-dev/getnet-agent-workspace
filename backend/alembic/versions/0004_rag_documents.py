"""Add managed RAG documents and preserve the existing vector corpus."""

from alembic import op

revision = "0004_rag_documents"
down_revision = "0003_automatic_handoffs"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
    CREATE TABLE IF NOT EXISTS rag_documents (
      id bigserial PRIMARY KEY,
      source text NOT NULL,
      title text NOT NULL,
      content text NOT NULL,
      origin text NOT NULL CHECK (origin IN ('crawler','manual')),
      status_embedding text NOT NULL DEFAULT 'indexed'
        CHECK (status_embedding IN ('pending','indexing','indexed','failed')),
      updated_at timestamptz NOT NULL DEFAULT now()
    );
    CREATE UNIQUE INDEX IF NOT EXISTS uq_rag_documents_source ON rag_documents(source);
    CREATE INDEX IF NOT EXISTS ix_rag_documents_origin_status
      ON rag_documents(origin,status_embedding,updated_at DESC);

    INSERT INTO rag_documents(source,title,content,origin,status_embedding,updated_at)
    SELECT d.url,d.title,
      COALESCE(string_agg(c.content,E'\n\n' ORDER BY c.position),''),
      'crawler','indexed',d.fetched_at
    FROM documents d LEFT JOIN chunks c ON c.document_id=d.id
    GROUP BY d.id,d.url,d.title,d.fetched_at
    ON CONFLICT(source) DO UPDATE SET title=EXCLUDED.title,
      content=CASE WHEN rag_documents.content='' THEN EXCLUDED.content ELSE rag_documents.content END,
      updated_at=GREATEST(rag_documents.updated_at,EXCLUDED.updated_at);

    SELECT setval(pg_get_serial_sequence('rag_documents','id'),
      GREATEST(COALESCE((SELECT max(id) FROM rag_documents),1),1),true);
    ALTER TABLE chunks ADD COLUMN IF NOT EXISTS rag_document_id bigint;
    UPDATE chunks c SET rag_document_id=r.id FROM documents d
      JOIN rag_documents r ON r.source=d.url
      WHERE c.document_id=d.id AND c.rag_document_id IS NULL;
    ALTER TABLE chunks ALTER COLUMN document_id DROP NOT NULL;
    ALTER TABLE chunks ALTER COLUMN rag_document_id SET NOT NULL;
    ALTER TABLE chunks DROP CONSTRAINT IF EXISTS chunks_rag_document_id_fkey;
    ALTER TABLE chunks ADD CONSTRAINT chunks_rag_document_id_fkey
      FOREIGN KEY(rag_document_id) REFERENCES rag_documents(id) ON DELETE CASCADE;
    CREATE INDEX IF NOT EXISTS ix_chunks_rag_document_position
      ON chunks(rag_document_id,position);
    """)


def downgrade():
    op.execute("""
    DELETE FROM chunks WHERE document_id IS NULL;
    ALTER TABLE chunks ALTER COLUMN document_id SET NOT NULL;
    ALTER TABLE chunks DROP CONSTRAINT IF EXISTS chunks_rag_document_id_fkey;
    ALTER TABLE chunks DROP COLUMN IF EXISTS rag_document_id;
    DROP TABLE IF EXISTS rag_documents;
    """)
