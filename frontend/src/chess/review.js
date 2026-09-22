// ChessMate - domain review layer.
//
// This module is intentionally UI-independent, and is the bridge between
// raw review data and future AI coaching / player profiling / training
// generation / mistake detection.
//
// IMPORTANT: move classification (best/inaccuracy/mistake/blunder/...),
// sacrifice and only-move detection, accuracy and opening-book detection
// are NOT reimplemented here. js/review.js (exposed via
// ./legacy/review-adapter.js) is the single source of truth for that -
// an earlier version of this file had its own simplified loss-threshold
// classifier that disagreed with it, which is exactly the duplication
// this migration is meant to remove. This file only aggregates and
// reshapes the move records that reviewGame() already produced.

import {
  reviewGame,
  CLASS_ORDER
} from "./legacy/review-adapter.js";

import {
  evalWhite
} from "./position.js";

export { CLASS_ORDER, reviewGame };

const MISTAKE_CLASSES = new Set(["inaccuracy", "mistake", "blunder"]);

/**
 * Raw evaluation change between two positions, White's POV.
 * A generic numeric helper - not a classifier.
 */
export function evaluationChange(before, after) {
  return evalWhite(after) - evalWhite(before);
}

/**
 * Evaluation change from the perspective of the player who moved.
 * A generic numeric helper - not a classifier.
 */
export function playerEvaluationLoss(before, after, color) {
  const change = evaluationChange(before, after);
  return color === "w" ? Math.max(0, -change) : Math.max(0, change);
}

/**
 * Summarize a collection of already-classified move records (the
 * `moves` array reviewGame() returns, or anything shaped like it: each
 * record needs at least `cls`, `loss`, `color`).
 */
export function summarizeReviews(moves = []) {
  const summary = {
    totalMoves: moves.length,
    byClass: {},
    averageLoss: 0
  };

  for (const cls of CLASS_ORDER) summary.byClass[cls] = 0;
  if (!moves.length) return summary;

  let totalLoss = 0;
  for (const move of moves) {
    if (Object.prototype.hasOwnProperty.call(summary.byClass, move.cls)) {
      summary.byClass[move.cls]++;
    }
    totalLoss += move.loss || 0;
  }

  summary.averageLoss = totalLoss / moves.length;
  return summary;
}

/**
 * The most significant mistakes in a game (inaccuracy/mistake/blunder),
 * worst first.
 */
export function criticalMistakes(moves = [], limit = 5) {
  return [...moves]
    .filter(move => MISTAKE_CLASSES.has(move.cls))
    .sort((a, b) => (b.loss || 0) - (a.loss || 0))
    .slice(0, limit);
}

/**
 * Group moves by game phase (opening/middlegame/endgame), as already
 * assigned by reviewGame().
 */
export function mistakesByPhase(moves = []) {
  const phases = { opening: [], middlegame: [], endgame: [] };
  for (const move of moves) {
    if (phases[move.phase]) phases[move.phase].push(move);
  }
  return phases;
}

/**
 * Group moves by their real classification.
 */
export function mistakesByType(moves = []) {
  const grouped = {};
  for (const cls of CLASS_ORDER) grouped[cls] = [];
  for (const move of moves) {
    if (grouped[move.cls]) grouped[move.cls].push(move);
  }
  return grouped;
}

/**
 * Produce a compact analysis object suitable for the future coach
 * orchestrator, from move records already classified by reviewGame().
 *
 * `legacyReview`, when provided, is the full object reviewGame()
 * resolved to - used to carry over accuracy/Elo/opening, which are
 * whole-game results rather than per-move ones.
 */
export function buildReviewReport(moves = [], legacyReview = null) {
  return {
    summary: summarizeReviews(moves),
    criticalMistakes: criticalMistakes(moves),
    byPhase: mistakesByPhase(moves),
    byType: mistakesByType(moves),
    accuracy: legacyReview
      ? {
          white: legacyReview.accWhite,
          black: legacyReview.accBlack,
          estimatedElo: legacyReview.est,
          phases: legacyReview.phases
        }
      : null,
    opening: legacyReview ? legacyReview.opening : null
  };
}
