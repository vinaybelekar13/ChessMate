// ChessMate - tactical motif domain layer.
//
// Motifs are chess concepts detected from positions/moves. This layer is
// UI-independent and will later feed game review, player profiling,
// puzzle generation and adaptive training.
//
// IMPORTANT: motif *detection* is not reimplemented here - js/motifs.js
// (exposed via ./legacy/motifs-adapter.js) is the single source of
// truth, and it decides motifs statically from the position (SEE, board
// geometry, mate search), never from the engine's chosen reply. An
// earlier version of this file defined its own MOTIF_TYPES vocabulary
// ("hanging-piece", "skewer", "zwischenzug", ...) that did not match the
// kinds explainMove() actually returns ("hung-piece", "losing-exchange",
// "allowed-mate", "missed-mate", "missed-material", "fork"), so every
// real motif was silently dropped by normalizeMotif(). MOTIF_TYPES now
// matches the adapter's real output.

export const MOTIF_TYPES = Object.freeze([
  "hung-piece",
  "losing-exchange",
  "fork",
  "allowed-mate",
  "missed-mate",
  "missed-material"
]);

/**
 * Check whether a motif kind is one explainMove() can actually produce.
 */
export function isKnownMotif(motif) {
  return MOTIF_TYPES.includes(String(motif).toLowerCase());
}

/**
 * Normalize a motif kind.
 */
export function normalizeMotif(motif) {
  const value = String(motif || "").trim().toLowerCase();
  return isKnownMotif(value) ? value : null;
}

/**
 * Create a normalized tactical event.
 */
export function createMotifEvent({
  motif,
  text = null,
  ply = null,
  fen = null,
  move = null,
  color = null,
  confidence = null,
  source = "review"
} = {}) {
  return {
    motif: normalizeMotif(motif),
    text,
    ply,
    fen,
    move,
    color,
    confidence,
    source
  };
}

/**
 * Extract domain motif events from move records already produced by
 * reviewGame() (see ./legacy/review-adapter.js). Each reviewed move
 * carries `.motif` as `{ kind, text }` or null - this just normalizes
 * whatever explainMove() found into the domain event shape, it does not
 * detect anything new.
 */
export function motifsFromReviewedMoves(moves = []) {
  const events = [];

  moves.forEach((move, index) => {
    if (!move || !move.motif) return;

    events.push(
      createMotifEvent({
        motif: move.motif.kind,
        text: move.motif.text,
        ply: index + 1,
        fen: move.fenBefore,
        move: move.san || move.uci || null,
        color: move.color,
        source: "review"
      })
    );
  });

  return events;
}

/**
 * Count occurrences of each motif.
 */
export function countMotifs(events = []) {
  const counts = {};
  for (const event of events) {
    const motif = normalizeMotif(event?.motif);
    if (!motif) continue;
    counts[motif] = (counts[motif] || 0) + 1;
  }
  return counts;
}

/**
 * Group tactical events by motif.
 */
export function groupMotifs(events = []) {
  const groups = {};
  for (const event of events) {
    const motif = normalizeMotif(event?.motif);
    if (!motif) continue;
    if (!groups[motif]) groups[motif] = [];
    groups[motif].push(event);
  }
  return groups;
}

/**
 * Find the most common tactical motifs.
 */
export function topMotifs(events = [], limit = 5) {
  return Object.entries(countMotifs(events))
    .sort((a, b) => b[1] - a[1])
    .slice(0, limit)
    .map(([motif, count]) => ({ motif, count }));
}

/**
 * Build a compact tactical profile. This will later become one input
 * into the player model.
 */
export function buildMotifProfile(events = []) {
  const counts = countMotifs(events);
  return {
    totalEvents: events.length,
    uniqueMotifs: Object.keys(counts).length,
    counts,
    top: topMotifs(events)
  };
}
