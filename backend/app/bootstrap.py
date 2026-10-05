"""Idempotent application bootstrap beyond schema and demonstration records."""

import json
import logging
import time
from pathlib import Path

from .config import settings
from .db import connection
from .ingest import run

logger = logging.getLogger("getnet")


def ensure_rag_seed(manifest: Path | None = None) -> bool:
    """Populate an empty vector corpus once when Docker bootstrap enables it."""
    if not settings().rag_auto_ingest:
        return False
    source_manifest = manifest or Path("data/sources.json")
    expected_documents = len(json.loads(source_manifest.read_text(encoding="utf-8")))
    with connection() as conn:
        counts = conn.execute(
            "SELECT (SELECT count(*) FROM chunks) AS chunks, "
            "(SELECT count(*) FROM rag_documents WHERE origin='crawler' AND status_embedding='indexed') AS documents"
        ).fetchone()
    if counts["chunks"] and counts["documents"] >= expected_documents:
        logger.info('{"event":"rag_seed_skipped","reason":"already_indexed"}')
        return False
    if not settings().openai_api_key.get_secret_value():
        _degraded("OPENAI_API_KEY ausente; use um dump RAG ou Reindexar no admin.")
        return False
    failures = []
    for attempt in range(1, 4):
        report = run(source_manifest)
        failures = [entry for entry in report if entry["status"] == "failed"]
        if not failures:
            break
        logger.warning('{"event":"rag_seed_retry","attempt":%d,"failures":%d}', attempt, len(failures))
        if attempt < 3:
            time.sleep(attempt)
    if failures:
        _degraded(f"Bootstrap RAG falhou em {len(failures)} fonte(s); use Reindexar no admin.")
        return False
    _healthy()
    logger.info('{"event":"rag_seed_completed"}')
    return True


def _degraded(reason: str) -> None:
    with connection() as conn:
        conn.execute(
            "INSERT INTO app_runtime_state(key,value,updated_at) VALUES ('rag_bootstrap',jsonb_build_object('degraded',true,'reason',%s),now()) ON CONFLICT(key) DO UPDATE SET value=EXCLUDED.value,updated_at=now()",
            (reason,),
        )
    logger.warning('{"event":"rag_bootstrap_degraded","reason":%s}', json.dumps(reason, ensure_ascii=False))


def _healthy() -> None:
    with connection() as conn:
        conn.execute(
            "INSERT INTO app_runtime_state(key,value,updated_at) VALUES ('rag_bootstrap','{\"degraded\":false}'::jsonb,now()) ON CONFLICT(key) DO UPDATE SET value=EXCLUDED.value,updated_at=now()"
        )
