// ChessMate - training/puzzle domain module.
//
// Generates training items from a GameAnalyzer report's own reviewed
// positions. Every item's `fen` is a position the player actually
// reached (fenBefore of a real move from the game) - nothing here
// invents a chess position. This is deliberately small: it produces
// data for a future trainer/puzzle UI, not the trainer itself.

const MISTAKE_CLASSES = new Set(["inaccuracy", "mistake", "blunder"]);

// Loss (centipawns) -> a coarse difficulty label. This buckets the
// review engine's own `loss` value; it does not add new judgement.
function difficultyFromLoss(loss) {
  if (loss >= 300) return "hard";
  if (loss >= 100) return "medium";
  return "easy";
}

/**
 * One training item for a mistake move: "find the better move".
 * Uses only fields reviewGame() already attached to the move
 * (fenBefore, san, bestSan, loss, cls, motif, phase, moveNo, color).
 */
function itemFromMistake(move, sourceGame) {
  return {
    fen: move.fenBefore,
    sourceGame: sourceGame || null,
    moveNumber: move.moveNo,
    color: move.color,
    concept: move.motif ? move.motif.kind : move.cls,
    task: "find-better-move",
    playedMove: move.san,
    expectedMove: move.bestSan || null,
    difficulty: difficultyFromLoss(move.loss || 0),
    explanation: {
      classification: move.cls,
      loss: move.loss,
      phase: move.phase,
      // The review's own reason this move was bad, when it had one (js/motifs.js).
      motifText: move.motif ? move.motif.text : null
    },
    // Additive: everything a trainer UI needs to show the answer without re-deriving it.
    // All of it is carried over from the reviewed move; nothing here is new judgement.
    playedFrom: move.from || null,
    playedTo: move.to || null,
    expectedFrom: move.bestFrom || null,
    expectedTo: move.bestTo || null,
    expectedPromo: move.bestPromo || null,
    expectedLine: move.bestLine || null,          // engine PV from this position (UCI)
    bestCpWhite: move.bestCpWhite ?? null,        // eval if the best move had been played
    bestMateWhite: move.bestMateWhite ?? null
  };
}

/**
 * One training item for a detected motif ("what's the tactic here?").
 * `event` is a domain motif event from motifsFromReviewedMoves()
 * (./motifs.js): { motif, text, ply, fen, move, color }.
 */
function itemFromMotif(event, sourceGame) {
  return {
    fen: event.fen,
    sourceGame: sourceGame || null,
    moveNumber: event.ply,
    color: event.color,
    concept: event.motif,
    task: "identify-motif",
    playedMove: event.move,
    expectedMove: null,
    difficulty: "medium",
    explanation: {
      classification: null,
      loss: null,
      motifText: event.text
    }
  };
}

/**
 * Generate training items from a single GameAnalyzer report. Mistakes
 * are prioritized (they carry the clearest "what should have happened"
 * signal via bestSan); motif events without an associated mistake are
 * added after, up to `maxItems`. Order is worst-loss-first among
 * mistakes, so the most valuable review-driven items are not the ones
 * silently dropped when a caller only wants the first few.
 */
export function generateTrainingItems(report, { maxItems = 10 } = {}) {
  if (!report) return [];
  const sourceGame = report.game || null;

  const mistakeItems = report.criticalPositions
    .filter(move => MISTAKE_CLASSES.has(move.cls))
    .sort((a, b) => (b.loss || 0) - (a.loss || 0))
    .map(move => itemFromMistake(move, sourceGame));

  const coveredPlies = new Set(report.criticalPositions.map(m => m.moveNo));
  const motifItems = (report.review.byType ? Object.values(report.review.byType).flat() : [])
    .filter(move => move.motif && !coveredPlies.has(move.moveNo))
    .map((move, i) =>
      itemFromMotif(
        { motif: move.motif.kind, text: move.motif.text, ply: move.moveNo, fen: move.fenBefore, move: move.san, color: move.color },
        sourceGame
      )
    );

  return [...mistakeItems, ...motifItems].slice(0, maxItems);
}

/**
 * Merge training items from several reports (e.g. a player's recent
 * games) into one queue, worst-first. Does not deduplicate across
 * games - the same concept recurring is signal, not noise.
 */
export function generateTrainingQueue(reports = [], options = {}) {
  const items = reports.flatMap(report => generateTrainingItems(report, options));
  return items.sort((a, b) => (b.explanation.loss || 0) - (a.explanation.loss || 0));
}

/**
 * Filter a training queue toward a player's weakest concepts, as
 * reported by PlayerModel.weaknesses (./player-model.js). Concepts not
 * present in `weaknesses` are kept but sorted after weighted ones.
 */
export function prioritizeByWeakness(items = [], weaknesses = []) {
  const weight = new Map(weaknesses.map(w => [w.key, w.count ?? w.averageLoss ?? 0]));
  return [...items].sort((a, b) => (weight.get(b.concept) || 0) - (weight.get(a.concept) || 0));
}
