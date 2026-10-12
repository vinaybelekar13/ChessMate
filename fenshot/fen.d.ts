/**
 * Model output to FEN piece placement. The classifier emits 13-class
 * probabilities per tile in A1..H8 rank order; class labels are
 * '1KQRBNPkqrbnp' (index 0 = empty square).
 */
export interface RecognitionResult {
    /** FEN piece-placement field (ranks 8..1), run-length compressed. */
    placement: string;
    /** Per-tile argmax confidence, A1..H8 rank order. */
    confidences: number[];
    /** The weakest tile confidence. Below ~0.7 treat as unreliable. */
    minConfidence: number;
    /** Average tile confidence; used to arbitrate between candidate
     *  board alignments (recognize.ts). */
    meanConfidence: number;
}
export declare function probsToPlacement(probs: Float32Array): RecognitionResult;
/** Mirror a placement for a board photographed with Black at the
 *  bottom (rotate 180 degrees: reverse ranks and files). */
export declare function flipPlacement(placement: string): string;
/** Decide board orientation from pawn-advance direction, the one
 *  orientation-fixed fact in chess: white pawns march up the ranks
 *  (home 2, promote 8), black pawns march down (home 7, promote 1).
 *  In any natural position white pawns sit, on average, on LOWER
 *  ranks than black pawns. The recognizer always reads tiles as if
 *  white were at the bottom, so a screenshot taken from Black's side
 *  comes back with that relationship inverted (white pawns appear
 *  high, black low). We compare the read against its 180-rotation and
 *  keep whichever has white pawns lower than black. When there are no
 *  pawns of one color, or the signal ties, orientation is genuinely
 *  undecidable from pixels, so we keep the white-at-bottom read and
 *  leave the call to the user's flip toggle. */
export declare function resolveOrientation(placement: string): {
    placement: string;
    orientation: "white" | "black";
};
