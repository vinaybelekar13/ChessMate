/**
 * ChessMate Chess Domain
 *
 * Public entry point for the chess-domain layer. Future code (current
 * UI, a future React UI, a backend, the AI coach, training/puzzle
 * generation) should import from here rather than reaching into
 * js/*.js or src/chess/legacy/*.js directly.
 */

export const CHESSMATE_CHESS_VERSION = "0.2.0";

export {
  PIECE_VALUE,
  MATE_CP,
  PHASE_ENDGAME_NPM,
  winPct,
  material,
  nonPawnMaterial,
  phaseOf,
  evalWhite,
  wpWhite
} from "./position.js";

export {
  ChessGame,
  createGame,
  normalizeGameSource
} from "./game.js";

export {
  buildEvaluationTimeline,
  getGamePhase,
  largestEvaluationSwing
} from "./analysis.js";

export {
  Engine
} from "./engine.js";

export {
  CLASS_ORDER,
  reviewGame,
  evaluationChange,
  playerEvaluationLoss,
  summarizeReviews,
  criticalMistakes,
  mistakesByPhase,
  mistakesByType,
  buildReviewReport
} from "./review.js";

export {
  MOTIF_TYPES,
  isKnownMotif,
  normalizeMotif,
  createMotifEvent,
  motifsFromReviewedMoves,
  countMotifs,
  groupMotifs,
  topMotifs,
  buildMotifProfile
} from "./motifs.js";

export {
  GameAnalyzer,
  createGameAnalyzer
} from "./game-analyzer.js";

export {
  PlayerModel,
  createPlayerModel
} from "./player-model.js";

export {
  MOTIF_CONCEPTS,
  buildCoachReport
} from "./coach.js";

export {
  generateTrainingItems,
  generateTrainingQueue,
  prioritizeByWeakness
} from "./training.js";
