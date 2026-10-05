import json
import threading
from datetime import datetime, timezone
from uuid import uuid4

import httpx

from .administration import audit
from .config import settings
from .db import connection
from .ingest import chunks, extract_document, fetch, poisoning_signals, validate_url
from .persistence import mask_sensitive
from .provider import Provider

reindex_state = {
    "status": "idle",
    "processed": 0,
    "total": 0,
    "error": None,
    "started_at": None,
    "finished_at": None,
}
reindex_lock = threading.Lock()


def _parts_and_vectors(content: str, provider=None):
    parts = chunks(content)
    if not parts:
        raise ValueError("O documento não possui conteúdo indexável.")
    if len(parts) > 300:
        raise ValueError("Documento muito grande para indexação automática.")
    provider = provider or Provider()
    vectors = []
    for start in range(0, len(parts), 32):
        vectors.extend(provider.embed(parts[start : start + 32]))
    if len(vectors) != len(parts):
        raise ValueError("O provedor retornou uma quantidade inválida de embeddings.")
    return parts, vectors


def _write_chunks(conn, document_id: int, parts: list[str], vectors: list[list[float]]):
    conn.execute("DELETE FROM chunks WHERE rag_document_id=%s", (document_id,))
    for position, (part, vector) in enumerate(zip(parts, vectors, strict=True)):
        conn.execute(
            "INSERT INTO chunks(document_id,rag_document_id,position,content,embedding) "
            "VALUES (NULL,%s,%s,%s,%s::vector)",
            (document_id, position, part, str(vector)),
        )


def list_documents(search: str, origin: str, status: str, page: int, page_size: int) -> dict:
    clauses = ["(d.title ILIKE %s OR d.source ILIKE %s OR d.content ILIKE %s)"]
    term = f"%{search}%"
    params: list = [term, term, term]
    if origin:
        clauses.append("d.origin=%s")
        params.append(origin)
    if status:
        clauses.append("d.status_embedding=%s")
        params.append(status)
    where = " AND ".join(clauses)
    with connection() as conn:
        total = conn.execute(f"SELECT count(*) AS n FROM rag_documents d WHERE {where}", params).fetchone()[
            "n"
        ]
        items = conn.execute(
            f"SELECT d.id,d.source,d.title,d.content,d.origin,d.status_embedding,d.updated_at,"
            f"d.review_required,d.poisoning_flags,d.review_decision,d.reviewed_at,d.review_reason,"
            f"count(c.id) AS chunk_count FROM rag_documents d LEFT JOIN chunks c ON c.rag_document_id=d.id "
            f"WHERE {where} GROUP BY d.id ORDER BY d.updated_at DESC,d.id DESC LIMIT %s OFFSET %s",
            [*params, page_size, (page - 1) * page_size],
        ).fetchall()
    return {"items": items, "total": total, "page": page, "page_size": page_size}


def create_document(actor_id: int, title: str, content: str, provider=None) -> dict:
    flags = poisoning_signals(content)
    parts, vectors = ([], []) if flags else _parts_and_vectors(content, provider)
    source = "manual://" + uuid4().hex
    with connection(vector=True) as conn:
        row = conn.execute(
            "INSERT INTO rag_documents(source,title,content,origin,status_embedding,review_required,poisoning_flags) "
            "VALUES (%s,%s,%s,'manual',%s,%s,%s::jsonb) "
            "RETURNING *",
            (source, title, content, "pending" if flags else "indexed", bool(flags), json.dumps(flags)),
        ).fetchone()
        if not flags:
            _write_chunks(conn, row["id"], parts, vectors)
        audit(
            conn,
            actor_id,
            "rag_document.created",
            "rag_document",
            row["id"],
            {
                "title": title,
                "origin": "manual",
                "chunks": len(parts),
                "review_required": bool(flags),
                "flags": flags,
            },
        )
        return row


def update_document(actor_id: int, document_id: int, title: str, content: str, provider=None) -> dict:
    flags = poisoning_signals(content)
    with connection() as conn:
        existing = conn.execute(
            "SELECT review_required FROM rag_documents WHERE id=%s", (document_id,)
        ).fetchone()
    if not existing:
        raise LookupError("Documento não localizado.")
    pending = bool(flags or existing["review_required"])
    parts, vectors = ([], []) if pending else _parts_and_vectors(content, provider)
    with connection(vector=True) as conn:
        current = conn.execute(
            "SELECT id,title,review_required FROM rag_documents WHERE id=%s FOR UPDATE", (document_id,)
        ).fetchone()
        if not current:
            raise LookupError("Documento não localizado.")
        if current["review_required"] and not pending:
            raise ValueError("Documento em revisão; recarregue a lista antes de editar.")
        row = conn.execute(
            "UPDATE rag_documents SET title=%s,content=%s,status_embedding=%s,review_required=%s,"
            "poisoning_flags=%s::jsonb,review_decision=NULL,reviewed_by=NULL,reviewed_at=NULL,"
            "review_reason=NULL,updated_at=now() WHERE id=%s RETURNING *",
            (title, content, "pending" if pending else "indexed", pending, json.dumps(flags), document_id),
        ).fetchone()
        _write_chunks(conn, document_id, parts, vectors)
        audit(
            conn,
            actor_id,
            "rag_document.updated",
            "rag_document",
            document_id,
            {
                "title": {"from": current["title"], "to": title},
                "chunks": len(parts),
                "review_required": pending,
                "flags": flags,
            },
        )
        return row


