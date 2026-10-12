import {
    createRecognizer,
    resolveOrientation,
    placementToFen
} from "/fenshot/index.js";

const recognizer = createRecognizer({
    modelUrl: "/models/chess-tiles-v2.onnx",
    wasmPaths: "/ort/"
});

export async function scanBoardFenshot(source) {
    console.log("[Fenshot] Starting recognition...");

    const result = await recognizer.recognize(source);

    console.log("[Fenshot] Raw result:", result);

    if (result && result.corners) {
        console.log(
            "[Fenshot] SELECTED CORNERS:",
            JSON.stringify(result.corners)
        );
    }


    if (!result) {
        return {
            reliable: false,
            reason: "No chessboard detected"
        };
    }

    const resolved = resolveOrientation(result.placement);

    const fen = placementToFen(
        resolved.placement,
        "w"
    );

    return {
        fen,
        placement: resolved.placement,
        orientation: resolved.orientation,
        meanConfidence: result.meanConfidence,
        minConfidence: result.minConfidence,
        reliable: result.reliable,
        corners: result.corners
    };
}

export function warmUpFenshot() {
    return recognizer.warmUp();
}

