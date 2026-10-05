# Snapshot de fallback do RAG

`rag_chunks.sql.gz` é um dump opcional de `rag_documents` e `chunks`, incluindo os embeddings. Ele não é gerado automaticamente nem contém chaves.

Com um cliente PostgreSQL compatível e `DATABASE_URL` definido, crie-o com:

```text
python backend/scripts/rag_snapshot.py create
```

Restaure-o somente após as migrations e quando a versão do pgvector e o modelo de embedding forem os mesmos:

```text
python backend/scripts/rag_snapshot.py restore
```