def delete_document(actor_id: int, document_id: int) -> dict:
    with connection() as conn:
        row = conn.execute(
            "DELETE FROM rag_documents WHERE id=%s RETURNING id,title,origin", (document_id,)
        ).fetchone()
        if not row:
            raise LookupError("Documento não localizado.")
        audit(
            conn,
            actor_id,
            "rag_document.deleted",
            "rag_document",
            document_id,
            {"title": row["title"], "origin": row["origin"]},
        )
        return row


def ingest_url(actor_id: int, url: str, provider=None) -> dict:
    validate_url(url)
    with httpx.Client(
        timeout=settings().ingest_timeout_seconds,
        headers={"User-Agent": "GetnetChallengeBot/0.1"},
        follow_redirects=False,
        cookies=None,
    ) as client:
        payload, canonical = fetch(client, url)
    raw_flags = poisoning_signals(payload) if isinstance(payload, str) else []
    title, content = extract_document(payload, canonical)
    flags = sorted(set(raw_flags + poisoning_signals(content)))
    with connection() as conn:
        previous = conn.execute(
            "SELECT review_required FROM rag_documents WHERE source=%s", (canonical,)
        ).fetchone()
    if flags or (previous and previous["review_required"]):
        with connection() as conn:
            row = conn.execute(
                "INSERT INTO rag_documents(source,title,content,origin,status_embedding,review_required,poisoning_flags) "
                "VALUES (%s,%s,%s,'crawler','pending',true,%s::jsonb) ON CONFLICT(source) DO UPDATE SET "
                "title=EXCLUDED.title,content=EXCLUDED.content,status_embedding='pending',review_required=true,"
                "poisoning_flags=EXCLUDED.poisoning_flags,review_decision=NULL,reviewed_by=NULL,"
                "reviewed_at=NULL,review_reason=NULL,updated_at=now() RETURNING *",
                (canonical, title, content, json.dumps(flags)),
            ).fetchone()
            conn.execute("DELETE FROM chunks WHERE rag_document_id=%s", (row["id"],))
            audit(
                conn,
                actor_id,
                "rag_document.flagged",
                "rag_document",
                row["id"],
                {"source": canonical, "flags": flags},
            )
            return row
    parts, vectors = _parts_and_vectors(content, provider)
    with connection(vector=True) as conn:
        row = conn.execute(
            "INSERT INTO rag_documents(source,title,content,origin,status_embedding) "
            "VALUES (%s,%s,%s,'crawler','indexed') ON CONFLICT(source) DO UPDATE SET "
            "title=EXCLUDED.title,content=EXCLUDED.content,status_embedding='indexed',updated_at=now() "
            "WHERE rag_documents.review_required=false RETURNING *",
            (canonical, title, content),
        ).fetchone()
        if not row:
            raise ValueError("Documento entrou em revisão; tente novamente após decisão administrativa.")
        _write_chunks(conn, row["id"], parts, vectors)
        audit(
            conn,
            actor_id,
            "rag_document.ingested",
            "rag_document",
            row["id"],
            {"source": canonical, "title": title, "chunks": len(parts)},
        )
        return row


