"""Local search fallback (Search Mode only — never curriculum order, see
ARCHITECTURE.md §2) backed by SQLite's built-in FTS5 extension. Used
whenever LightRAG isn't installed/configured — which is the default local
mode per the "external dependencies must not block the project" brief.

Split into two layers on purpose:
  - the `*_core` functions take a plain sqlite3 connection and plain tuples,
    with zero SQLModel/SQLAlchemy dependency, so they can be (and are, see
    tests/test_local_search.py) unit tested with nothing but the standard
    library — genuinely executed in the build sandbox, unlike the
    SQLModel-session-based wrappers below them, which need sqlalchemy
    installed (not available in this sandbox — see README).
  - the session-based wrappers pull SourceBlock rows via the app's normal
    SQLModel session, then open a second, plain sqlite3 connection to the
    same database file to do the FTS work.

Only works against a SQLite-backed DATABASE_URL. Production on Postgres
should use the LightRAG adapter, or Postgres's own full-text search — not
implemented here, out of scope for local mode.
"""
from __future__ import annotations
import sqlite3
from dataclasses import dataclass


class LocalSearchUnavailable(RuntimeError):
    pass


@dataclass
class LocalSearchResult:
    text: str
    source_block_id: str
    section_id: str | None
    score: float  # higher = more relevant (inverted bm25)


# ---- core: plain sqlite3, no ORM ----

def ensure_fts_table_core(conn: sqlite3.Connection) -> None:
    conn.execute(
        "CREATE VIRTUAL TABLE IF NOT EXISTS source_block_fts "
        "USING fts5(text, source_block_id UNINDEXED, book_id UNINDEXED, section_id UNINDEXED)"
    )


def index_blocks_core(conn: sqlite3.Connection, book_id: str,
                       rows: list[tuple[str, str, str | None]]) -> int:
    """rows: list of (text, source_block_id, section_id)."""
    ensure_fts_table_core(conn)
    conn.execute("DELETE FROM source_block_fts WHERE book_id = ?", (book_id,))
    conn.executemany(
        "INSERT INTO source_block_fts (text, source_block_id, book_id, section_id) VALUES (?, ?, ?, ?)",
        [(text, sb_id, book_id, section_id or "") for text, sb_id, section_id in rows if text],
    )
    conn.commit()
    return len(rows)


def _fts_query(query: str) -> str:
    tokens = [t for t in query.replace('"', " ").split() if t]
    if not tokens:
        return '""'
    return " OR ".join(f'"{t}"' for t in tokens)


def search_core(conn: sqlite3.Connection, book_id: str, query: str,
                 section_id: str | None = None, limit: int = 10) -> list[LocalSearchResult]:
    ensure_fts_table_core(conn)
    sql = (
        "SELECT text, source_block_id, section_id, bm25(source_block_fts) as rank "
        "FROM source_block_fts WHERE source_block_fts MATCH ? AND book_id = ?"
    )
    params: list = [_fts_query(query), book_id]
    if section_id:
        sql += " AND section_id = ?"
        params.append(section_id)
    sql += " ORDER BY rank LIMIT ?"
    params.append(limit)
    try:
        cur = conn.execute(sql, params)
    except sqlite3.OperationalError:
        return []  # e.g. an empty/degenerate FTS query — fail closed, not with a 500
    return [
        LocalSearchResult(text=r[0], source_block_id=r[1], section_id=r[2] or None, score=-r[3])
        for r in cur.fetchall()
    ]


# ---- session-based wrappers used by app/rag/book_rag.py ----

def _sqlite_path_from_url(database_url: str) -> str:
    prefix = "sqlite:///"
    if not database_url.startswith(prefix):
        raise LocalSearchUnavailable(
            f"Local FTS5 search only supports SQLite; DATABASE_URL={database_url!r} "
            "is not a sqlite:/// URL. Use the LightRAG adapter for Postgres/production."
        )
    return database_url[len(prefix):]


def index_book_for_local_search(session, book_id: str) -> int:
    from sqlmodel import select
    from app.db import models as db
    from app.config import settings

    blocks = session.exec(select(db.SourceBlock).where(db.SourceBlock.book_id == book_id)).all()
    rows = [(b.text, b.id, b.section_id) for b in blocks if b.text]
    conn = sqlite3.connect(_sqlite_path_from_url(settings.database_url))
    try:
        return index_blocks_core(conn, book_id, rows)
    finally:
        conn.close()


def local_search(book_id: str, query: str, section_id: str | None = None, limit: int = 10) -> list[LocalSearchResult]:
    from app.config import settings

    conn = sqlite3.connect(_sqlite_path_from_url(settings.database_url))
    try:
        return search_core(conn, book_id, query, section_id=section_id, limit=limit)
    finally:
        conn.close()
