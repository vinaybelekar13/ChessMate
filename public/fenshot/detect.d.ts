/**
 * Chessboard detection in a screenshot. Pure TypeScript port of
 * chessboard_finder.py from Elucidation/tensorflow_chessbot (MIT).
 *
 * Input: grayscale image as Float32Array (0-255 values, row-major).
 * Output: board bounding box in image coordinates, or null when no
 * board-like gradient structure is found.
 *
 * Algorithm: image gradients split into +/- components, summed into
 * 1D "hough" responses per row and per column. Board edges produce
 * strong evenly spaced peaks; we find length-7+ arithmetic sequences
 * of peaks (the 7 inner lines of an 8x8 board), then pick the 7x7
 * sub-grid whose crop correlates best with an ideal checkerboard
 * kernel. Faithful to the python reference, validated against its
 * outputs in tests/unit/board-scan.test.ts.
 *
 * Deliberate deviation from the reference: its noise pre-gate
 * (std(hough)/length >= 8000 on both axes) is removed. The metric is
 * scale-dependent, so a page screenshot whose board spans only part
 * of a wide frame fails the gate even when the board peaks are
 * pristine (reddit-page-board.png in the test set). Measured against
 * the fixture corpus the gate rejected nothing the arithmetic
 * sequence search did not already reject.
 */
export interface BoardCorners {
    x0: number;
    y0: number;
    x1: number;
    y1: number;
}
export interface GrayImage {
    data: Float32Array;
    width: number;
    height: number;
}
/**
 * Grid-snap refinement candidate: the peak-sequence search can lock
 * onto an offset grid when the board texture itself is edge-rich
 * (hatched book diagrams put more gradient energy inside squares
 * than on the grid lines). Checkerboard correlation peaks at true
 * alignment on such boards, but is too crude to be trusted blindly
 * on photo-textured boards, so callers treat the snapped box as a
 * CANDIDATE alongside the raw one and let the tile classifier pick
 * the alignment with higher mean confidence (recognize.ts).
 */
export declare function snapCorners(img: GrayImage, box: BoardCorners): BoardCorners;
export declare function findChessboardCorners(img: GrayImage): BoardCorners | null;
