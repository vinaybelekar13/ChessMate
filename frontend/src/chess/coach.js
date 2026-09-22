// ChessMate - coach domain module.
//
// Turns a GameAnalyzer report (./game-analyzer.js), and optionally a
// PlayerModel (./player-model.js) for cross-game context, into
// structured coaching data:
//
//   { summary, strengths, weaknesses, recurringPatterns,
//     criticalMistakes, concepts, recommendations, questions }
//
// Everything produced here is templated off real fields (cls, loss,
// phase, motif, san, fenBefore, moveNo) - there is no free-text
// generation and no invented chess judgement. This is the shape a
// future LLM explanation layer would consume and phrase in prose; it
// is not that layer.

const GOOD_CLASSES = new Set(["brilliant", "great", "best", "excellent"]);
const MISTAKE_CLASSES = new Set(["inaccuracy", "mistake", "blunder"]);

// Short, factual definitions of the real motif kinds explainMove() can
// produce (see ./motifs.js MOTIF_TYPES). These are standard chess-theory
// facts, not per-game commentary.
export const MOTIF_CONCEPTS = Object.freeze({
  "hung-piece": "A piece was left undefended, or moved somewhere it could be captured for free.",
  "losing-exchange": "A trade was initiated that loses material once all recaptures are counted.",
  "fork": "One piece attacked two or more enemy pieces at the same time.",
  "allowed-mate": "A move allowed a forced checkmate that could have been avoided.",
  "missed-mate": "A forced checkmate was available and was not played.",
  "missed-material": "A move that would have won material was available and was not played."
});

function phaseLabel(phase) {
  return phase.charAt(0).toUpperCase() + phase.slice(1);
}

/**
 * Build the summary section: counts and accuracy already computed by
 * buildReviewReport(), reshaped for direct display.
 */
function buildSummary(report) {
  const { summary, accuracy, opening } = report.review;
  return {
    totalMoves: summary.totalMoves,
    averageLoss: Math.round(summary.averageLoss * 10) / 10,
    byClass: summary.byClass,
    accuracy,
    opening
  };
}

/**
 * Phases/classes that stand out as comparatively strong, from real
 * per-phase averages - not praise generation.
 */
function buildStrengths(report) {
  const strengths = [];
  for (const [phase, moves] of Object.entries(report.review.byPhase)) {
    if (!moves.length) continue;
    const goodShare = moves.filter(m => GOOD_CLASSES.has(m.cls)).length / moves.length;
    if (goodShare >= 0.6) {
      strengths.push({
        type: "phase",
        phase,
        detail: `${phaseLabel(phase)} moves were classified best/excellent or better ${Math.round(goodShare * 100)}% of the time.`
      });
    }
  }
  return strengths;
}

function buildWeaknesses(report, playerModel) {
  const weaknesses = [];
  for (const [phase, moves] of Object.entries(report.review.byPhase)) {
    if (!moves.length) continue;
    const mistakeShare = moves.filter(m => MISTAKE_CLASSES.has(m.cls)).length / moves.length;
    if (mistakeShare > 0) {
      weaknesses.push({
        type: "phase",
        phase,
        detail: `${phaseLabel(phase)}: ${moves.filter(m => MISTAKE_CLASSES.has(m.cls)).length} of ${moves.length} moves were inaccuracies, mistakes, or blunders.`
      });
    }
  }
  for (const { motif, count } of report.motifs.top) {
    weaknesses.push({
      type: "motif",
      motif,
      detail: `"${motif}" occurred ${count} time${count === 1 ? "" : "s"} this game.${
        playerModel && playerModel.motifCounts[motif] > count
          ? ` It has now come up ${playerModel.motifCounts[motif]} times across your analyzed games.`
          : ""
      }`
    });
  }
  return weaknesses;
}

/**
 * Cross-game recurrence, only populated when a PlayerModel is supplied.
 * Purely a lookup against counts the model already has.
 */
function buildRecurringPatterns(report, playerModel) {
  if (!playerModel) return [];
  const patterns = [];
  for (const { motif, count } of report.motifs.top) {
    const total = playerModel.motifCounts[motif] || 0;
    if (total > count) {
      patterns.push({
        motif,
        thisGame: count,
        total,
        detail: `You have made this type of mistake (${motif}) in ${total} moves across your analyzed games.`
      });
    }
  }
  return patterns;
}

function buildConcepts(report) {
  const concepts = [];
  for (const motif of Object.keys(report.motifs.counts)) {
    if (MOTIF_CONCEPTS[motif]) {
      concepts.push({ concept: motif, explanation: MOTIF_CONCEPTS[motif] });
    }
  }
  return concepts;
}

/**
 * Templated recommendations tied to the report's own worst weakness -
 * not an open-ended suggestion generator.
 */
function buildRecommendations(report) {
  const recommendations = [];
  const [topMotif] = report.motifs.top;
  if (topMotif) {
    recommendations.push({
      type: "training",
      detail: `Practice positions involving "${topMotif.motif}" (${topMotif.count} occurrence${topMotif.count === 1 ? "" : "s"} this game).`
    });
  }
  const worstPhase = Object.entries(report.review.byPhase)
    .map(([phase, moves]) => ({
      phase,
      mistakes: moves.filter(m => MISTAKE_CLASSES.has(m.cls)).length
    }))
    .sort((a, b) => b.mistakes - a.mistakes)[0];
  if (worstPhase && worstPhase.mistakes > 0) {
    recommendations.push({
      type: "phase-focus",
      detail: `Review your ${worstPhase.phase} decisions - ${worstPhase.mistakes} mistake${worstPhase.mistakes === 1 ? "" : "s"} occurred there.`
    });
  }
  return recommendations;
}

/**
 * One question per critical mistake, referencing the real move and
 * position - a prompt for the player to answer, not an answer itself.
 */
function buildQuestions(report) {
  return report.criticalPositions.map(move => ({
    ply: move.moveNo,
    color: move.color,
    fen: move.fenBefore,
    question: `At move ${move.moveNo} (${move.san}), what was your plan, and what could ${
      move.color === "w" ? "Black" : "White"
    } do in response?`
  }));
}

/**
 * Build the full structured coaching object for one GameAnalyzer report.
 * `playerModel`, when supplied, unlocks cross-game recurrence detection.
 */
export function buildCoachReport(report, playerModel = null) {
  if (!report) return null;

  return {
    summary: buildSummary(report),
    strengths: buildStrengths(report),
    weaknesses: buildWeaknesses(report, playerModel),
    recurringPatterns: buildRecurringPatterns(report, playerModel),
    criticalMistakes: report.criticalPositions,
    concepts: buildConcepts(report),
    recommendations: buildRecommendations(report),
    questions: buildQuestions(report)
  };
}
