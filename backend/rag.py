"""Local SQLite evidence and FAISS retrieval. Ingestion builds the index offline."""

import hashlib
import json
import os
import sqlite3
import tempfile
from contextlib import contextmanager
from pathlib import Path

import faiss
import numpy as np
from dotenv import load_dotenv

from . import llm


ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")


def resolve_path(value: str | Path) -> Path:
    path = Path(value).expanduser()
    return (path if path.is_absolute() else ROOT / path).resolve()


DATABASE = resolve_path(os.getenv("HPV_DATABASE", "storage/hpv.sqlite"))
INDEX_PATH = resolve_path(os.getenv("HPV_INDEX", "storage/evidence.faiss"))
TOP_K = int(os.getenv("RETRIEVAL_TOP_K", "5"))
MIN_SCORE = float(os.getenv("RETRIEVAL_MIN_SCORE", "0.25"))
if not 1 <= TOP_K <= 20 or not -1 <= MIN_SCORE <= 1:
    raise ValueError("RETRIEVAL_TOP_K must be 1 to 20 and RETRIEVAL_MIN_SCORE must be -1 to 1")

REBUILD = "Index missing, stale, corrupt or incompatible. Run: python ingest.py --rebuild-only (use --reembed to refresh embeddings)."


class IndexIncompatible(RuntimeError):
    pass


def stable_id(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@contextmanager
def connect():
    """One short transaction per call; connections are never shared across threads."""
    db = sqlite3.connect(DATABASE, timeout=10)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    try:
        yield db
        db.commit()
    except BaseException:
        db.rollback()
        raise
    finally:
        db.close()


def init_database() -> None:
    """Create missing tables without replacing existing documents or query logs."""
    DATABASE.parent.mkdir(parents=True, exist_ok=True)
    with connect() as db:
        db.executescript("""
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS documents (
                id TEXT PRIMARY KEY, title TEXT NOT NULL, url TEXT NOT NULL UNIQUE,
                publisher TEXT NOT NULL, published_date TEXT, retrieved_date TEXT NOT NULL,
                content TEXT NOT NULL, fixture INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS chunks (
                id TEXT PRIMARY KEY, document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
                ordinal INTEGER NOT NULL, content TEXT NOT NULL,
                UNIQUE(document_id, ordinal)
            );
            CREATE TABLE IF NOT EXISTS embeddings (
                chunk_id TEXT REFERENCES chunks(id) ON DELETE CASCADE,
                model TEXT NOT NULL, dimensions INTEGER NOT NULL, vector BLOB NOT NULL,
                PRIMARY KEY(chunk_id, model, dimensions)
            );
            CREATE TABLE IF NOT EXISTS index_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS index_entries (
                position INTEGER PRIMARY KEY, chunk_id TEXT NOT NULL UNIQUE REFERENCES chunks(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS query_logs (
                request_id TEXT PRIMARY KEY, timestamp TEXT NOT NULL, input_type TEXT NOT NULL,
                claim TEXT, retrieved TEXT NOT NULL DEFAULT '[]', verdict TEXT,
                cited_ids TEXT NOT NULL DEFAULT '[]', generation_model TEXT NOT NULL,
                embedding_model TEXT NOT NULL, duration_ms REAL,
                error_status TEXT, status TEXT NOT NULL, token_usage TEXT NOT NULL DEFAULT '{}'
            );
        """)


def chunks(include_fixtures: bool = False) -> list[dict]:
    with connect() as db:
        return [dict(row) for row in db.execute("""
            SELECT c.id, c.content, c.ordinal, d.id AS document_id, d.title, d.url,
                   d.publisher, d.published_date, d.retrieved_date, d.fixture
            FROM chunks c JOIN documents d ON d.id=c.document_id
            WHERE (? OR d.fixture=0) ORDER BY c.id
        """, (int(include_fixtures),))]


def fingerprint(rows: list[dict]) -> str:
    return stable_id(json.dumps(rows, sort_keys=True, ensure_ascii=False))


def vectors(values: list | np.ndarray) -> np.ndarray:
    data = np.asarray(values, dtype="float32")
    if data.ndim != 2 or data.shape[1] != llm.EMBEDDING_DIMENSIONS or not np.isfinite(data).all():
        raise ValueError("Embedding response has invalid dimensions or values")
    if np.any(np.linalg.norm(data, axis=1) == 0):
        raise ValueError("Embedding response contains a zero vector")
    data = np.ascontiguousarray(data)
    faiss.normalize_L2(data)
    return data


def rebuild_index(reembed: bool = False, *, include_fixtures: bool = False) -> int:
    """Reuse cached embeddings unless a source changed or --reembed was requested."""
    rows = chunks(include_fixtures)
    with connect() as db:
        if reembed:
            db.execute("DELETE FROM embeddings WHERE model=? AND dimensions=?",
                       (llm.EMBEDDING_MODEL, llm.EMBEDDING_DIMENSIONS))
        cached = {row["chunk_id"]: np.frombuffer(row["vector"], dtype="float32").copy()
                  for row in db.execute("SELECT * FROM embeddings WHERE model=? AND dimensions=?",
                                        (llm.EMBEDDING_MODEL, llm.EMBEDDING_DIMENSIONS))}
    missing = [row for row in rows if row["id"] not in cached]
    for start in range(0, len(missing), 64):
        batch = missing[start:start + 64]
        raw, _usage = llm.embed([row["content"] for row in batch])
        data = vectors(raw)
        if len(data) != len(batch):
            raise ValueError("Embedding response count mismatch")
        with connect() as db:
            for row, vector in zip(batch, data):
                cached[row["id"]] = vector
                db.execute("INSERT OR REPLACE INTO embeddings VALUES (?,?,?,?)",
                           (row["id"], llm.EMBEDDING_MODEL, llm.EMBEDDING_DIMENSIONS, vector.tobytes()))
    index = faiss.IndexFlatIP(llm.EMBEDDING_DIMENSIONS)
    if rows:
        index.add(vectors([cached[row["id"]] for row in rows]))
    INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=INDEX_PATH.parent, suffix=".faiss")
    os.close(fd)
    try:
        faiss.write_index(index, temporary)
        digest = hashlib.sha256(Path(temporary).read_bytes()).hexdigest()
        os.replace(temporary, INDEX_PATH)
        meta = {"model": llm.EMBEDDING_MODEL, "dimensions": str(llm.EMBEDDING_DIMENSIONS),
                "corpus_hash": fingerprint(rows), "file_hash": digest,
                "fixtures": str(include_fixtures), "format": "1"}
        with connect() as db:
            db.execute("DELETE FROM index_entries")
            db.executemany("INSERT INTO index_entries VALUES (?,?)", [(i, row["id"]) for i, row in enumerate(rows)])
            db.execute("DELETE FROM index_meta")
            db.executemany("INSERT INTO index_meta VALUES (?,?)", meta.items())
    finally:
        Path(temporary).unlink(missing_ok=True)
    return len(rows)


