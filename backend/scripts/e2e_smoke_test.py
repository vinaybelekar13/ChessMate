#!/usr/bin/env python3
"""End-to-end smoke test: PDF -> upload -> ingest -> chapters -> sections ->
source blocks -> chess extraction -> curriculum -> lesson -> puzzle attempt
-> progress -> restart-persistence -> search -> ask the book.

Two modes, chosen automatically:

  REAL MODE   — uses the actual app.db (SQLModel), app.ingestion.pipeline,
                app.coach.book_coach, app.rag.book_rag exactly as the FastAPI
                app does. Requires `pip install -r requirements.txt` (fastapi,
                sqlmodel, python-chess, etc.) to have actually happened.

  CORE MODE   — sqlmodel/fastapi aren't importable (e.g. this project's own
                build/verification sandbox, or a fresh checkout before
                `pip install`), so this exercises the same *logic* — the
                local_pdf_adapter / structure_detector / chess_extractor /
                local_search / local_coach modules, which have zero
                sqlmodel/fastapi dependency — against a raw sqlite3 database
                whose schema mirrors app/db/models.py. This is what actually
                ran when this project was built, and is real execution, not
                a mock — it just isn't exercising the FastAPI/SQLModel
                wiring layer itself, which needs those packages installed.

Either way, this script prints which mode it ran in — never silently
pretends one when it did the other.
"""
from __future__ import annotations
import json
import os
import sqlite3
import sys
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

FIXTURE = os.path.join(os.path.dirname(__file__), "..", "tests", "fixtures", "sample_book.pdf")
DB_PATH = os.path.join(os.path.dirname(__file__), "..", "_smoke_test.db")


def _try_real_mode() -> bool:
    try:
        import sqlmodel  # noqa: F401
        import fastapi  # noqa: F401
        return True
    except ImportError:
        return False


def run_real_mode():
    raise NotImplementedError(
        "REAL MODE is written against app.db.session/app.ingestion.pipeline/"
        "app.coach.book_coach/app.rag.book_rag exactly as the FastAPI app "
        "uses them, but sqlmodel/fastapi are not installed in this sandbox, "
        "so it has not been implemented/exercised here to avoid shipping "
        "unexecuted 'real mode' code as if it were tested. Once you have "
        "`pip install -r requirements.txt` done, the fastest genuine e2e "
        "check is to run the actual server (`uvicorn app.main:app`) and "
        "drive it through the /books/upload, /books/{id}/start, "
        "/books/{id}/continue, /puzzles/{id}/attempt, /progress/{u}/{b} "
        "endpoints by hand or with `httpx`/`requests` — every one of those "
        "routes is implemented in app/api/routes/ and calls the exact same "
        "BookCoach/BookRAG/pipeline code CORE MODE below exercises the "
        "logic of."
    )


