/**
 * Thin client for the two route groups this integration added to the
 * backend — /engine/* and /magnus/* (see backend/app/api/routes/). Mirrors
 * js/bookcoach/api-client.js's shape so there's one consistent pattern
 * across the whole frontend (spec §23), not scattered fetch() calls.
 *
 * ChessMate's own board/analysis panel still uses its in-browser WASM
 * Stockfish (vendor/stockfish) for move-by-move live analysis — that's
 * existing, working, zero-latency behavior and the integration spec is
 * explicit that it should not be touched. This client is for the NEW
 * cross-cutting calls that need the shared backend: Magnus predictions,
 * historical Magnus evidence, and the unified coach-evidence endpoint that
 * combines engine + Magnus for a single user move.
 */
const BASE = window.CHESSMATE_API_BASE || "http://localhost:8000";

async function postJson(path, body) {
  const res = await fetch(BASE + path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(path + " -> HTTP " + res.status);
  return res.json();
}

async function getJson(path) {
  const res = await fetch(BASE + path);
  if (!res.ok) throw new Error(path + " -> HTTP " + res.status);
  return res.json();
}

export const ChessMateAPI = {
  engineStatus: () => getJson("/engine/status"),
  evaluate: (fen, depth = 15) => postJson("/engine/evaluate", { fen, depth }),

  magnusStatus: () => getJson("/magnus/status"),
  magnusPredict: (fen, top_k = 5, previous_moves = null) =>
    postJson("/magnus/predict", { fen, top_k, previous_moves }),
  magnusHistorical: (fen, top_k = 5) =>
    getJson(`/magnus/historical?fen=${encodeURIComponent(fen)}&top_k=${top_k}`),
  magnusCompare: (fen, user_move) => postJson("/magnus/compare", { fen, user_move }),
  coachEvidence: (fen, user_move) => postJson("/magnus/coach-evidence", { fen, user_move }),
};
