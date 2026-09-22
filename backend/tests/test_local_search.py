"""Runs against a real in-memory SQLite connection with FTS5 — no ORM, no
mocks. Tests only the `*_core` functions from app.rag.local_search, since
the session-based wrappers need sqlalchemy (not installed in this sandbox).
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import sqlite3
from app.rag.local_search import index_blocks_core, search_core


def _fresh_conn():
    return sqlite3.connect(":memory:")


def test_index_and_search_finds_relevant_block():
    conn = _fresh_conn()
    rows = [
        ("A weak square is one that can no longer be defended by a pawn.", "sb1", "sec1"),
        ("The knight is the ideal piece to occupy an outpost.", "sb2", "sec1"),
        ("Castling early improves king safety.", "sb3", "sec2"),
    ]
    n = index_blocks_core(conn, "book1", rows)
    assert n == 3

    results = search_core(conn, "book1", "weak square")
    assert len(results) >= 1
    assert results[0].source_block_id == "sb1"


def test_search_is_scoped_to_book_id():
    conn = _fresh_conn()
    index_blocks_core(conn, "book1", [("Outposts are strong in the endgame.", "sb1", "sec1")])
    index_blocks_core(conn, "book2", [("Outposts are strong in the endgame.", "sb2", "sec1")])
    results = search_core(conn, "book1", "outposts")
    assert all(r.source_block_id == "sb1" for r in results)


def test_search_can_be_scoped_to_a_section():
    conn = _fresh_conn()
    rows = [
        ("Isolated pawns can be weak in the endgame.", "sb1", "sec1"),
        ("Isolated pawns can also be a strength in the middlegame.", "sb2", "sec2"),
    ]
    index_blocks_core(conn, "book1", rows)
    results = search_core(conn, "book1", "isolated pawns", section_id="sec2")
    assert len(results) == 1
    assert results[0].source_block_id == "sb2"


def test_reindexing_a_book_replaces_old_entries():
    conn = _fresh_conn()
    index_blocks_core(conn, "book1", [("old content about forks", "sb1", "sec1")])
    index_blocks_core(conn, "book1", [("new content about pins", "sb2", "sec1")])
    results = search_core(conn, "book1", "forks")
    assert results == []
    results = search_core(conn, "book1", "pins")
    assert len(results) == 1


def test_empty_query_fails_closed_not_with_an_exception():
    conn = _fresh_conn()
    index_blocks_core(conn, "book1", [("some text", "sb1", "sec1")])
    results = search_core(conn, "book1", "")
    assert results == []
