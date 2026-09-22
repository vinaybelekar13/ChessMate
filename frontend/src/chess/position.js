// ChessMate - pure position/evaluation utilities.
// No DOM, UI, engine, or browser-specific code.

export const PIECE_VALUE = {
  p: 1,
  n: 3,
  b: 3,
  r: 5,
  q: 9,
  k: 0
};

export const MATE_CP = 100000;

export const PHASE_ENDGAME_NPM = 20;

/**
 * Convert centipawn evaluation to an approximate win percentage.
 */
export function winPct(cp) {
  return 50 + 50 * (2 / (1 + Math.exp(-0.00368208 * cp)) - 1);
}

/**
 * Calculate material value for one side from a FEN.
 */
export function material(fen, color) {
  const board = fen.split(" ")[0];
  let total = 0;

  for (const char of board) {
    if (char === "/" || /\d/.test(char)) continue;

    const pieceColor = char === char.toUpperCase() ? "w" : "b";

    if (pieceColor === color) {
      total += PIECE_VALUE[char.toLowerCase()] || 0;
    }
  }

  return total;
}

/**
 * Calculate total non-pawn material.
 * Kings and pawns are excluded.
 */
export function nonPawnMaterial(fen) {
  const board = fen.split(" ")[0];
  let total = 0;

  for (const char of board) {
    if (char === "/" || /\d/.test(char)) continue;

    const piece = char.toLowerCase();

    if (piece !== "p" && piece !== "k") {
      total += PIECE_VALUE[piece] || 0;
    }
  }

  return total;
}

/**
 * Determine the game phase from non-pawn material.
 */
export function phaseOf(fenBefore, ply, openingEndPly = 0) {
  if (ply <= openingEndPly) return "opening";

  const npm = nonPawnMaterial(fenBefore);

  if (npm <= PHASE_ENDGAME_NPM) {
    return "endgame";
  }

  return "middlegame";
}

/**
 * Convert engine score information into a White POV centipawn value.
 */
export function evalWhite(node) {
  if (!node) return 0;

  if (node.mate != null) {
    return node.mate > 0
      ? 10000 - node.mate * 10
      : -10000 - node.mate * 10;
  }

  return node.cp == null ? 0 : node.cp;
}

/**
 * Convert engine score information into White POV win percentage.
 */
export function wpWhite(node) {
  if (!node) return 50;

  if (node.mate != null) {
    return node.mate > 0 ? 100 : 0;
  }

  return winPct(node.cp == null ? 0 : node.cp);
}