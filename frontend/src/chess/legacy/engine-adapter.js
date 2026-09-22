// Adapter over the existing, working Stockfish wrapper (js/engine.js).
//
// The domain layer must not maintain a second engine implementation.
// js/engine.js is the single source of truth for talking to Stockfish;
// this file just gives the src/chess/ layer a stable import path to it
// so future code (AI coach, training, book positions, ...) can depend
// on "the domain engine" without knowing it currently lives under js/.
export { Engine } from "../../../js/engine.js";
