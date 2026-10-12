import {
    createRecognizer,
    resolveOrientation,
    placementToFen
} from "/fenshot/index.js";

const FENSHOT_MODEL = "/models/chess-tiles-v2.onnx";
const FENSHOT_WASM = "/ort/";

let recognizerPromise = null;

/*
 * Create the Fenshot recognizer only once.
 *
 * The model and ONNX runtime are lazy-loaded by Fenshot on the
 * first recognition attempt.
 */
function getRecognizer() {
    if (!recognizerPromise) {
        console.log("[ChessMate] Initializing Fenshot recognizer...");

        recognizerPromise = Promise.resolve(
            createRecognizer({
                modelUrl: FENSHOT_MODEL,
                wasmPaths: FENSHOT_WASM
            })
        );

        recognizerPromise.then(() => {
            console.log("[ChessMate] Fenshot recognizer ready.");
        }).catch((error) => {
            console.error("[ChessMate] Fenshot initialization failed:", error);
            recognizerPromise = null;
        });
    }

    return recognizerPromise;
}


/*
 * Convert a FEN placement field into the grid format that the
 * old board scanner exposed.
 *
 * This keeps compatibility with any other ChessMate code that
 * expects result.grid.
 */
function placementToGrid(placement) {
    const grid = [];

    if (typeof placement !== "string") {
        return grid;
    }

    const ranks = placement.split("/");

    for (const rank of ranks) {
        const row = [];

        for (const char of rank) {
            if (/^[1-8]$/.test(char)) {
                const empty = Number(char);

                for (let i = 0; i < empty; i++) {
                    row.push(null);
                }
            } else {
                row.push(char);
            }
        }

        while (row.length < 8) {
            row.push(null);
        }

        grid.push(row.slice(0, 8));
    }

    while (grid.length < 8) {
        grid.push(new Array(8).fill(null));
    }

    return grid.slice(0, 8);
}


/*
 * Convert the editor's 8x8 grid back into a complete FEN.
 *
 * Row 0 is rank 8 and row 7 is rank 1.
 */
export function gridToFen(grid, sideToMove = "w") {
    const rows = [];

    for (let r = 0; r < 8; r++) {
        const row = Array.isArray(grid?.[r])
            ? grid[r]
            : [];

        let empty = 0;
        let fenRank = "";

        for (let c = 0; c < 8; c++) {
            const piece = row[c];

            if (
                typeof piece === "string" &&
                /^[prnbqkPRNBQK]$/.test(piece)
            ) {
                if (empty > 0) {
                    fenRank += String(empty);
                    empty = 0;
                }

                fenRank += piece;
            } else {
                empty++;
            }
        }

        if (empty > 0) {
            fenRank += String(empty);
        }

        rows.push(fenRank || "8");
    }

    const stm = sideToMove === "b" ? "b" : "w";

    return `${rows.join("/")} ${stm} KQkq - 0 1`;
}


/*
 * Count pieces from a FEN placement.
 */
function countPieces(placement) {
    if (typeof placement !== "string") {
        return 0;
    }

    let count = 0;

    for (const char of placement) {
        if (/^[prnbqkPRNBQK]$/.test(char)) {
            count++;
        }
    }

    return count;
}


/*
 * Main compatibility function.
 *
 * book-reader.js already calls:
 *
 *     const result = await scanBoard(bitmap);
 *
 * We keep that API unchanged and replace the old pixel-template
 * recognizer internally with Fenshot.
 */
export async function scanBoard(source) {
    console.log("[ChessMate] Fenshot scan started.");

    if (!source) {
        throw new Error("No image source supplied to Fenshot.");
    }

    const recognizer = await getRecognizer();

    console.log("[ChessMate] Sending captured board to Fenshot...");

    const result = await recognizer.recognize(source);

    if (!result) {
        console.warn("[ChessMate] Fenshot could not find a chessboard.");

        return {
            grid: [],
            fen: null,
            occupied: 0,
            confidence: 0,
            minConfidence: 0,
            plausible: false,
            reliable: false
        };
    }

    console.log("[ChessMate] Fenshot raw result:", result);

    /*
     * Fenshot initially reads the board white-at-bottom.
     * resolveOrientation() determines whether the image is actually
     * from Black's point of view.
     */
    const orientationResult = resolveOrientation(result.placement);

    const placement = orientationResult.placement;

    /*
     * ChessMate currently wants a complete FEN, not just the
     * board-placement field.
     */
    const fen = placementToFen(placement, "w");

    const occupied = countPieces(placement);
    const grid = placementToGrid(placement);

    const confidence =
        typeof result.meanConfidence === "number"
            ? result.meanConfidence
            : 0;

    const minConfidence =
        typeof result.minConfidence === "number"
            ? result.minConfidence
            : 0;

    const reliable = result.reliable === true;

    console.log("[ChessMate] Fenshot corners:", result.corners);
    console.log("[ChessMate] Fenshot placement:", placement);
    console.log("[ChessMate] Fenshot orientation:", orientationResult.orientation);
    console.log("[ChessMate] Fenshot FEN:", fen);
    console.log("[ChessMate] Fenshot mean confidence:", confidence);
    console.log("[ChessMate] Fenshot minimum confidence:", minConfidence);
    console.log("[ChessMate] Fenshot minimum confidence:", minConfidence);
    console.log("[ChessMate] Fenshot reliable:", reliable);
    console.log("[ChessMate] Pieces detected:", occupied);

    return {
        grid,
        fen,
        occupied,
        confidence,
        minConfidence,
        plausible: reliable,
        reliable,
        placement,
        orientation: orientationResult.orientation,
        corners: result.corners
    };
}

