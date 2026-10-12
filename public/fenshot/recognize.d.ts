/**
 * Browser-side screenshot recognition. Lazy-loads onnxruntime-web
 * (pure-wasm build) and the tile classifier model on first use.
 *
 * The classifier is trained on a synthetic corpus spanning lichess +
 * chess.com piece sets and board themes, procedural flat boards, and
 * book-diagram hatch boards, with screenshot degradations baked in
 * (dimming, JPEG artifacts, blur, corner jitter).
 *
 * Alignment arbitration: detection corners plus a checkerboard
 * grid-snap candidate are both classified, and the read with higher
 * mean confidence wins. Edge-rich board textures (hatched book
 * diagrams) fool the gradient peak search by a quarter tile; the
 * snap fixes those, but is itself unreliable on dim photo-textured
 * boards, so the classifier arbitrates.
 *
 * recognize: HTMLImageElement/ImageBitmap/File/Blob -> placement FEN
 * + per-tile confidence. reliable=false (minConfidence below
 * CONFIDENCE_FLOOR) means the read is untrustworthy (truly foreign
 * piece set, partial board) and the caller should route the user to
 * an editor with a warning rather than trusting the result.
 */
import { type BoardCorners, type GrayImage } from "./detect";
import { type RecognitionResult } from "./fen";
export declare const CONFIDENCE_FLOOR = 0.7;
export interface BoardScanResult extends RecognitionResult {
    corners: BoardCorners;
    reliable: boolean;
}
export interface RecognizerOptions {
    /** URL of the tile classifier model (`chess-tiles-v2.onnx`, shipped
     *  in this package under `model/`). Serve it as a static asset and
     *  point here, e.g. "/models/chess-tiles-v2.onnx". */
    modelUrl: string;
    /** Location of the onnxruntime-web wasm assets. Either a directory
     *  URL prefix (e.g. "/ort/") or exact per-file URLs, which is what
     *  bundlers like Vite need:
     *  `{ mjs: mjsUrl, wasm: wasmUrl }` from `?url` imports. */
    wasmPaths: string | {
        mjs: string;
        wasm: string;
    };
}
export interface Recognizer {
    /** Scan an image for a chessboard. Resolves null when no board-like
     *  structure is found. */
    recognize(source: HTMLImageElement | ImageBitmap | File | Blob): Promise<BoardScanResult | null>;
    /** Eagerly fetch + compile the wasm runtime and the model so the
     *  first scan is near-instant. Idempotent; failures are swallowed
     *  (a warmup miss just means the first scan pays the cost). */
    warmUp(): void;
}
export type TileClassifier = (corners: BoardCorners) => Promise<RecognitionResult>;
/**
 * Pure recognition core: detect corners, classify, arbitrate against
 * the grid-snap candidate. Platform-independent (no canvas, no ONNX);
 * the classifier is injected. Exercised directly by the golden test
 * suite and usable from Node with any rasterizer.
 *
 * An all-empty read is never the board the user means (an empty board
 * has no position to analyze, and whole-screen captures can include
 * decorative or placeholder boards). When a pass reads empty, the
 * region is masked and the scan repeats, preferring a piece-bearing
 * board found later. The empty read is still returned when nothing
 * better exists.
 */
export declare function recognizeGray(gray: GrayImage, classify: TileClassifier): Promise<BoardScanResult | null>;
export declare function createRecognizer(options: RecognizerOptions): Recognizer;