def load_index(rows: list[dict], *, include_fixtures: bool = False) -> faiss.Index:
    with connect() as db:
        meta = dict(db.execute("SELECT key,value FROM index_meta"))
        mapping = [row[0] for row in db.execute("SELECT chunk_id FROM index_entries ORDER BY position")]
    expected = {"model": llm.EMBEDDING_MODEL, "dimensions": str(llm.EMBEDDING_DIMENSIONS),
                "corpus_hash": fingerprint(rows), "fixtures": str(include_fixtures), "format": "1"}
    if any(meta.get(key) != value for key, value in expected.items()) or mapping != [row["id"] for row in rows]:
        raise IndexIncompatible(REBUILD)
    try:
        if hashlib.sha256(INDEX_PATH.read_bytes()).hexdigest() != meta.get("file_hash"):
            raise IndexIncompatible(REBUILD)
        index = faiss.read_index(str(INDEX_PATH))
        if index.d != llm.EMBEDDING_DIMENSIONS or index.ntotal != len(mapping):
            raise IndexIncompatible(REBUILD)
    except (OSError, RuntimeError) as exc:
        raise IndexIncompatible(REBUILD) from exc
    return index


def search(claim: str, *, include_fixtures: bool = False) -> tuple[list[dict], dict]:
    """Return relevant passages with stored source metadata, scores and evidence IDs."""
    rows = chunks(include_fixtures)
    if not rows:
        return [], {}
    index = load_index(rows, include_fixtures=include_fixtures)
    raw, usage = llm.embed([claim])
    query = vectors(raw)
    if len(query) != 1:
        raise ValueError("Expected a single query embedding")
    scores, positions = index.search(query, min(TOP_K, len(rows)))
    hits = [dict(rows[int(pos)], score=float(score), evidence_id="E_" + rows[int(pos)]["id"])
            for score, pos in zip(scores[0], positions[0])
            if pos >= 0 and float(score) >= MIN_SCORE]
    return hits, usage
