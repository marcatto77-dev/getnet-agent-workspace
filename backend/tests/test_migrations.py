"""Migration regression from the pre-RAG (Phase 5) schema state."""

import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from app.config import settings
from app.db import connection

pytestmark = pytest.mark.integration


def test_phase5_upgrade_preserves_legacy_rag_data(monkeypatch):
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Defina TEST_DATABASE_URL para executar a integração com PostgreSQL real.")
    if not url.rstrip("/").endswith("getnet_test"):
        pytest.fail("Por segurança, o banco de integração deve se chamar getnet_test.")
    monkeypatch.setenv("DATABASE_URL", url)
    settings.cache_clear()
    backend = Path(__file__).resolve().parents[1]
    config = Config(str(backend / "alembic.ini"))
    config.set_main_option("script_location", str(backend / "alembic"))
    command.downgrade(config, "0003_automatic_handoffs")
    vector = "[" + ",".join(["0"] * 1536) + "]"
    with connection() as conn:
        document_id = conn.execute(
            "INSERT INTO documents(url,title,country,language,content_hash,embedding_model) "
            "VALUES ('https://site.getnet.com.br/fase5-teste','Legado fase 5','BR','pt','hash-fase5','text-embedding-3-small') "
            "ON CONFLICT(url) DO UPDATE SET title=EXCLUDED.title RETURNING id"
        ).fetchone()["id"]
        conn.execute("DELETE FROM chunks WHERE document_id=%s", (document_id,))
        conn.execute(
            "INSERT INTO chunks(document_id,position,content,embedding) VALUES (%s,0,'conteúdo preservado',%s::vector)",
            (document_id, vector),
        )
    command.upgrade(config, "head")
    with connection() as conn:
        row = conn.execute(
            "SELECT r.content,c.content AS chunk_content FROM documents d "
            "JOIN rag_documents r ON r.source=d.url JOIN chunks c ON c.document_id=d.id "
            "WHERE d.url='https://site.getnet.com.br/fase5-teste'"
        ).fetchone()
        assert row == {"content": "conteúdo preservado", "chunk_content": "conteúdo preservado"}
    settings.cache_clear()
