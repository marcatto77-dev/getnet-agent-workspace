"""Create/restore a compressed RAG-only PostgreSQL dump without OpenAI calls."""
import argparse
import gzip
import os
import subprocess
from pathlib import Path

TABLES = ["rag_documents", "chunks"]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("create", "restore"))
    parser.add_argument("--file", default="db/seed/rag_chunks.sql.gz")
    args = parser.parse_args()
    target = Path(args.file)
    database_url = os.environ["DATABASE_URL"]
    if args.command == "create":
        target.parent.mkdir(parents=True, exist_ok=True)
        command = ["pg_dump", "--dbname", database_url, "--data-only", "--inserts", *sum((["--table", table] for table in TABLES), [])]
        raw = subprocess.check_output(command)
        with gzip.open(target, "wb") as output:
            output.write(raw)
        print(f"snapshot criado: {target}")
        return
    with gzip.open(target, "rb") as source:
        subprocess.run(["psql", "--dbname", database_url, "--set", "ON_ERROR_STOP=1"], input=source.read(), check=True)
    print(f"snapshot restaurado: {target}")


if __name__ == "__main__":
    main()
