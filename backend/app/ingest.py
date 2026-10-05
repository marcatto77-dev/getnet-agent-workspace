"""Explicit, bounded ingestion. --collect-only performs no paid API calls."""

import argparse
import hashlib
import io
import ipaddress
import json
import re
import socket
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import httpx
import trafilatura
from bs4 import BeautifulSoup
from pypdf import PdfReader

from .config import settings
from .db import connection
from .guardrails.input import decoded_candidates
from .provider import Provider

USER_AGENT = "GetnetChallengeBot/0.1"
ALLOWED_CONTENT_TYPES = {"text/html", "text/plain", "application/xhtml+xml"}
PDF_CONTENT_TYPE = "application/pdf"


def validate_url(url: str):
    parsed = urlparse(url)
    hostname = (parsed.hostname or "").casefold().rstrip(".")
    domain_allowed = any(
        hostname == domain or hostname.endswith("." + domain) for domain in settings().allowed_ingest_domains
    )
    if (
        parsed.scheme != "https"
        or not domain_allowed
        or parsed.port not in (None, 80, 443)
        or parsed.username
        or parsed.password
    ):
        raise ValueError("URL fora da lista oficial permitida")
    try:
        addresses = {
            item[4][0] for item in socket.getaddrinfo(hostname, parsed.port or 443, type=socket.SOCK_STREAM)
        }
    except socket.gaierror as exc:
        raise ValueError("Não foi possível resolver o domínio") from exc
    for address in addresses:
        ip = ipaddress.ip_address(address)
        if not ip.is_global or ip in ipaddress.ip_network("169.254.169.254/32"):
            raise ValueError("Destino de rede privado ou reservado não permitido")


def fetch(client, url: str):
    for _ in range(settings().ingest_max_redirects + 1):
        validate_url(url)
        with client.stream("GET", url) as response:
            if response.is_redirect:
                url = urljoin(url, response.headers["location"])
                continue
            response.raise_for_status()
            content_type = response.headers.get("content-type", "").split(";", 1)[0].strip().casefold()
            if content_type not in ALLOWED_CONTENT_TYPES | {PDF_CONTENT_TYPE}:
                raise ValueError("Formato não textual")
            limit = (
                settings().ingest_pdf_max_bytes
                if content_type == PDF_CONTENT_TYPE
                else settings().ingest_max_bytes
            )
            if int(response.headers.get("content-length", "0")) > limit:
                raise ValueError("Documento excede limite de tamanho")
            content = bytearray()
            for part in response.iter_bytes():
                content.extend(part)
                if len(content) > limit:
                    raise ValueError("Documento excede limite de tamanho")
            payload = bytes(content)
            return (
                payload if content_type == PDF_CONTENT_TYPE else payload.decode("utf-8", errors="replace")
            ), url
    raise ValueError("Muitos redirecionamentos")


def chunks(text: str, size: int = 1800, overlap: int = 200):
    if size <= overlap or overlap < 0:
        raise ValueError("Tamanho de chunk inválido")
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    result = []
    start = 0
    while start < len(text):
        end = min(start + size, len(text))
        if end < len(text):
            boundary = text.rfind("\n", start + size // 2, end)
            if boundary > start:
                end = boundary
        part = text[start:end].strip()
        if part:
            result.append(part)
        if end == len(text):
            break
        start = end - overlap
    return result


def extract(html: str):
    soup = BeautifulSoup(html, "html.parser")
    title = soup.title.get_text(" ", strip=True) if soup.title else "Getnet"
    for node in soup.select(
        "script, style, nav, footer, header, form, noscript, [hidden], [aria-hidden='true'], [style*='display:none'], [style*='display: none']"
    ):
        node.decompose()
    text = trafilatura.extract(str(soup), include_comments=False, include_tables=True, favor_recall=True)
    # Article extraction can discard product cards and FAQ headings.
    content = soup.find("main") or soup.body or soup
    full_text = content.get_text("\n", strip=True)
    if len(full_text) > 1.5 * len(text or ""):
        text = full_text
    if not text or len(text) < 200:
        raise ValueError("Texto útil insuficiente: exige revisão manual")
    return title, text


def extract_document(payload: str | bytes, url: str):
    if isinstance(payload, str):
        return extract(payload)
    if not payload.startswith(b"%PDF-"):
        raise ValueError("PDF inválido")
    reader = PdfReader(io.BytesIO(payload), strict=False)
    if reader.is_encrypted or len(reader.pages) > settings().ingest_pdf_max_pages:
        raise ValueError("PDF protegido ou com páginas acima do limite")
    text = "\n\n".join(page.extract_text(extraction_mode="layout") or "" for page in reader.pages)
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text).strip()
    if len(text) < 200:
        raise ValueError("PDF sem texto extraível suficiente: exige revisão manual")
    filename = urlparse(url).path.casefold()
    model = next(
        (
            name
            for key, name in (
                ("getsmart", "Get Smart"),
                ("getclassica", "Get Clássica"),
                ("getmini", "Get Mini"),
                ("getlite", "Get Lite"),
            )
            if key in filename
        ),
        "Maquininhas Getnet",
    )
    return f"Manual oficial {model} — Getnet", text


