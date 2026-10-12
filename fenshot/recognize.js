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

/*
 * A real chess position must contain exactly one white king
 * and exactly one black king.
 *
 * Detector false positives often produce sparse garbage such as
 * a single pawn, random pieces, or UI/card patterns. Do not accept
 * those as a chess position.
 */
function isPlausiblePosition(placement) {
    let whiteKings = 0;
    let blackKings = 0;

    for (const ch of placement) {
        if (ch === "K") {
            whiteKings++;
        } else if (ch === "k") {
            blackKings++;
        }
    }

    return (
        whiteKings === 1 &&
        blackKings === 1
    );
}

/** Detection passes per image. */
const MAX_SCAN_PASSES = 3;

async function scanOnce(gray, classify) {
    let corners = findChessboardCorners(gray);

    if (!corners) {
        return null;
    }

    /*
     * The native ChessMate snip captures the selected chessboard
     * itself. On hatched book diagrams the gradient detector can
     * lock onto an offset grid which extends outside the capture.
     *
     * In that situation the complete captured image is the correct
     * board crop. Do not run snapCorners() afterwards because it can
     * reintroduce the bad offset.
     */
    const aspect =
        Math.max(gray.width, gray.height) /
        Math.min(gray.width, gray.height);

    const outOfBounds =
        corners.x0 < 0 ||
        corners.y0 < 0 ||
        corners.x1 > gray.width ||
        corners.y1 > gray.height;

    const detectedWidth = corners.x1 - corners.x0;
    const detectedHeight = corners.y1 - corners.y0;
    const detectedArea = detectedWidth * detectedHeight;
    const capturedArea = gray.width * gray.height;

    const detectorTooSmall =
        aspect <= 1.15 &&
        detectedWidth > 0 &&
        detectedHeight > 0 &&
        detectedArea < capturedArea * 0.35;

    if (
        (outOfBounds || detectorTooSmall) &&
        aspect <= 1.15
    ) {
        corners = {
            x0: 0,
            y0: 0,
            x1: gray.width,
            y1: gray.height
        };

        console.log(
            detectorTooSmall
                ? "[Fenshot] Detector crop too small -> using full captured board"
                : "[Fenshot] Detector crop out of bounds -> using full captured board"
        );

        let best = null;
        let bestCorners = null;

        for (const candidate of fullCropCandidates(gray)) {
            const read = await classify(candidate);

            console.log(
                "[Fenshot] Square crop candidate:",
                candidate,
                "mean=",
                read.meanConfidence,
                "min=",
                read.minConfidence,
                "plausible=",
                isPlausiblePosition(read.placement)
            );

            if (
                !best ||
                read.meanConfidence >
                best.meanConfidence
            ) {
                best = read;
                bestCorners = candidate;
            }
        }

        if (!best) {
            return null;
        }

        return {
            ...best,
            corners: bestCorners,
            reliable:
                best.minConfidence >=
                CONFIDENCE_FLOOR,
            plausible:
                isPlausiblePosition(
                    best.placement
                )
        };
    }

    let bestCorners = corners;
    let best = await classify(corners);

    const snapped = snapCorners(
        gray,
        corners
    );

    if (
        snapped.x0 !== corners.x0 ||
        snapped.y0 !== corners.y0 ||
        snapped.x1 !== corners.x1 ||
        snapped.y1 !== corners.y1
    ) {
        const snappedRead =
            await classify(snapped);

        if (
            snappedRead.meanConfidence >
            best.meanConfidence
        ) {
            best = snappedRead;
            bestCorners = snapped;
        }
    }

    return {
        ...best,
        corners: bestCorners,
        reliable:
            best.minConfidence >=
            CONFIDENCE_FLOOR,
        plausible:
            isPlausiblePosition(
                best.placement
            )
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
    let fallback = null;

    for (
        let pass = 0;
        pass < MAX_SCAN_PASSES;
        pass++
    ) {
        const result =
            await scanOnce(
                working,
                classify
            );

        if (!result) {
            break;
        }

        console.log(
            "[Fenshot] SCAN PASS:",
            pass + 1,
            "corners:",
            result.corners,
            "placement:",
            result.placement,
            "min:",
            result.minConfidence,
            "mean:",
            result.meanConfidence,
            "plausible:",
            result.plausible
        );

        /*
         * This is the important distinction:
         * a piece-bearing result is NOT automatically valid.
         *
         * Only accept a position immediately when it contains
         * exactly one king of each colour.
         */
        if (result.plausible) {
            return result;
        }

        /*
         * Keep the first useful non-empty result as a fallback,
         * but mask it and search again for the real board.
         */
        const fallbackIsEmpty =
            !fallback ||
            fallback.placement ===
                EMPTY_PLACEMENT;

        if (
            fallbackIsEmpty &&
            (
                !fallback ||
                result.placement !==
                    EMPTY_PLACEMENT
            )
        ) {
            fallback = result;
            console.log(
                "[Fenshot] FALLBACK SET:",
                "pass:",
                pass + 1,
                "corners:",
                fallback.corners,
                "placement:",
                fallback.placement,
                "mean:",
                fallback.meanConfidence
            );
        }

        working =
            maskRegion(
                working,
                result.corners
            );
    }

    console.log(
        "[Fenshot] FINAL FALLBACK:",
        fallback
    );

    return fallback;
}
function fullCropCandidates(gray) {
    const size =
        Math.min(
            gray.width,
            gray.height
        );

    const maxInset =
        Math.min(
            12,
            Math.floor(size / 20)
        );

    const candidates = [];

    for (
        let inset = 0;
        inset <= maxInset;
        inset += 2
    ) {
        const availableW =
            gray.width -
            inset * 2;

        const availableH =
            gray.height -
            inset * 2;

        const s =
            Math.min(
                availableW,
                availableH
            );

        const x0 =
            Math.floor(
                (gray.width - s) / 2
            );

        const y0 =
            Math.floor(
                (gray.height - s) / 2
            );

        candidates.push({
            x0,
            y0,
            x1: x0 + s,
            y1: y0 + s
        });
    }

    return candidates;
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



