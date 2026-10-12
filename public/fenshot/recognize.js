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
import { findChessboardCorners, snapCorners } from "./detect.js";
import { extractTiles, rgbaToGray } from "./tiles.js";
import { probsToPlacement } from "./fen.js";
export const CONFIDENCE_FLOOR = 0.7;
/** Detection works on moderate resolutions; downscale huge retina
 *  screenshots for speed (gradients survive downscaling fine). */
const MAX_DETECT_DIM = 1600;
function imageToGray(img) {
    const w = "naturalWidth" in img ? img.naturalWidth : img.width;
    const h = "naturalHeight" in img ? img.naturalHeight : img.height;
    const scale = Math.min(1, MAX_DETECT_DIM / Math.max(w, h));
    const cw = Math.round(w * scale);
    const ch = Math.round(h * scale);
    const canvas = document.createElement("canvas");
    canvas.width = cw;
    canvas.height = ch;
    const ctx = canvas.getContext("2d", { willReadFrequently: true });
    if (!ctx)
        throw new Error("Canvas 2d context unavailable");
    ctx.drawImage(img, 0, 0, cw, ch);
    const data = ctx.getImageData(0, 0, cw, ch);
    return rgbaToGray(data.data, cw, ch);
}
const EMPTY_PLACEMENT = "8/8/8/8/8/8/8/8";
/** Detection passes per image: the first board found can be an empty
 *  decorative board (a page can contain several board-like regions,
 *  including this library's own UI); masking it and rescanning finds
 *  the board the user actually means. */
const MAX_SCAN_PASSES = 3;
async function scanOnce(gray, classify) {
    const corners = findChessboardCorners(gray);
    if (!corners)
        return null;
    let bestCorners = corners;
    let best = await classify(corners);
    const snapped = snapCorners(gray, corners);
    if (snapped.x0 !== corners.x0 ||
        snapped.y0 !== corners.y0 ||
        snapped.x1 !== corners.x1 ||
        snapped.y1 !== corners.y1) {
        const snappedRead = await classify(snapped);
        if (snappedRead.meanConfidence > best.meanConfidence) {
            best = snappedRead;
            bestCorners = snapped;
        }
    }
    return {
        ...best,
        corners: bestCorners,
        reliable: best.minConfidence >= CONFIDENCE_FLOOR,
    };
}
/** Flatten a region so its gradients vanish and the detector cannot
 *  lock onto it again on the next pass. */
function maskRegion(gray, box) {
    const data = Float32Array.from(gray.data);
    const x0 = Math.max(0, Math.floor(box.x0));
    const y0 = Math.max(0, Math.floor(box.y0));
    const x1 = Math.min(gray.width, Math.ceil(box.x1));
    const y1 = Math.min(gray.height, Math.ceil(box.y1));
    for (let y = y0; y < y1; y++) {
        data.fill(128, y * gray.width + x0, y * gray.width + x1);
    }
    return { data, width: gray.width, height: gray.height };
}
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
export async function recognizeGray(gray, classify) {
    let working = gray;
    let emptyFallback = null;
    for (let pass = 0; pass < MAX_SCAN_PASSES; pass++) {
        const result = await scanOnce(working, classify);
        if (!result)
            break;
        if (result.placement !== EMPTY_PLACEMENT)
            return result;
        emptyFallback = emptyFallback ?? result;
        working = maskRegion(working, result.corners);
    }
    return emptyFallback;
}
export function createRecognizer(options) {
    let ortPromise = null;
    let sessionPromise = null;
    function loadOrt() {
        if (!ortPromise) {
            // The pure-wasm build: the default package entry is the JSEP
            // (webgpu) bundle which requests ort-wasm-*.jsep.mjs at runtime;
            // only the plain wasm pair is required here.
            ortPromise = import("/ort/ort.wasm.mjs").then((ort) => {
                ort.env.wasm.wasmPaths = options.wasmPaths;
                return ort;
            });
        }
        return ortPromise;
    }
    function getSession() {
        if (!sessionPromise) {
            sessionPromise = (async () => {
                const ort = await loadOrt();
                return ort.InferenceSession.create(options.modelUrl, {
                    executionProviders: ["wasm"],
                });
            })();
        }
        return sessionPromise;
    }
    return {
        warmUp() {
            void getSession().catch(() => undefined);
        },
        async recognize(source) {
            const img = source instanceof File || source instanceof Blob ? await createImageBitmap(source) : source;
            const gray = imageToGray(img);
            const [ort, session] = await Promise.all([loadOrt(), getSession()]);
            return recognizeGray(gray, async (c) => {
                const tiles = extractTiles(gray, c);
                const out = await session.run({ tiles: new ort.Tensor("float32", tiles, [64, 1024]) });
                return probsToPlacement(out["probs"].data);
            });
        },
    };
}