def poisoning_signals(text: str) -> list[str]:
    patterns = {
        "ignore_instructions": r"(?i)(?:ignore|ignora|desconsidere|olvida|forget|disregard).{0,40}(?:instruções|instrucciones|instructions|regras|rules|prompt)",
        "system_prompt": r"(?i)(?:system prompt|prompt do sistema|revele.{0,25}prompt|reveal.{0,25}prompt)",
        "role_spoofing": r"(?im)(?:^|\n)\s*(?:system|developer|assistant|administrador)\s*:\s*[^\n]{0,100}",
        "tool_override": r"(?i)(?:execute|chame|call|invoque).{0,30}(?:ferramenta|tool|function)",
        "data_exfiltration": r"(?i)(?:envie|send|exfiltrate|vaze).{0,60}(?:segredo|secret|token|api[ _-]?key|chave\s+(?:api|privada|secreta)|dados\s+(?:do|de)\s+cliente|customer\s+(?:data|records))",
    }
    candidates = decoded_candidates(text[:500_000])
    return [
        name
        for name, pattern in patterns.items()
        if any(re.search(pattern, candidate) for candidate in candidates)
    ]


def run(manifest: Path, collect_only=False):
    sources = json.loads(manifest.read_text(encoding="utf-8"))
    if not 1 <= len(sources) <= 30:
        raise ValueError("Manifesto deve conter de 1 a 30 páginas")
    raw_dir = manifest.parent / "raw"
    report_dir = manifest.parent / "reports"
    raw_dir.mkdir(exist_ok=True)
    report_dir.mkdir(exist_ok=True)
    report = []
    provider = None if collect_only else Provider()
    with httpx.Client(timeout=30, headers={"User-Agent": USER_AGENT}, follow_redirects=False) as client:
        robots = {}
        for source in sources:
            url = source["url"]
            entry = {
                "url": url,
                "topic": source["topic"],
                "fetched_at": datetime.now(timezone.utc).isoformat(),
            }
            try:
                validate_url(url)
                origin = "https://" + urlparse(url).netloc
                if origin not in robots:
                    try:
                        robots_text, _ = fetch(client, origin + "/robots.txt")
                    except httpx.HTTPStatusError as exc:
                        # Missing robots.txt is different from forbidden or temporarily unavailable.
                        if exc.response.status_code not in (404, 410):
                            raise
                        robots_text = "User-agent: *\nAllow: /"
                    parser = RobotFileParser()
                    parser.parse(robots_text.splitlines())
                    robots[origin] = parser
                if not robots[origin].can_fetch(USER_AGENT, url):
                    raise ValueError("Coleta não permitida por robots.txt")
                payload, canonical = fetch(client, url)
                title, text = extract_document(payload, canonical)
                if poisoning_signals(text) or (isinstance(payload, str) and poisoning_signals(payload)):
                    raise ValueError("Fonte com instruções suspeitas: requer revisão no admin")
                digest = hashlib.sha256(text.encode()).hexdigest()
                parts = chunks(text)
                if len(parts) > 300:
                    raise ValueError("Documento muito grande: revisar escopo antes de gerar embeddings")
                snapshot = {
                    **source,
                    "canonical_url": canonical,
                    "title": title,
                    "text": text,
                    "hash": digest,
                    "fetched_at": entry["fetched_at"],
                }
                (raw_dir / (hashlib.sha256(url.encode()).hexdigest()[:16] + ".json")).write_text(
                    json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8"
                )
                entry.update(title=title, chunks=len(parts), characters=len(text))
                if collect_only:
                    entry["status"] = "collected"
                else:
                    with connection() as conn:
                        existing = conn.execute(
                            "SELECT content_hash,embedding_model FROM documents WHERE url=%s", (url,)
                        ).fetchone()
                        held = conn.execute(
                            "SELECT id FROM rag_documents WHERE source=%s AND review_required=true",
                            (canonical,),
                        ).fetchone()
                    if held:
                        entry["status"] = "review_required"
                        report.append(entry)
                        print(json.dumps(entry, ensure_ascii=False), flush=True)
                        continue
                    if (
                        existing
                        and existing["content_hash"] == digest
                        and existing["embedding_model"] == settings().embedding_model
                    ):
                        with connection() as conn:
                            conn.execute("UPDATE documents SET fetched_at=now() WHERE url=%s", (url,))
                        entry["status"] = "unchanged"
                    else:
                        vectors = []
                        for start in range(0, len(parts), 32):
                            vectors.extend(provider.embed(parts[start : start + 32]))
                        with connection(vector=True) as conn:
                            document = conn.execute(
                                "INSERT INTO documents(url,title,country,language,content_hash,embedding_model) "
                                "VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT(url) DO UPDATE SET title=EXCLUDED.title, "
                                "country=EXCLUDED.country,language=EXCLUDED.language,content_hash=EXCLUDED.content_hash, "
                                "embedding_model=EXCLUDED.embedding_model,fetched_at=now() RETURNING id",
                                (
                                    url,
                                    title,
                                    source["country"],
                                    source["language"],
                                    digest,
                                    settings().embedding_model,
                                ),
                            ).fetchone()
                            managed = conn.execute(
                                "INSERT INTO rag_documents(source,title,content,origin,status_embedding) "
                                "VALUES (%s,%s,%s,'crawler','indexed') ON CONFLICT(source) DO UPDATE SET "
                                "title=EXCLUDED.title,content=EXCLUDED.content,status_embedding='indexed',updated_at=now() "
                                "WHERE rag_documents.review_required=false "
                                "RETURNING id",
                                (canonical, title, text),
                            ).fetchone()
                            if not managed:
                                raise ValueError("Documento entrou em revisão; a indexação foi cancelada")
                            conn.execute("DELETE FROM chunks WHERE document_id=%s", (document["id"],))
                            conn.execute("DELETE FROM chunks WHERE rag_document_id=%s", (managed["id"],))
                            for i, (part, vector) in enumerate(zip(parts, vectors, strict=True)):
                                conn.execute(
                                    "INSERT INTO chunks(document_id,rag_document_id,position,content,embedding) "
                                    "VALUES (%s,%s,%s,%s,%s::vector)",
                                    (document["id"], managed["id"], i, part, str(vector)),
                                )
                        entry["status"] = "indexed"
            except Exception as exc:
                # No credentials or provider payloads in reports.
                entry.update(status="failed", error_type=type(exc).__name__)
                if getattr(exc, "code", None) in ("credit_balance_exhausted", "insufficient_quota"):
                    entry["reason"] = (
                        "Crédito OpenAI indisponível; ingestão interrompida para evitar novas tentativas."
                    )
                    report.append(entry)
                    print(json.dumps(entry, ensure_ascii=False), flush=True)
                    break
                if isinstance(exc, httpx.HTTPStatusError):
                    entry["http_status"] = exc.response.status_code
                if isinstance(exc, ValueError):
                    entry["reason"] = str(exc)
            report.append(entry)
            print(json.dumps(entry, ensure_ascii=False), flush=True)
            time.sleep(0.4)
    (report_dir / "ingestion.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=Path("data/sources.json"))
    parser.add_argument("--collect-only", action="store_true")
    args = parser.parse_args()
    result = run(args.manifest, args.collect_only)
    raise SystemExit(1 if any(x["status"] == "failed" for x in result) else 0)