def review_document(actor_id: int, document_id: int, decision: str, reason: str, provider=None) -> dict:
    if decision not in {"approved", "rejected"} or len(reason.strip()) < 10:
        raise ValueError("Informe decisão e motivo com pelo menos 10 caracteres.")
    safe_reason = mask_sensitive(reason.strip())[:1000]
    with connection() as conn:
        document = conn.execute(
            "SELECT id,content,review_required,status_embedding FROM rag_documents WHERE id=%s",
            (document_id,),
        ).fetchone()
    if not document:
        raise LookupError("Documento não localizado.")
    if not document["review_required"] or document["status_embedding"] != "pending":
        raise ValueError("Documento não está pendente de revisão.")
    parts, vectors = ([], []) if decision == "rejected" else _parts_and_vectors(document["content"], provider)
    with connection(vector=True) as conn:
        current = conn.execute(
            "SELECT content,review_required,status_embedding FROM rag_documents WHERE id=%s FOR UPDATE",
            (document_id,),
        ).fetchone()
        if (
            not current
            or not current["review_required"]
            or current["status_embedding"] != "pending"
            or current["content"] != document["content"]
        ):
            raise ValueError("Documento mudou durante a revisão; carregue-o novamente.")
        _write_chunks(conn, document_id, parts, vectors)
        row = conn.execute(
            "UPDATE rag_documents SET review_required=%s,status_embedding=%s,review_decision=%s,"
            "reviewed_by=%s,reviewed_at=now(),review_reason=%s,updated_at=now() WHERE id=%s RETURNING *",
            (
                decision != "approved",
                "indexed" if decision == "approved" else "failed",
                decision,
                actor_id,
                safe_reason,
                document_id,
            ),
        ).fetchone()
        audit(
            conn,
            actor_id,
            f"rag_document.{decision}",
            "rag_document",
            document_id,
            {"reason": safe_reason[:300], "chunks": len(parts)},
        )
        return row


def reindex_all(actor_id: int, provider=None):
    try:
        with connection() as conn:
            excluded = conn.execute(
                "SELECT count(*) AS n FROM rag_documents WHERE review_required=true OR status_embedding='pending'"
            ).fetchone()["n"]
            documents = conn.execute(
                "SELECT id,title,content FROM rag_documents WHERE review_required=false "
                "AND status_embedding IN ('indexed','failed') AND btrim(content)<>'' ORDER BY id"
            ).fetchall()
        with reindex_lock:
            reindex_state.update(
                status="running",
                processed=0,
                total=len(documents),
                error=None,
                started_at=datetime.now(timezone.utc).isoformat(),
                finished_at=None,
            )
        if documents:
            provider = provider or Provider()
        prepared = []
        for index, document in enumerate(documents, 1):
            flags = poisoning_signals(document["content"])
            if flags:
                prepared.append((document, [], [], flags))
            else:
                parts, vectors = _parts_and_vectors(document["content"], provider)
                prepared.append((document, parts, vectors, []))
            with reindex_lock:
                reindex_state["processed"] = index
        with connection(vector=True) as conn:
            indexed = 0
            quarantined = 0
            for document, parts, vectors, flags in prepared:
                current = conn.execute(
                    "SELECT content,review_required,status_embedding FROM rag_documents WHERE id=%s FOR UPDATE",
                    (document["id"],),
                ).fetchone()
                if (
                    not current
                    or current["review_required"]
                    or current["status_embedding"] not in ("indexed", "failed")
                    or current["content"] != document["content"]
                ):
                    excluded += 1
                    continue
                if flags:
                    conn.execute("DELETE FROM chunks WHERE rag_document_id=%s", (document["id"],))
                    conn.execute(
                        "UPDATE rag_documents SET review_required=true,status_embedding='pending',"
                        "poisoning_flags=%s::jsonb,updated_at=now() WHERE id=%s",
                        (json.dumps(flags), document["id"]),
                    )
                    audit(
                        conn,
                        actor_id,
                        "rag_document.flagged",
                        "rag_document",
                        document["id"],
                        {"flags": flags},
                    )
                    quarantined += 1
                    continue
                _write_chunks(conn, document["id"], parts, vectors)
                conn.execute(
                    "UPDATE rag_documents SET status_embedding='indexed',updated_at=now() WHERE id=%s",
                    (document["id"],),
                )
                indexed += 1
            audit(
                conn,
                actor_id,
                "rag.reindexed",
                "rag_document",
                "all",
                {
                    "documents": indexed,
                    "excluded_pending": excluded,
                    "quarantined": quarantined,
                    "embedding_model": settings().embedding_model,
                },
            )
        with reindex_lock:
            reindex_state.update(status="completed", finished_at=datetime.now(timezone.utc).isoformat())
    except Exception as exc:
        with reindex_lock:
            reindex_state.update(
                status="failed",
                error=f"{type(exc).__name__}: {exc}"[:500],
                finished_at=datetime.now(timezone.utc).isoformat(),
            )


def start_reindex(actor_id: int) -> dict:
    with reindex_lock:
        if reindex_state["status"] == "running":
            raise ValueError("Já existe uma reindexação em andamento.")
        reindex_state.update(status="queued", processed=0, total=0, error=None)
    thread = threading.Thread(target=reindex_all, args=(actor_id,), daemon=True)
    thread.start()
    return get_reindex_status()


def get_reindex_status() -> dict:
    with reindex_lock:
        return dict(reindex_state)
