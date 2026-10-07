import re

from .config import settings
from .db import connection


def catalog_question(query: str) -> bool:
    """A broad model-list request needs one cited manual per model, not
    whichever unrelated passage happens to be closest in vector space."""
    return bool(
        re.search(r"\b(?:todos?|quais|liste|lista)\b", query, re.IGNORECASE)
        and re.search(r"\b(?:modelos?|m[aá]quinas?|maquininhas?)\b", query, re.IGNORECASE)
        and not re.search(r"\b(?:aceita|suporta|compat[ií]vel|pix|wifi|wi-fi)\b", query, re.IGNORECASE)
    )


def retrieve(query: str, provider, limit: int = 5):
    with connection() as conn:
        if not conn.execute("SELECT 1 FROM chunks LIMIT 1").fetchone():
            return []
    vector = provider.embed([query])[0]
    # Exact vector scan is adequate for the bounded initial corpus. Add HNSW after measurement.
    with connection(vector=True) as conn:
        catalog = []
        lexical = []
        terms = lexical_terms(query)
        if terms:
            lexical = conn.execute(
                "SELECT c.id,c.content,d.title,d.source,d.origin,d.updated_at, "
                "c.embedding <=> %s::vector AS distance FROM chunks c "
                "JOIN rag_documents d ON c.rag_document_id=d.id "
                "WHERE d.status_embedding='indexed' AND d.review_required=false "
                "AND to_tsvector('portuguese',d.title || ' ' || c.content) "
                "@@ to_tsquery('portuguese',%s) "
                "ORDER BY ts_rank_cd("
                "setweight(to_tsvector('portuguese',d.title),'A') || "
                "setweight(to_tsvector('portuguese',c.content),'B'),"
                "to_tsquery('portuguese',%s)) DESC, distance LIMIT %s",
                (str(vector), terms, terms, min(2, limit)),
            ).fetchall()
        if catalog_question(query):
            catalog = conn.execute(
                "SELECT c.id,c.content,d.title,d.source,d.origin,d.updated_at, "
                "c.embedding <=> %s::vector AS distance FROM chunks c "
                "JOIN rag_documents d ON c.rag_document_id=d.id "
                "WHERE d.status_embedding='indexed' AND d.review_required=false AND d.origin='crawler' "
                "AND d.source LIKE 'https://site.getnet.com.br/%%.pdf' "
                "AND d.title ILIKE 'Manual oficial Get %%' AND c.position=0 "
                "ORDER BY d.title LIMIT %s",
                (str(vector), limit),
            ).fetchall()
        rows = conn.execute(
            "SELECT c.id,c.content,d.title,d.source,d.origin,d.updated_at, "
            "c.embedding <=> %s::vector AS distance FROM chunks c "
            "JOIN rag_documents d ON c.rag_document_id=d.id "
            "WHERE d.status_embedding='indexed' AND d.review_required=false "
            "ORDER BY distance LIMIT %s",
            (str(vector), limit),
        ).fetchall()
    selected = []
    seen = set()
    seen_sources = set()
    for row in [*catalog, *lexical, *rows]:
        if row["id"] in seen or len(selected) >= limit:
            continue
        if catalog and row["source"] in seen_sources:
            continue
        if row not in catalog and row not in lexical and float(row["distance"]) > settings().rag_max_distance:
            continue
        selected.append(row)
        seen.add(row["id"])
        seen_sources.add(row["source"])
    return [
        {
            "id": i + 1,
            "title": row["title"] + (" (conteúdo manual)" if row["origin"] == "manual" else ""),
            "url": row["source"] if row["origin"] == "crawler" else None,
            "kind": "manual" if row["origin"] == "manual" else "rag",
            "retrieved_at": row["updated_at"].isoformat(),
            "content": row["content"],
            "chunk_id": row["id"],
            "distance": float(row["distance"]),
        }
        for i, row in enumerate(selected)
    ]


def lexical_terms(query: str) -> str:
    # OR over meaningful words catches short administrative records missed by
    # vector similarity. Values stay parameterized, never executable SQL.
    ignored = {
        "getnet",
        "get",
        "qual",
        "quais",
        "onde",
        "fica",
        "como",
        "para",
        "uma",
        "por",
        "com",
        "dos",
        "das",
        "modelo",
        "modelos",
        "hoje",
        "posso",
        "the",
        "what",
        "where",
        "how",
        "can",
        "and",
        "que",
        "todos",
    }
    words = list(
        dict.fromkeys(word for word in re.findall(r"[^\W\d_]{3,}", query.casefold()) if word not in ignored)
    )
    if re.search(r"\bonde\s+fica\b", query, re.I) and "endereço" not in words:
        words.append("endereço")
    return " | ".join(words[:12])
