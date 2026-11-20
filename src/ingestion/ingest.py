"""
NOT UPDATED
chunk, embed and store
Ingest reviewed .md/.txt sources with .json metadata, then build SQLite/FAISS storage."""

import argparse
import sys
from pathlib import Path

from src import rag
from src.schemas import SourceMetadata


def split_text(text: str, size: int = 1800, overlap: int = 200) -> list[str]:
    # Character windows preserve punctuation/negations and bound embedding inputs.
    return [text[start:start + size] for start in range(0, len(text), size - overlap)]


def ingest_file(path: Path, allow_fixtures: bool = False) -> str:
    meta = SourceMetadata.model_validate_json(path.with_suffix(".json").read_text(encoding="utf-8"))
    if meta.fixture and not allow_fixtures:
        raise ValueError("Test fixtures require explicit opt-in and a separate test database")
    content = path.read_text(encoding="utf-8").strip()
    if not content or len(content) > 1_000_000:
        raise ValueError("Reviewed source must contain 1 to 1,000,000 characters")
    document_id = rag.stable_id(meta.url)
    parts = split_text(content)
    with rag.connect() as db:
        db.execute("""INSERT INTO documents
            (id,title,url,publisher,published_date,retrieved_date,content,fixture) VALUES (?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET title=excluded.title,publisher=excluded.publisher,
            published_date=excluded.published_date,retrieved_date=excluded.retrieved_date,
            content=excluded.content,fixture=excluded.fixture""",
            (document_id, meta.title, meta.url, meta.publisher,
             meta.published_date.isoformat() if meta.published_date else None,
             meta.retrieved_date.isoformat(), content, int(meta.fixture)))
        for ordinal, part in enumerate(parts):
            chunk_id = rag.stable_id(f"{document_id}|{ordinal}|{part}")
            # Remove a changed chunk occupying this ordinal before inserting its replacement.
            db.execute("DELETE FROM chunks WHERE document_id=? AND ordinal=? AND id<>?",
                       (document_id, ordinal, chunk_id))
            db.execute("INSERT OR IGNORE INTO chunks VALUES (?,?,?,?)", (chunk_id, document_id, ordinal, part))
        db.execute("DELETE FROM chunks WHERE document_id=? AND ordinal>=?", (document_id, len(parts)))
    return document_id


def ingest_directory(directory: Path, allow_fixtures: bool = False) -> int:
    paths = sorted(p for p in directory.iterdir() if p.suffix.lower() in {".md", ".txt"})
    if not paths:
        raise ValueError("No .md or .txt evidence files found")
    for path in paths:
        ingest_file(path, allow_fixtures)
    return len(paths)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", nargs="?", type=Path, default=rag.ROOT / "data" / "raw",
                        help="Reviewed .md/.txt files with adjacent .json metadata (default: data/raw)")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--no-index", action="store_true", help="Only ingest documents; no embedding API calls")
    mode.add_argument("--rebuild-only", action="store_true", help="Rebuild from already ingested documents")
    parser.add_argument("--reembed", action="store_true", help="Refresh cached embeddings through the API")
    args = parser.parse_args(argv)
    if args.no_index and args.reembed:
        parser.error("--reembed cannot be combined with --no-index")
    try:
        rag.init_database()
        if not args.rebuild_only:
            count = ingest_directory(args.directory)
            print(f"Ingested {count} reviewed documents into {rag.DATABASE}.")
        if args.no_index:
            print("Index unchanged. Next: python ingest.py --rebuild-only")
        else:
            count = rag.rebuild_index(reembed=args.reembed)
            print(f"Indexed {count} chunks into {rag.INDEX_PATH}. Metadata and cached vectors are in SQLite.")
    except (ValueError, FileNotFoundError) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from None
    except Exception as exc:
        print(f"Ingestion failed ({type(exc).__name__}). Check settings, credentials and network access.", file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