def run_core_mode():
    print("=" * 60)
    print("CORE MODE — sqlmodel/fastapi not installed; exercising the")
    print("dependency-free logic modules against a raw SQLite schema.")
    print("=" * 60)

    from app.ingestion import local_pdf_adapter, structure_detector, chess_extractor
    from app.rag import local_search
    from app.coach import local_coach
    from app.chess import validation as chess_validation, engine as chess_engine

    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)

    # ---- schema mirroring app/db/models.py (subset needed for this smoke test) ----
    conn = sqlite3.connect(DB_PATH)
    conn.executescript("""
        CREATE TABLE book (id TEXT PRIMARY KEY, title TEXT, status TEXT, extraction_method TEXT, total_pages INTEGER);
        CREATE TABLE chapter (id TEXT PRIMARY KEY, book_id TEXT, order_index INTEGER, title TEXT, start_page INTEGER, end_page INTEGER);
        CREATE TABLE section (id TEXT PRIMARY KEY, chapter_id TEXT, book_id TEXT, order_index INTEGER, title TEXT, start_page INTEGER, end_page INTEGER);
        CREATE TABLE source_block (id TEXT PRIMARY KEY, book_id TEXT, section_id TEXT, block_type TEXT, order_index INTEGER, text TEXT);
        CREATE TABLE puzzle (id TEXT PRIMARY KEY, book_id TEXT, section_id TEXT, source TEXT, original_text TEXT, solution_line_san TEXT);
        CREATE TABLE progress (id TEXT PRIMARY KEY, user_id TEXT, book_id TEXT, current_section_id TEXT, sections_completed TEXT);
    """)
    conn.commit()

    # ---- 1. "upload" ----
    book_id = str(uuid.uuid4())
    conn.execute("INSERT INTO book (id, title, status, extraction_method, total_pages) VALUES (?, ?, ?, ?, ?)",
                 (book_id, "The Synthetic Chess Primer", "processing", None, None))
    conn.commit()
    print(f"\n[1/10] Uploaded book_id={book_id}")

    # ---- 2. ingest: extract (local_pdf fallback, since MinerU/Docling aren't installed) ----
    blocks = local_pdf_adapter.parse(FIXTURE)
    extraction_method = "local_pdf"
    print(f"[2/10] Extracted {len(blocks)} blocks via {extraction_method}")

    # ---- 3. structure detection ----
    hierarchy = structure_detector.build_hierarchy(blocks)
    print(f"[3/10] Detected {len(hierarchy)} chapters: {[c.title for c in hierarchy]}")

    chapter_ids = {}
    section_ids = {}
    for ci, ch in enumerate(hierarchy):
        cid = str(uuid.uuid4())
        chapter_ids[ch.title] = cid
        conn.execute(
            "INSERT INTO chapter (id, book_id, order_index, title, start_page, end_page) VALUES (?,?,?,?,?,?)",
            (cid, book_id, ci, ch.title, ch.start_page, ch.end_page),
        )
        for si, s in enumerate(ch.children):
            sid = str(uuid.uuid4())
            section_ids[s.title] = (sid, s.start_page, s.end_page)
            conn.execute(
                "INSERT INTO section (id, chapter_id, book_id, order_index, title, start_page, end_page) "
                "VALUES (?,?,?,?,?,?,?)",
                (sid, cid, book_id, si, s.title, s.start_page, s.end_page),
            )
    conn.commit()
    print(f"[4/10] Persisted {len(chapter_ids)} chapters, {len(section_ids)} sections")

    def section_for_page(page_number):
        for title, (sid, start, end) in section_ids.items():
            if start <= page_number <= end:
                return sid, title
        return None, None

    # ---- 5. persist source blocks with provenance ----
    n_blocks = 0
    for b in blocks:
        sid, _ = section_for_page(b.page_number)
        conn.execute(
            "INSERT INTO source_block (id, book_id, section_id, block_type, order_index, text) VALUES (?,?,?,?,?,?)",
            (str(uuid.uuid4()), book_id, sid, b.block_type, b.order_index, b.text),
        )
        n_blocks += 1
    conn.commit()
    print(f"[5/10] Persisted {n_blocks} source blocks with section provenance")

    # ---- 6. chess extraction: puzzles + move text ----
    puzzle_candidates = chess_extractor.find_puzzle_candidates(blocks)
    move_blocks = chess_extractor.find_move_text_blocks(blocks)
    puzzle_ids = []
    for cand in puzzle_candidates:
        sid, title = section_for_page(cand.block.page_number)
        if not sid:
            continue
        pid = str(uuid.uuid4())
        conn.execute(
            "INSERT INTO puzzle (id, book_id, section_id, source, original_text, solution_line_san) "
            "VALUES (?,?,?,?,?,?)",
            (pid, book_id, sid, "book", cand.block.text, json.dumps([])),
        )
        puzzle_ids.append(pid)
    conn.commit()
    print(f"[6/10] Found {len(puzzle_candidates)} puzzles ({len(puzzle_ids)} placed in curriculum), "
          f"{len(move_blocks)} move-text blocks (e.g. {move_blocks[0].text[:40]!r})")

    # ---- 7. curriculum walk (book order, not semantic) ----
    ordered_sections = sorted(section_ids.items(), key=lambda kv: (kv[1][1],))  # by start_page
    print(f"[7/10] Curriculum order (by page, never reordered by search): "
          f"{[title for title, _ in ordered_sections]}")

    first_section_id = ordered_sections[0][1][0]
    user_id = "smoke-test-user"
    conn.execute(
        "INSERT INTO progress (id, user_id, book_id, current_section_id, sections_completed) VALUES (?,?,?,?,?)",
        (str(uuid.uuid4()), user_id, book_id, first_section_id, json.dumps([])),
    )
    conn.commit()
    print(f"    Progress started at section_id={first_section_id}")

    # ---- 8. attempt a puzzle (correct + incorrect), using real validation logic ----
    fake_solution = ["Nf5", "Kg8", "Qh5#"]
    wrong = chess_validation.check_move_against_solution("Qxd4", fake_solution)
    right = chess_validation.check_move_against_solution("Nf5", fake_solution)
    assert wrong.correct is False and right.correct is True
    mistake_feedback = local_coach.explain_mistake_locally("Qxd4", None)
    print(f"[8/10] Puzzle attempt check: wrong={wrong.correct}, correct={right.correct}; "
          f"local feedback mode={mistake_feedback['mode']}")

    engine_result = chess_engine.evaluate_fen("8/8/8/8/8/8/8/8 w - - 0 1")
    print(f"    Engine (Stockfish) availability check: available={engine_result['available']} "
          f"(honest — no binary in this sandbox)")

    # ---- 9. search + ask the book (local FTS, never reorders curriculum) ----
    fts_conn = sqlite3.connect(DB_PATH)
    rows = [(r[0], r[1], r[2]) for r in
            conn.execute("SELECT text, id, section_id FROM source_block WHERE text IS NOT NULL")]
    local_search.index_blocks_core(fts_conn, book_id, rows)
    results = local_search.search_core(fts_conn, book_id, "weak square")
    narrative = local_coach.ask_book_locally("what is a weak square?", [r.text for r in results])
    print(f"[9/10] Search Mode found {len(results)} result(s) for 'weak square'; "
          f"ask_book narrative starts: {narrative[:70]!r}...")
    assert len(results) >= 1, "search should have found the weak-square passage"

    # confirm progress pointer was NOT moved by search (curriculum vs search separation)
    still_at = conn.execute(
        "SELECT current_section_id FROM progress WHERE user_id=? AND book_id=?", (user_id, book_id)
    ).fetchone()[0]
    assert still_at == first_section_id, "search must never move the curriculum pointer"
    print("    Confirmed: Search Mode did not move the curriculum pointer.")

    conn.close()
    fts_conn.close()

    # ---- 10. restart: reopen the SQLite file fresh and confirm persistence ----
    conn2 = sqlite3.connect(DB_PATH)
    row = conn2.execute(
        "SELECT current_section_id FROM progress WHERE user_id=? AND book_id=?", (user_id, book_id)
    ).fetchone()
    conn2.close()
    assert row is not None and row[0] == first_section_id
    print(f"[10/10] Reopened {DB_PATH} after 'restart' — progress persisted: "
          f"current_section_id={row[0]}")

    os.remove(DB_PATH)
    print("\nALL STEPS PASSED — CORE MODE end-to-end smoke test succeeded.")
    print("(This validates the ingestion/curriculum/search/puzzle logic and SQLite")
    print(" persistence shape. It does NOT exercise the FastAPI routes or SQLModel")
    print(" ORM layer themselves — install fastapi+sqlmodel and hit the running")
    print(" server to validate those; see REAL MODE note above.)")


if __name__ == "__main__":
    if _try_real_mode():
        run_real_mode()
    else:
        run_core_mode()
