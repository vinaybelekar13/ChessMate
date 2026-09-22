// Ad-hoc smoke test for the domain-layer migration. Not part of the
// Playwright suite (no browser/Stockfish available here) - exercises
// the real js/review.js + js/motifs.js pipeline through the new
// src/chess/ domain API with a small scripted game and a fake engine,
// so the wiring itself (not the chess logic, which is untouched) gets
// verified.
import { Chess } from "../../vendor/chess.js";
import {
  GameAnalyzer,
  ChessGame,
  createPlayerModel,
  buildCoachReport,
  generateTrainingItems,
  generateTrainingQueue,
  prioritizeByWeakness
} from "./index.js";

// A short, real game with a deliberate late blunder (hangs the queen)
// so classification, motif detection ("hung-piece"), and critical-move
// extraction all have something to find.
const SAN_MOVES = ["e4", "e5", "Bc4", "Bc5", "Qh5", "Nf6", "Qxf7#"];

function buildMoves(sanList, startFen) {
  const chess = new Chess();
  const moves = [];
  for (let i = 0; i < sanList.length; i++) {
    const fenBefore = chess.fen();
    const mv = chess.move(sanList[i]);
    moves.push({
      san: mv.san,
      from: mv.from,
      to: mv.to,
      uci: mv.from + mv.to + (mv.promotion || ""),
      color: mv.color,
      fenBefore,
      fenAfter: chess.fen(),
      moveNo: Math.floor(i / 2) + 1
    });
  }
  return moves;
}

// A fake "engine" good enough to drive reviewGame(): every position is
// dead equal, EXCEPT that it can spot a mate-in-1 when one exists (a
// depth-1 search would find this too). That's enough for the scripted
// Nf6?? blunder (which allows Qxf7#) to classify as a real mistake with
// an "allowed-mate" motif, without needing real Stockfish search. Mate
// values follow the real engine's convention: White's POV, from
// js/engine.js's parseInfo().
function makeFakeEngine() {
  return {
    async newGame() {},
    async analyse(fen) {
      const chess = new Chess(fen);
      const stm = fen.split(" ")[1];
      if (chess.isCheckmate()) {
        const mateCp = stm === "b" ? 100000 : -100000;
        return { stm, bestmove: null, best: { cp: mateCp, mate: null, pv: [] }, lines: [] };
      }
      for (const mv of chess.moves({ verbose: true })) {
        const probe = new Chess(fen);
        probe.move(mv.san);
        if (probe.isCheckmate()) {
          const mateVal = stm === "w" ? 1 : -1;
          const uci = mv.from + mv.to + (mv.promotion || "");
          return { stm, bestmove: uci, best: { cp: null, mate: mateVal, pv: [uci] }, lines: [] };
        }
      }
      return { stm, bestmove: "e2e4", best: { cp: 0, mate: null, pv: ["e2e4"] }, lines: [] };
    }
  };
}

async function main() {
  const moves = buildMoves(SAN_MOVES);
  const engine = makeFakeEngine();
  const analyzer = new GameAnalyzer({ engine });
  const game = new ChessGame({ headers: { White: "A", Black: "B" }, moves, source: "manual" });

  const report = await analyzer.analyzeGame({
    game,
    moves,
    startFen: new Chess().fen(),
    depth: 1,
    bookPlies: 0
  });

  const assert = (cond, msg) => {
    if (!cond) throw new Error("SMOKE TEST FAILED: " + msg);
  };

  assert(report != null, "report should not be null");
  assert(report.metadata.analyzedMoves === moves.length, "analyzedMoves should equal move count");
  assert(Array.isArray(report.review.criticalMistakes), "criticalMistakes should be an array");
  assert(report.review.summary.totalMoves === moves.length, "summary.totalMoves should equal move count");
  assert(typeof report.motifs.totalEvents === "number", "motifs.totalEvents should be a number");
  assert(report.evaluationTimeline.length === moves.length, "evaluationTimeline length should equal move count");

  console.log("SMOKE_TEST_PASSED");
  console.log("classification counts:", JSON.stringify(report.review.summary.byClass));
  console.log("critical mistakes found:", report.review.criticalMistakes.length);
  console.log("motif events found:", report.motifs.totalEvents, JSON.stringify(report.motifs.counts));

  // --- PlayerModel / Coach / Training wiring ---
  const playerModel = createPlayerModel();
  playerModel.ingestReport(report, { gameId: "smoke-test-game" });
  assert(playerModel.gamesAnalyzed === 1, "playerModel should record one game");
  assert(Array.isArray(playerModel.weaknesses), "playerModel.weaknesses should be an array");
  assert(playerModel.toJSON().gamesAnalyzed === 1, "playerModel.toJSON() should round-trip gamesAnalyzed");

  const coach = buildCoachReport(report, playerModel);
  assert(coach != null, "coach report should not be null");
  for (const key of ["summary", "strengths", "weaknesses", "recurringPatterns", "criticalMistakes", "concepts", "recommendations", "questions"]) {
    assert(Object.prototype.hasOwnProperty.call(coach, key), `coach report missing "${key}"`);
  }

  const items = generateTrainingItems(report);
  assert(Array.isArray(items), "generateTrainingItems should return an array");
  for (const item of items) {
    assert(typeof item.fen === "string" && item.fen.length > 0, "every training item needs a real FEN");
  }

  const queue = generateTrainingQueue([report]);
  assert(Array.isArray(queue), "generateTrainingQueue should return an array");

  const prioritized = prioritizeByWeakness(items, playerModel.weaknesses);
  assert(prioritized.length === items.length, "prioritizeByWeakness should not drop items");

  console.log("player model games analyzed:", playerModel.gamesAnalyzed);
  console.log("coach recommendations:", coach.recommendations.length, "questions:", coach.questions.length);
  console.log("training items generated:", items.length);
  console.log("PLAYER_MODEL_COACH_TRAINING_SMOKE_TEST_PASSED");
}

main().catch(e => {
  console.error(e.message);
  process.exit(1);
});
