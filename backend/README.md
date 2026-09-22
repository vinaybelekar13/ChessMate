# Book Coach backend

## Local development (no Docker, no Postgres — works on Windows)

```bash
python -m venv venv
venv\Scripts\activate            # Windows; use `source venv/bin/activate` on macOS/Linux
pip install -r requirements.txt
copy .env.example .env           # Windows; `cp` on macOS/Linux — defaults are already SQLite
uvicorn app.main:app --reload --port 8080
```

That's it. No `docker compose up`, no Postgres install, no API key required.
On first request, `init_db()` (see `app/db/session.py`) creates
`bookcoach.db` (a plain SQLite file) in the working directory automatically.

Verify it's up:
```bash
curl http://localhost:8080/health
```

## What works with zero configuration (LOCAL mode)

| Piece | Local fallback | File |
|---|---|---|
| PDF extraction | `pdfplumber`-based text/heading extraction (no OCR) | `app/ingestion/local_pdf_adapter.py` |
| Search ("Ask the book", "Find in book") | SQLite FTS5 keyword search | `app/rag/local_search.py` |
| Coach narration | Template-based, uses the book's actual extracted text verbatim, labeled `LOCAL GROUNDED MODE` | `app/coach/local_coach.py` |
| Chess move/puzzle checking | String-normalized SAN comparison (`app/chess/validation.py`); full legality checking additionally available once `python-chess` is installed | `app/chess/validation.py` |
| Engine evaluation | Returns `{"available": false, "reason": ...}` rather than a fabricated score | `app/chess/engine.py` |
| Database | SQLite file, zero setup | `app/db/session.py` |

Every one of these has an "upgrade path" (MinerU, LightRAG, Anthropic,
Stockfish, Postgres) that the app switches to automatically once it's
installed/configured — see `ARCHITECTURE.md §8` for the exact fallback
chain and why the local versions are genuine implementations, not stubs.

## Running the tests

`pytest` itself wasn't installable in the build sandbox this project was
developed in (no network access to PyPI beyond a package allowlist), so a
small stdlib-only runner is included and has actually been run — 26/26
passing as of the last change:

```bash
python scripts/run_tests.py
```

On your machine, once you've `pip install -r requirements.txt` (which
includes `pytest` implicitly via nothing — add it yourself:
`pip install pytest`), you can also just run:

```bash
pytest tests/
```

Both discover the same `tests/test_*.py` files; the custom runner exists
only because this project's own build/verification environment couldn't
install pytest, not because of anything about your machine.

## End-to-end smoke test

```bash
python scripts/e2e_smoke_test.py
```

Actually uploads `tests/fixtures/sample_book.pdf` through the real
ingestion pipeline, walks the curriculum, attempts a puzzle, searches the
book, and asks it a question — then closes and reopens the SQLite
connection to confirm progress actually persisted across a restart. See
the script's own output for a step-by-step report.

## Directory map

- `app/models/schemas.py` — Pydantic request/response + domain models.
- `app/db/models.py` — SQLModel ORM tables (Book, Chapter, Section, … Attempt).
- `app/ingestion/` — PDF → structured book pipeline. Fallback chain:
  MinerU → Docling → `local_pdf_adapter.py` (always available).
- `app/rag/` — `BookRAG` interface. Fallback chain: LightRAG →
  `local_search.py` (SQLite FTS5, always available).
- `app/coach/` — `BookCoach` interface, prompts, and `local_coach.py` (the
  no-LLM narrator used whenever `ANTHROPIC_API_KEY` isn't set).
- `app/chess/` — python-chess validation + Stockfish adapter (both degrade
  gracefully when unavailable rather than raising).
- `app/api/routes/` — FastAPI routers.
- `app/player_model.py` — per-user concept accuracy + adaptive review detours.
- `tests/` — see "Running the tests" above. `tests/fixtures/` has a small
  synthetic chess-book PDF (and its generator script) used for real,
  executed ingestion tests rather than mocks.
- `scripts/run_tests.py`, `scripts/e2e_smoke_test.py` — see above.

## Known gaps (see ARCHITECTURE.md §10 for the full list)

- Diagram → FEN board-vision reconstruction is not implemented (needs a
  trained model); diagrams are stored with `fen=None, verified=False` and
  the frontend should show "position requires verification".
- Puzzle *solutions* are never invented — book puzzles are detected and
  linked to a position, but `solution_line_san` stays empty unless you wire
  up real solution-text extraction. Don't present an empty solution as "the
  book has no solution" vs "we haven't extracted it yet" without checking
  which is true for your book.
- MinerU/Docling/LightRAG adapters are written against their documented
  APIs but untested (couldn't be installed in the build sandbox) — expect
  to need to fix up the exact call signatures against whatever version you
  install.
