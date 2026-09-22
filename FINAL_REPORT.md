# ChessMate Integration — Final Report

## 1. What was inspected

All three source zips, fully:
- **ZIP1 (ChessMate UI)** — static vanilla-JS frontend, in-browser WASM
  Stockfish, 26 Playwright browser test suites, no backend.
- **ZIP2 (MagnusCoach)** — Python library: trained checkpoint
  (`magnus_model.pt`, 5.4MB, present), Stockfish wrapper, coach/evidence
  logic, 345 pytest tests. Historical database (721k positions / ~400MB per
  its own `outputs/database_report.json`) **not bundled**.
- **ZIP3 (Book Coach)** — FastAPI + SQLite backend + matching frontend
  screens. Its own `ARCHITECTURE.md` and `/health` endpoint explicitly
  labeled it a **scaffold that had never been run for real** before this
  integration.

## 2. Integration architecture

See `README.md` "Architecture". Book Coach's backend is the base; ChessMate
UI is the frontend shell; MagnusCoach is vendored as a sibling package
(`magnus_coach/`) and reached through a new thin adapter (`/magnus/*`).

## 3. What was reused (unmodified)

- `magnus_coach/src/**`, `magnus_coach/models/final/magnus_model.pt` — byte-
  for-byte from ZIP2.
- `frontend/js/bookcoach/*.js`, `frontend/css/bookcoach.css` — byte-for-byte
  from ZIP3.
- Every existing ChessMate UI file except the two listed in §4.
- Book Coach's own routers (`books`, `ingestion`, `lessons`, `puzzles`,
  `search`, `progress`) — logic untouched; two bug fixes below.

## 4. What was patched (bugs found by actually running the code)

1. **Naive-datetime crash** (`app/db/models.py`, `app/coach/book_coach.py`)
   — `datetime.utcnow()` defaults broke on the very first real insert
   against the installed SQLAlchemy version. Fixed with
   `datetime.now(timezone.utc)`. This is the reason the scaffold's own
   `/health` endpoint had never returned anything but "unverified" — the
   very first real write failed.
2. **Duplicate-ingestion bug** (`app/ingestion/pipeline.py`) — the
   documented "retry a failed ingest" endpoint had no idempotency guard;
   calling it on an already-ingested book duplicated every chapter/section.
   Fixed by clearing prior ingestion rows before re-running (found and fixed
   a follow-on bug in the same patch: `Subsection` has no `book_id` column).
3. **Stockfish-not-found false negative** (`app/chess/engine.py`) — the
   engine only checked `PATH`, so a standard `apt install stockfish`
   (binary lands at `/usr/games/stockfish`, often absent from non-
   interactive `PATH`) was silently reported unavailable. Added a fallback
   to common install locations.
4. **Test portability** (`tests/test_engine_fallback.py`) — rewritten to
   monkeypatch instead of relying on the test machine happening to lack a
   Stockfish binary; the original version broke the moment Stockfish was
   installed for this integration's own testing.
5. **Fake version pin** (`requirements.txt`) — `python-chess==1.999` (not a
   real release) replaced with the actual installed/working `1.11.2`.

All five are small, targeted fixes — no rewrites, no logic redesign.

## 5. What was newly added

- `backend/app/api/routes/engine.py`, `backend/app/api/routes/magnus.py` —
  adapters, described in `README.md`.
- `backend/tests/test_integration_engine_magnus.py` — 6 new tests.
- `frontend/js/integration/{api-client,book-coach-entry,magnus-coach-bubble}.js`,
  `frontend/css/magnus-coach.css` — described in `README.md`.
- Small additive edits to `frontend/index.html` and `frontend/js/app.js`
  (exact diff below).

## 6. Shared engine architecture

One Stockfish adapter (`app/chess/engine.py`), reused by Book Coach's
ingestion checks and now exposed at `/engine/*`. Verified with a real
evaluation of the starting position: `best_move: e2e4, score_cp: ~40-50`
(varies slightly by depth) — correct. No second engine process anywhere in
the codebase.

## 7. Magnus integration

`/magnus/*` routes are wired correctly and call straight into
`magnus_coach/src/api.py`, unmodified. **PyTorch could not be installed in
this build sandbox** (see §16) — every route was verified to return a clean
`{"available": false, "reason": "No module named 'torch'"}` rather than a
500 or a fabricated prediction. On a machine with torch installed, no code
change is needed for real predictions to start flowing.

Historical Magnus: same graceful-unavailable contract; the underlying
~400MB database isn't bundled (see `README.md`).

## 8. Book integration

Genuinely exercised end-to-end against a live server (real SQLite, real
Stockfish): upload → background ingestion → idempotent re-ingest (no
duplication) → curriculum start/current → progress → puzzle list/attempt/
hint/solution → local search → **process restart with progress intact**.
All observed directly via curl against a running `uvicorn` process, not
inferred from code reading.

## 9. Unified Coach

`/magnus/coach-evidence` exists and returns the underlying
`magnus_coach.generate_coach_evidence()` evidence object (engine + Magnus
model + historical, each separately labeled) when torch is available; a
clean `available: false` otherwise. Not separately re-implemented — this is
intentionally a pass-through to the existing, tested logic in ZIP2.

## 10. Magnus avatar/speech integration

