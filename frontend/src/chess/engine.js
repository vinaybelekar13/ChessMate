// ChessMate - domain engine access point.
//
// This used to contain a byte-for-byte copy of js/engine.js. Two
// implementations of the same Stockfish wrapper is exactly the
// duplication the migration must avoid, so this now re-exports the one
// real implementation via the legacy adapter. If the engine wrapper
// ever needs a domain-specific extension, add it here as a subclass or
// wrapper around Engine rather than forking its source again.
export { Engine } from "./legacy/engine-adapter.js";
