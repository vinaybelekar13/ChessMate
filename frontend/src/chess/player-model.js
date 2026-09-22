// ChessMate - personal player model.
//
// Aggregates GameAnalyzer reports (see ./game-analyzer.js) into a profile
// of a player's tendencies over time. Everything here is derived purely
// by counting/averaging real fields already present on reviewed moves
// (`cls`, `loss`, `phase`, `motif`) - nothing is inferred beyond simple
// arithmetic, and no chess judgement is invented.
//
// This module holds state only in memory; persistence (a save file, a
// database row) is a future concern and does not belong here.

import { CLASS_ORDER } from "./review.js";
import { MOTIF_TYPES } from "./motifs.js";

const PHASES = ["opening", "middlegame", "endgame"];
const MISTAKE_CLASSES = new Set(["inaccuracy", "mistake", "blunder"]);

// Real motif kinds explainMove() can produce, grouped into the weakness
// categories the product spec asks for. This is a fixed lookup, not a
// classifier - it only labels motif kinds that already exist.
const TACTICAL_MOTIFS = new Set(["fork", "hung-piece", "losing-exchange"]);
const CALCULATION_MOTIFS = new Set(["missed-mate", "allowed-mate", "missed-material"]);

function emptyPhaseStat() {
  return { moves: 0, totalLoss: 0, mistakes: 0 };
}

export class PlayerModel {
  constructor() {
    this.gamesAnalyzed = 0;
    this.totalMoves = 0;
    this.classCounts = Object.fromEntries(CLASS_ORDER.map(cls => [cls, 0]));
    this.motifCounts = Object.fromEntries(MOTIF_TYPES.map(m => [m, 0]));
    this.phaseStats = Object.fromEntries(PHASES.map(p => [p, emptyPhaseStat()]));
    this.criticalMistakes = [];
    this.trainingHistory = [];
    this.history = [];
  }

  /**
   * Fold one GameAnalyzer report into the running profile.
   * `meta` can carry caller-supplied context (e.g. { gameId, playedAs }).
   */
  ingestReport(report, meta = {}) {
    if (!report) return this;

    const moves = report.review?.summary ? this._movesFromReport(report) : [];
    this.gamesAnalyzed += 1;
    this.totalMoves += moves.length;

    for (const move of moves) {
      if (Object.prototype.hasOwnProperty.call(this.classCounts, move.cls)) {
        this.classCounts[move.cls]++;
      }
      const phaseStat = this.phaseStats[move.phase];
      if (phaseStat) {
        phaseStat.moves++;
        phaseStat.totalLoss += move.loss || 0;
        if (MISTAKE_CLASSES.has(move.cls)) phaseStat.mistakes++;
      }
    }

    for (const [motif, count] of Object.entries(report.motifs?.counts || {})) {
      if (Object.prototype.hasOwnProperty.call(this.motifCounts, motif)) {
        this.motifCounts[motif] += count;
      }
    }

    this.criticalMistakes.push(
      ...(report.criticalPositions || []).map(move => ({ ...move, gameId: meta.gameId || null }))
    );
    // Keep only the worst mistakes overall so this doesn't grow unbounded
    // across a long history.
    this.criticalMistakes.sort((a, b) => (b.loss || 0) - (a.loss || 0));
    this.criticalMistakes = this.criticalMistakes.slice(0, 50);

    this.history.push({
      gameId: meta.gameId || null,
      analyzedMoves: report.metadata?.analyzedMoves ?? moves.length,
      accuracy: report.review?.accuracy || null,
      opening: report.metadata?.opening || null
    });

    return this;
  }

  _movesFromReport(report) {
    // buildReviewReport() (./review.js) groups moves by type/phase but does
    // not keep the flat list on the report; reconstruct it from those
    // groupings rather than re-deriving anything.
    const moves = [];
    for (const list of Object.values(report.review.byType || {})) moves.push(...list);
    return moves;
  }

  /** Record that a training item was attempted, for future mastery tracking. */
  recordTrainingAttempt(item, { correct = null } = {}) {
    this.trainingHistory.push({
      concept: item?.concept || null,
      fen: item?.fen || null,
      correct,
      at: this.trainingHistory.length
    });
    return this;
  }

  /**
   * A simple exposure-based mastery estimate per concept: how often it has
   * come up in training, and the share of recorded attempts marked
   * correct. Concepts with no recorded attempts have no mastery entry -
   * this is exposure bookkeeping, not a claim about the player's skill.
   */
  get conceptMastery() {
    const byConcept = {};
    for (const attempt of this.trainingHistory) {
      if (!attempt.concept) continue;
      if (!byConcept[attempt.concept]) byConcept[attempt.concept] = { attempts: 0, correct: 0 };
      byConcept[attempt.concept].attempts++;
      if (attempt.correct) byConcept[attempt.concept].correct++;
    }
    return byConcept;
  }

  /**
   * Ranked weaknesses across phases and motifs, worst first. This ranks
   * by real counted quantities (average loss, mistake share, motif
   * frequency) - it does not diagnose *why* a weakness exists.
   */
  get weaknesses() {
    const items = [];

    for (const phase of PHASES) {
      const stat = this.phaseStats[phase];
      if (!stat.moves) continue;
      items.push({
        type: "phase",
        key: phase,
        averageLoss: stat.totalLoss / stat.moves,
        mistakeRate: stat.mistakes / stat.moves,
        sampleSize: stat.moves
      });
    }

    for (const [motif, count] of Object.entries(this.motifCounts)) {
      if (!count) continue;
      items.push({
        type: TACTICAL_MOTIFS.has(motif) ? "tactical" : CALCULATION_MOTIFS.has(motif) ? "calculation" : "motif",
        key: motif,
        count
      });
    }

    return items.sort((a, b) => {
      const scoreA = a.averageLoss ?? a.count ?? 0;
      const scoreB = b.averageLoss ?? b.count ?? 0;
      return scoreB - scoreA;
    });
  }

  toJSON() {
    return {
      gamesAnalyzed: this.gamesAnalyzed,
      totalMoves: this.totalMoves,
      classCounts: this.classCounts,
      motifCounts: this.motifCounts,
      phaseStats: this.phaseStats,
      weaknesses: this.weaknesses,
      conceptMastery: this.conceptMastery,
      criticalMistakes: this.criticalMistakes,
      history: this.history
    };
  }
}

export function createPlayerModel() {
  return new PlayerModel();
}
