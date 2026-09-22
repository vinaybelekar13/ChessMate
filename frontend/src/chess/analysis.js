// ChessMate - game analysis domain.
// The UI should eventually call these functions instead of
// implementing chess-analysis rules itself.

import {
  evalWhite,
  wpWhite,
  phaseOf
} from "./position.js";

/**
 * Convert a sequence of engine evaluations into
 * simple position snapshots.
 */
export function buildEvaluationTimeline(evaluations = []) {
  return evaluations.map((evaluation, index) => ({
    ply: index + 1,
    eval: evalWhite(evaluation),
    winPct: wpWhite(evaluation)
  }));
}

/**
 * Determine the broad game phase for a position.
 */
export function getGamePhase(fen, ply, openingEndPly = 0) {
  return phaseOf(fen, ply, openingEndPly);
}

/**
 * Calculate the largest evaluation swing in a game.
 */
export function largestEvaluationSwing(evaluations = []) {
  if (evaluations.length < 2) return 0;

  let largest = 0;

  for (let i = 1; i < evaluations.length; i++) {
    const previous = evalWhite(evaluations[i - 1]);
    const current = evalWhite(evaluations[i]);

    largest = Math.max(
      largest,
      Math.abs(current - previous)
    );
  }

  return largest;
}