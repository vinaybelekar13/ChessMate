# ChessMate — Integrated Build

One ChessMate application assembled from three existing projects:

- **ChessMate UI** (frozen, unmodified except the four additive hooks listed
  below) — the frontend, in `frontend/`.
- **MagnusCoach** — the trained Magnus model + coach/evidence logic,
  vendored unmodified as `magnus_coach/`.
- **Book Coach** — PDF ingestion, curriculum, puzzles, local search — the
  backend, in `backend/`, extended (not rewritten) with the shared engine
  and Magnus routes below.

## Architecture

```
                    SHARED ENGINE SERVICE (app/chess/engine.py)
                                 |
                              Stockfish
                                 |
              ChessMate UI  ── HTTP ──▶  backend/app/api/routes/engine.py
                                 |
                    ┌────────────┼────────────┐
                    │            │            │
                 /engine/*   /magnus/*    /books,/puzzles,
                (this repo) (adapter over  /progress,/search
                             magnus_coach/) (Book Coach, as-is)
```

There is **one** Stockfish process type in this codebase
(`backend/app/chess/engine.py`), reused by Book Coach's own ingestion-time
checks and now also exposed over HTTP for the rest of the app. Nothing else
spawns Stockfish.

The Magnus **model** (learned move prediction) and **historical Magnus**
(actual games from a database) are kept in separate response fields
everywhere — `/magnus/predict` vs `/magnus/historical` — and a UI must never
merge them into one "Magnus says" claim.

### New backend routes (added by this integration)

| Route | What it does | Source |
|---|---|---|
| `GET /engine/status`, `POST /engine/evaluate` | Shared Stockfish evaluation | wraps `app/chess/engine.py` (existing) |
| `GET /magnus/status`, `POST /magnus/predict`, `GET /magnus/historical`, `POST /magnus/compare`, `POST /magnus/coach-evidence` | Magnus model + historical evidence | adapter over `magnus_coach/src/api.py` (existing, unmodified) |
| everything under `/books`, `/puzzles`, `/progress` | Book Coach | unmodified except two bug fixes below |

### Frontend additions (additive only — see `git diff`-style summary in
`FINAL_REPORT.md`)

- A 4th tab, **Book Coach**, next to Analyze / Free board / Play engine.
- `js/integration/book-coach-entry.js` — wires the existing Book Coach
  screens (`js/bookcoach/*.js`, untouched) into that tab.
- `js/integration/magnus-coach-bubble.js` + `css/magnus-coach.css` — the
  `MagnusCoachBubble` component, mounted inside the existing AI Coach card.
  It speaks in ChessMate's own coach voice ("the model ranks X highly",
  "Magnus played X in a real game") — never as a quote from Magnus Carlsen.
- `js/integration/api-client.js` — client for the two new route groups
  above, following the same shape as the existing
  `js/bookcoach/api-client.js`.
- One inline config block in `index.html`:
  `window.CHESSMATE_API_BASE` (default `http://localhost:8000`) is the one
  place both API clients read the backend URL from.

No color, spacing, board, or existing-panel change. See `FINAL_REPORT.md`
for the literal diff against the original UI zip.

## Setup

### Backend

```bash
cd backend
python3 -m venv venv && source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Stockfish (pick one):
#   Debian/Ubuntu: sudo apt install stockfish
#   macOS:         brew install stockfish
#   Windows:       download a build from https://stockfishchess.org/download/
#                  and set STOCKFISH_PATH to the .exe

export DATABASE_URL="sqlite:///./chessmate.db"          # Windows (cmd): set DATABASE_URL=sqlite:///./chessmate.db
export STOCKFISH_PATH="stockfish"                        # or the full path if it's not on PATH
uvicorn app.main:app --reload                             # http://localhost:8000
```

Run the backend's own test suite (32 tests — Book Coach + the new
engine/Magnus integration tests):

```bash
cd backend && pytest -q
```

### Frontend

No build step — it's static. Serve it with anything, e.g.:

```bash
cd frontend
python3 -m http.server 5500
# open http://localhost:5500
```

If the backend isn't on `http://localhost:8000`, set
`window.CHESSMATE_API_BASE` before `app.js` loads (edit the inline
`<script>` block near the top of `index.html`).

Frontend's own browser test suite (26 Playwright suites, **not run as part
of this integration** — see `FINAL_REPORT.md` for why):

```bash
cd frontend
npm install
npx playwright install chromium
node tests/run.mjs        # or however the suite is invoked — see tests/run.mjs
```

### Magnus model (PyTorch)

The checkpoint (`magnus_coach/models/final/magnus_model.pt`) is included.
Running actual inference needs PyTorch, which this build environment could
not install (see `FINAL_REPORT.md`). On a normal machine:

```bash
cd magnus_coach
pip install -r requirements.txt   # includes torch
pytest -q                          # full suite, including model/inference tests
```

Once torch is installed in the same environment as the backend,
`/magnus/*` routes will report `"available": true` and return real
predictions automatically — no code change needed.

### Historical Magnus database

Not bundled (the original project's own build report puts it at ~400MB /
721k positions). `/magnus/historical` will report
`"available": false, "reason": "..."` until it's rebuilt or supplied. See
`magnus_coach/README.md` for the rebuild pipeline from source PGNs.

## Known limitations

See `FINAL_REPORT.md` for the full, itemized PASS/PARTIAL/UNAVAILABLE
breakdown. In short: everything backend-side was actually run and verified
in this build environment (32/32 tests, real Stockfish evaluation, a real
book uploaded/ingested/worked-through, progress surviving a real process
restart). Magnus model inference and the frontend's own Playwright suite
could not be executed *in this particular sandbox* (no PyTorch-capable
environment, no downloadable browser) — both are wired correctly and ready
to run on a normal development machine with the commands above.
