/**
 * FEN composition helpers for scan results. A recognizer returns a
 * bare placement; these build a full analyzable FEN from it without
 * pulling in a chess library.
 */
/** Derive castling rights from piece placement (screenshots carry no
 *  history). King + rook on their home squares keep the right;
 *  anything else drops it. */
export declare function inferCastling(placement: string): string;
/** Build a full FEN from a placement and side to move. Castling is
 *  inferred from home squares; en passant, halfmove and fullmove get
 *  neutral defaults (unknowable from a screenshot). */
export declare function placementToFen(placement: string, turn: "w" | "b"): string;
