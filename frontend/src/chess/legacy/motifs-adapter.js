// Adapter over the existing, working tactical-motif detector (js/motifs.js).
//
// explainMove() decides motifs statically from the position (SEE, board
// geometry, mate search) rather than from the engine's chosen reply — see
// the comments in js/motifs.js for why. The domain layer must not create
// a second, simplified motif detector; it only normalizes whatever
// explainMove() already found (see ../motifs.js).
export {
  explainMove,
  rollup,
  detectFork
} from "../../../js/motifs.js";
