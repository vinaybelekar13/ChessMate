// ChessMate - game analysis orchestrator.
//
// This is the domain-level entry point for analysing a game:
//
//   GAME -> ENGINE ANALYSIS -> REVIEW -> MOTIFS -> STRUCTURED REPORT
//
// UI code should not need to know that "engine analysis" and
// "review" both currently run through js/review.js's reviewGame(), or
// that "motifs" are extracted from the same move records. That wiring
// lives here so it can change later (a review cache, a server-side
// analyzer, book/master-game positions) without callers noticing.

import { reviewGame } from "./legacy/review-adapter.js";
import { buildReviewReport, criticalMistakes } from "./review.js";
import { buildMotifProfile, motifsFromReviewedMoves } from "./motifs.js";
import { buildEvaluationTimeline, largestEvaluationSwing } from "./analysis.js";

export class GameAnalyzer {
  constructor({ engine = null } = {}) {
    this.engine = engine;
  }

  /**
   * Run a full game analysis: engine evaluation of every position,
   * move classification, and motif extraction, then combine the
   * results into a single structured report.
   *
   * `moves` must be in the shape reviewGame() expects:
   * [{ san, from, to, uci, color, fenBefore, fenAfter, moveNo }].
   *
   * Returns null if the analysis was cancelled via opts.signal.
   */
  async analyzeGame({
    game = null,
    moves = [],
    startFen,
    depth,
    bookPlies,
    onProgress,
    signal
  } = {}) {
    if (!this.engine) {
      throw new Error("GameAnalyzer requires an engine to analyze a game.");
    }

    const legacyReview = await reviewGame(this.engine, moves, startFen, {
      depth,
      bookPlies,
      onProgress,
      signal
    });

    // reviewGame() itself returns null when the signal was cancelled
    // mid-analysis; preserve that rather than building a report out of
    // partial data.
    if (!legacyReview) return null;

    return this.buildReportFromLegacyReview({ game, legacyReview });
  }

  /**
   * Build the structured report from a review already produced by
   * reviewGame() - useful for cached analysis, imported reviews, or
   * (later) master/Magnus games and book positions that were reviewed
   * ahead of time.
   */
  buildReportFromLegacyReview({ game = null, legacyReview }) {
    const moves = legacyReview.moves || [];
    const evaluations = moves.map(move => ({
      cp: move.mateWhite ? null : move.cpWhite,
      mate: move.mateWhite
    }));
    const motifEvents = motifsFromReviewedMoves(moves);
    const review = buildReviewReport(moves, legacyReview);

    return {
      game,
      // Temporary compatibility bridge for the existing browser UI.
      // The UI can keep consuming the proven reviewGame() result while the
      // richer domain report becomes the future coach-facing contract.
      legacyReview,
      evaluationTimeline: buildEvaluationTimeline(evaluations),
      largestEvaluationSwing: largestEvaluationSwing(evaluations),
      review,
      motifs: buildMotifProfile(motifEvents),
      criticalPositions: criticalMistakes(moves),
      metadata: {
        analyzedMoves: moves.length,
        detectedMotifs: motifEvents.length,
        opening: legacyReview.opening
      }
    };
  }

  /**
   * Lower-level entry point: build a report from move records that are
   * already classified elsewhere, in the same shape reviewGame()
   * produces (each needs at least `cls`, `loss`, `color`, `phase`,
   * `cpWhite`/`mateWhite`, and optionally `.motif`). Does not run the
   * engine itself.
   */
  buildReport({ game = null, moves = [], legacyReview = null } = {}) {
    return this.buildReportFromLegacyReview({
      game,
      legacyReview: legacyReview || { moves, accWhite: null, accBlack: null, est: null, phases: null, opening: null }
    });
  }

  /**
   * Return the engine associated with this analyzer.
   */
  getEngine() {
    return this.engine;
  }
}

/**
 * Convenience factory.
 */
export function createGameAnalyzer(options = {}) {
  return new GameAnalyzer(options);
}
