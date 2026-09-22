// Adapter over the existing, working game-review engine (js/review.js).
//
// js/review.js is the real source of truth for:
//   - move classification (brilliant/great/best/excellent/good/book/
//     inaccuracy/mistake/blunder), including sacrifice and only-move
//     detection
//   - accuracy and Elo estimation
//   - opening-book / theory detection
//
// The domain layer must not reimplement any of this. It only reads the
// results reviewGame() already produces and normalizes/aggregates them
// (see ../review.js). This file exists so src/chess/ never imports
// "../../js/..." paths directly and so there is exactly one place that
// says where the real review engine lives.
export {
  reviewGame,
  bookLookup,
  detectOpening,
  CLASSES,
  CLASS_ORDER,
  MATE_CP,
  VAL,
  winPct,
  seeGain,
  accuracy,
  estimateElo,
  nonPawnMaterial,
  PHASE_ENDGAME_NPM,
  phaseOf
} from "../../../js/review.js";
