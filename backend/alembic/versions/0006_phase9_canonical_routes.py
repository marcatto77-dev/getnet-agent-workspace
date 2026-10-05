"""Canonicalize operational routes and repair legacy RAG links idempotently."""

from alembic import op

revision = "0006_phase9_canonical_routes"
down_revision = "0005_dashboard_log_indexes"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
    UPDATE agent_runs SET route = CASE route
      WHEN 'web' THEN 'knowledge'
      WHEN 'combined' THEN 'knowledge_support'
      WHEN 'escalate' THEN 'escalation'
      WHEN 'handoff' THEN 'escalation'
      ELSE route END
    WHERE route IN ('web','combined','escalate','handoff');

    INSERT INTO rag_documents(source,title,content,origin,status_embedding,updated_at)
    SELECT d.url,d.title,COALESCE(string_agg(c.content,E'\n\n' ORDER BY c.position),''),
           'crawler','indexed',d.fetched_at
    FROM documents d LEFT JOIN chunks c ON c.document_id=d.id
    GROUP BY d.id,d.url,d.title,d.fetched_at
    ON CONFLICT(source) DO UPDATE SET
      title=EXCLUDED.title,
      content=CASE WHEN rag_documents.content='' THEN EXCLUDED.content ELSE rag_documents.content END,
      updated_at=GREATEST(rag_documents.updated_at,EXCLUDED.updated_at);

    UPDATE chunks c SET rag_document_id=r.id
    FROM documents d JOIN rag_documents r ON r.source=d.url
    WHERE c.document_id=d.id AND c.rag_document_id IS DISTINCT FROM r.id;
    """)


def downgrade():
    # Canonical values are intentionally not made ambiguous again.
    pass