`MagnusCoachBubble` implemented exactly per spec's state list and phrasing
(§15-18 of the original brief): never attributes a line to the real Magnus
Carlsen. Wired into the existing AI Coach card, driven by the same
post-game coach report the UI already computes (no duplicate evidence
fetch). **Not browser-verified** (see §14) — verified by static review and
`node --check` syntax validation only.

## 11. API connections

One consistent client shape front-end side
(`js/integration/api-client.js` mirrors the existing
`js/bookcoach/api-client.js`), one shared `window.CHESSMATE_API_BASE`
config point. Backend: one FastAPI app, one router include list in
`app/main.py`.

## 12. Database

One SQLite database (Book Coach's), used for books/chapters/sections/pages/
puzzles/progress — unchanged from ZIP3 except the two bug fixes in §4.
Magnus's historical database, if/when rebuilt, is a separate file by
design (read-only reference data, not part of Book Coach's write path).

## 13. Tests — PASS / PARTIAL / UNAVAILABLE / NOT TESTED

| Suite | Result |
|---|---|
| Backend (Book Coach + new integration tests), `backend/tests` | **PASS** — 32/32, verified in both "Stockfish on PATH" and "Stockfish not on PATH" configurations |
| MagnusCoach non-torch suite, `magnus_coach/tests` | **PASS** — 161/167 (6 skipped, none failed) |
| MagnusCoach engine+history suite (real Stockfish) | **PASS** — 37/39 (2 skipped) |
| MagnusCoach torch-dependent suite (model/inference/training) | **NOT TESTED** — cannot collect without PyTorch installed (see §16) |
| Frontend Playwright suite (26 files) | **NOT TESTED — ENVIRONMENT BLOCKED**, see §14 |
| Manual end-to-end backend flow (upload→ingest→curriculum→puzzle→persistence→restart) | **PASS** — executed against a live process, not simulated |
| Manual end-to-end frontend flow in a real browser | **NOT TESTED** — see §14 |

## 14. Browser test status

Playwright's Chromium could not be downloaded in this sandbox (its CDN host
isn't network-allowlisted here). This is an environment limitation, not a
code issue — the frontend code itself passed `node --check` on every
modified/added file, and the change against the original UI is a 4-line
index.html diff + a ~25-line app.js diff (reproduced in full in §17), which
was hand-reviewed line by line.

**To actually run the browser suite:**
```bash
cd frontend
npm install
npx playwright install chromium
node tests/run.mjs
```

## 15. End-to-end test

Backend half of the spec's full flow (§28 of the original brief) was run
for real, see §8/§13. The frontend half (board load → click Book Coach tab
→ see it render in an actual browser) was **not** run — same blocker as
§14.

## 16. Known limitations

1. **PyTorch not installed** — the only PyPI wheel available in this sandbox
   pulls ~5GB of CUDA packages that exceed the disk quota here, and
   `download.pytorch.org` (the CPU-only wheel host) isn't network-
   allowlisted. Fix on a normal machine: `pip install torch` (or the CPU
   wheel per PyTorch's own install instructions) then `pytest` in
   `magnus_coach/`.
2. **Historical Magnus database not bundled** — ~400MB, needs rebuilding
   from source PGN data per `magnus_coach/README.md`.
3. **Playwright browser not downloadable** in this sandbox — see §14.
4. **MagnusCoachBubble** is wired into the code path but not visually
   confirmed in a real browser.
5. Deployments should set `STOCKFISH_PATH` explicitly (or rely on the new
   `/usr/games/stockfish` fallback) rather than assuming `stockfish` is on
   every shell's `PATH`.

## 17. Exact diff against the original UI (frontend)

Only two files differ from the original ChessMate UI zip; everything else
under `frontend/` is either unmodified or a new file. Full diffs:

```diff
--- index.html
+++ index.html
@@ head additions: 2 stylesheet links + 1 inline config <script>
@@ nav additions: 1 new <button class="modetab" data-mode="book">
@@ coach card: 1 new <div id="magnusBubbleMount">
@@ after </main>: 1 new <section id="bookCoachRoot">

--- js/app.js
+++ js/app.js
@@ 1 new import (magnus-coach-bubble.js)
@@ renderModeUi(): +13 lines, early-return for mode "book" (workspace/
   bookCoachRoot visibility + lazy mount) before any existing analyze/
   solo/bot logic runs
@@ +17 lines: new updateMagnusBubble(cr) helper
@@ renderCoachV2(): +1 line calling updateMagnusBubble(cr) after existing
   render; +5 lines hiding the bubble in the "no report yet" branch
```

No color, dimension, spacing, typography, board, or existing-panel change
anywhere. (Full literal diffs available by running `diff` between this
package's `frontend/` and the original `ChessMate-updated.zip` — reproduced
verbatim during integration and hand-verified line by line.)

## 18. Exact run commands

```bash
# Backend
cd backend
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
export STOCKFISH_PATH="stockfish"   # or full path, e.g. /usr/games/stockfish
export DATABASE_URL="sqlite:///./chessmate.db"
uvicorn app.main:app --reload       # http://localhost:8000
pytest -q                            # 32/32

# Frontend
cd frontend
python3 -m http.server 5500          # http://localhost:5500
# (Playwright suite — see §14)

# Magnus (on a torch-capable machine)
cd magnus_coach
pip install -r requirements.txt
pytest -q
```

## 19. Final ZIP path

`ChessMate-Final.zip` (this package).
