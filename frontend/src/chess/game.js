// ChessMate - game domain model.
// Keeps game data independent from the UI.

export class ChessGame {
  constructor({
    id = null,
    pgn = "",
    headers = {},
    moves = [],
    source = "manual"
  } = {}) {
    this.id = id;
    this.pgn = pgn;
    this.headers = headers;
    this.moves = moves;
    this.source = source;
  }

  get white() {
    return this.headers.White || "White";
  }

  get black() {
    return this.headers.Black || "Black";
  }

  get result() {
    return this.headers.Result || "*";
  }

  get opening() {
    return this.headers.Opening || null;
  }

  get eco() {
    return this.headers.ECO || null;
  }

  get date() {
    return this.headers.Date || null;
  }

  get moveCount() {
    return this.moves.length;
  }

  toJSON() {
    return {
      id: this.id,
      pgn: this.pgn,
      headers: this.headers,
      moves: this.moves,
      source: this.source
    };
  }
}

/**
 * Create a ChessGame from a plain object.
 */
export function createGame(data = {}) {
  return new ChessGame(data);
}

/**
 * Normalize common game-source names.
 */
export function normalizeGameSource(source) {
  const value = String(source || "manual").toLowerCase();

  if (value.includes("chess.com")) return "chess.com";
  if (value.includes("lichess")) return "lichess";
  if (value.includes("pgn")) return "pgn";
  if (value.includes("master")) return "master";

  return "manual";
}