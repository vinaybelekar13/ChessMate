import { Chess } from "../vendor/chess.js?v=35";

import { winPct, MATE_CP } from "./review.js?v=35";
import { Engine } from "./engine.js?v=35";
import { renderBoard } from "./board.js?v=36";
import { scanBoardFenshot } from "./boardscan-fenshot.js";
import * as pdfjsLib from "../node_modules/pdfjs-dist/build/pdf.mjs";


/* ============================================================
   CONFIG
   ============================================================ */

const API_BASE =
    "http://127.0.0.1:5000/api/bookreader";

let BOOK_ID =
    "Improve Your Chess Calculation";

const START_FEN =
    "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1";


/* ============================================================
   ELEMENTS
   ============================================================ */

const pdfViewer = null;

const board =
    document.getElementById("readerBoard");

/*
 * Match the working home board's pointer behaviour.
 */
if (board) {
    board.style.touchAction = "none";
    board.style.userSelect = "none";
    board.style.webkitUserSelect = "none";
}

if (board) {
    board.addEventListener("contextmenu", (event) => {
        event.preventDefault();

        // A drag fires contextmenu after pointerup in some browsers.
        // Consume that event so it doesn't erase the arrow just drawn.
        if (state.suppressNextArrowContextMenu) {
            state.suppressNextArrowContextMenu = false;
            return;
        }

        // Right-click is reserved for drawing arrows.
        // Do not clear arrows from the context-menu event.

    });
}


const pageCurrent =
    document.querySelector(".page-current");

const pageTotal =
    document.querySelector(".page-total");

const pageSlider =
    document.getElementById("pageSlider");

const fenDisplay =
    document.getElementById("fenDisplay");

const moveNotation =
    document.getElementById("moveNotation");

const moveNotationCount =
    document.getElementById("moveNotationCount");

const readerTopCaptured =
    document.getElementById("readerTopCaptured");

const readerBottomCaptured =
    document.getElementById("readerBottomCaptured");


/* ============================================================
   STATE
   ============================================================ */

const state = {

    page: 1,

    totalPages: 585,

    fen: START_FEN,

    flip: false,

    lastMove: null,

    selectedSquare: null,

    moveHistory: [
        START_FEN
    ],

    moveIndex: 0,
    sideToMove: "w",
    magnusEnabled: false,
    magnusArrows: [],
    userArrows: [],
    userArrowStart: null,
    userArrowPointerId: null,

    positions: [],

    positionIndex: 0
};


/* ============================================================
   PDF
   ============================================================ */

async function updatePdfViewer() {

    if (!window.pdfjsLibReady) {
        return;
    }

    if (!pdfDocument) {
        return;
    }

    const pageNumber =
        Math.max(
            1,
            Math.min(
                state.page,
                pdfDocument.numPages
            )
        );

    try {

        const page =
            await pdfDocument.getPage(pageNumber);

        const viewport =
            page.getViewport({
                scale: pdfZoom
            });

        const canvas =
            document.getElementById("pdfCanvas");

        if (!canvas) {
            return;
        }

        const context =
            canvas.getContext("2d");

        const container =
            document.getElementById(
                "pdfPageArea"
            );

        if (!container) {
            return;
        }

        const availableWidth =
            Math.max(
                100,
                container.clientWidth - 32
            );

        const baseViewport =
            page.getViewport({
                scale: 1
            });

        const fitScale =
            availableWidth /
            baseViewport.width;

        const finalScale =
            pdfFitMode
                ? fitScale
                : pdfZoom;

        const finalViewport =
            page.getViewport({
                scale: finalScale
            });

        const devicePixelRatio =
            window.devicePixelRatio || 1;

        canvas.width =
            Math.floor(
                finalViewport.width *
                devicePixelRatio
            );

        canvas.height =
            Math.floor(
                finalViewport.height *
                devicePixelRatio
            );

        canvas.style.width =
            `${finalViewport.width}px`;

        canvas.style.height =
            `${finalViewport.height}px`;

        context.setTransform(
            devicePixelRatio,
            0,
            0,
            devicePixelRatio,
            0,
            0
        );

        await page.render({
            canvasContext: context,
            viewport: finalViewport
        }).promise;

        const currentPage =
            document.getElementById(
                "pdfCurrentPage"
            );

        const totalPages =
            document.getElementById(
                "pdfTotalPages"
            );

        const zoomValue =
            document.getElementById(
                "pdfZoomValue"
            );

        if (currentPage) {
            currentPage.textContent =
                String(pageNumber);
        }

        if (totalPages) {
            totalPages.textContent =
                String(pdfDocument.numPages);
        }

        if (zoomValue) {

            const percentage =
                Math.round(
                    finalScale * 100
                );

            zoomValue.textContent =
                `${percentage}%`;
        }

    } catch (error) {

        console.error(
            "ChessMate PDF.js render error:",
            error
        );

    }
}

/* ============================================================
   FEN VALIDATION
   ============================================================ */

function validFen(fen) {

    try {

        new Chess(fen);

        return true;

    } catch {

        return false;
    }
}


/* ============================================================
   LEGAL TARGETS
   ============================================================ */

function legalTargets(
    fen,
    square
) {

    try {

        const chess =
            new Chess(fen);

        return chess
            .moves({
                square,
                verbose: true
            })
            .map(
                move => move.to
            );

    } catch {

        return [];
    }
}



/* ============================================================
   CHESSMATE READER MATERIAL / PIECE PROFIT
   Same material concept as the ChessMate home board.
   ============================================================ */

const READER_INIT_MATERIAL = {
    p: 8,
    n: 2,
    b: 2,
    r: 2,
    q: 1
};

const READER_PIECE_VALUE = {
    p: 1,
    n: 3,
    b: 3,
    r: 5,
    q: 9
};

function readerCountPieces(fen) {

    const white = {
        p: 0,
        n: 0,
        b: 0,
        r: 0,
        q: 0
    };

    const black = {
        p: 0,
        n: 0,
        b: 0,
        r: 0,
        q: 0
    };

    const placement =
        fen.split(" ")[0];

    for (const ch of placement) {

        const type =
            ch.toLowerCase();

        if (
            READER_INIT_MATERIAL[type] ===
            undefined
        ) {
            continue;
        }

        if (ch === ch.toUpperCase()) {
            white[type]++;
        } else {
            black[type]++;
        }
    }

    return {
        white,
        black
    };
}


function readerCapturedList(counts) {

    const list = [];

    for (const type of [
        "q",
        "r",
        "b",
        "n",
        "p"
    ]) {

        const missing =
            Math.max(
                0,
                READER_INIT_MATERIAL[type] -
                counts[type]
            );

        for (
            let i = 0;
            i < missing;
            i++
        ) {
            list.push(type);
        }
    }

    return list;
}


function readerMaterialScore(counts) {

    let score = 0;

    for (const type of [
        "p",
        "n",
        "b",
        "r",
        "q"
    ]) {

        score +=
            counts[type] *
            READER_PIECE_VALUE[type];
    }

    return score;
}


function renderReaderMaterialBar(
    element,
    side,
    capturedPieces,
    advantage
) {

    if (!element) {
        return;
    }

    const sideName =
        side === "w"
            ? "WHITE"
            : "BLACK";

    const pieceImages =
        capturedPieces
            .map(type => {

                const file =
                    type.toUpperCase();

                const color =
                    side === "w"
                        ? "b"
                        : "w";

                return `
                    <span
                        class="captured-piece"
                        title="${type.toUpperCase()}"
                    >
                        <img
                            src="vendor/pieces/cburnett/${color}${file}.svg"
                            alt=""
                            draggable="false"
                        >
                    </span>
                `;
            })
            .join("");


    const advantageText =
        advantage > 0
            ? `<span class="material-advantage">+${advantage}</span>`
            : "";


    element.innerHTML = `

        <span class="reader-material-side">
            ${sideName}
        </span>

        <span class="chessmate-captured-pieces">
            ${pieceImages}
        </span>

        ${advantageText}
    `;
}


function updateReaderMaterial() {

    if (
        !readerTopCaptured ||
        !readerBottomCaptured
    ) {
        return;
    }

    const {
        white,
        black
    } = readerCountPieces(
        state.fen
    );


    /*
     * Missing white pieces =
     * pieces captured by Black.
     */
    const capturedByBlack =
        readerCapturedList(
            white
        );


    /*
     * Missing black pieces =
     * pieces captured by White.
     */
    const capturedByWhite =
        readerCapturedList(
            black
        );


    const whiteScore =
        readerMaterialScore(
            white
        );

    const blackScore =
        readerMaterialScore(
            black
        );


    /*
     * Positive advantage belongs
     * to the side with more material.
     */
    const whiteAdvantage =
        Math.max(
            0,
            whiteScore - blackScore
        );

    const blackAdvantage =
        Math.max(
            0,
            blackScore - whiteScore
        );


    /*
     * The bars follow board orientation.
     *
     * Normal:
     * TOP    = Black
     * BOTTOM = White
     *
     * Flipped:
     * TOP    = White
     * BOTTOM = Black
     */
    if (!state.flip) {

        renderReaderMaterialBar(
            readerTopCaptured,
            "b",
            capturedByBlack,
            blackAdvantage
        );

        renderReaderMaterialBar(
            readerBottomCaptured,
            "w",
            capturedByWhite,
            whiteAdvantage
        );

    } else {

        renderReaderMaterialBar(
            readerTopCaptured,
            "w",
            capturedByWhite,
            whiteAdvantage
        );

        renderReaderMaterialBar(
            readerBottomCaptured,
            "b",
            capturedByBlack,
            blackAdvantage
        );
    }
}

/* ============================================================
   BARABOSIK BOARD
   DO NOT REBUILD IT HERE.
   We directly call Barabosik's renderer.
   ============================================================ */

/* ============================================================
   GAME END OVERLAY
   ============================================================ */

function updateGameEndOverlay() {

    const overlay =
        document.getElementById("readerGameOverlay");

    const title =
        document.getElementById("readerGameOverlayTitle");

    const subtitle =
        document.getElementById("readerGameOverlaySubtitle");

    if (!overlay || !title || !subtitle) {
        return;
    }

    let chess;

    try {
        chess = new Chess(state.fen);
    } catch (error) {
        overlay.classList.remove("is-visible");
        overlay.setAttribute("aria-hidden", "true");
        return;
    }

    let gameType = null;
    let gameSubtitle = "";

    /*
     * CHECKMATE
     *
     * chess.turn() is the side that is checkmated.
     * Therefore the opposite side wins.
     */
    if (
        typeof chess.isCheckmate === "function" &&
        chess.isCheckmate()
    ) {

        gameType = "CHECKMATE";

        const winner =
            chess.turn() === "w"
                ? "Black wins"
                : "White wins";

        gameSubtitle = winner;

    } else if (
        typeof chess.isStalemate === "function" &&
        chess.isStalemate()
    ) {

        gameType = "STALEMATE";
        gameSubtitle = "No legal moves";

    } else if (
        typeof chess.isDraw === "function" &&
        chess.isDraw()
    ) {

        gameType = "DRAW";
        gameSubtitle = "Game drawn";
    }

    /*
     * Normal position:
     * completely hide the overlay.
     */
    if (!gameType) {

        overlay.classList.remove("is-visible");
        overlay.setAttribute("aria-hidden", "true");

        return;
    }

    title.textContent = gameType;
    subtitle.textContent = gameSubtitle;

    overlay.classList.add("is-visible");
    overlay.setAttribute("aria-hidden", "false");
}


function renderChessBoard() {

    if (!board) {
        return;
    }

    const targets =
        state.selectedSquare
            ? legalTargets(
                state.fen,
                state.selectedSquare
            )
            : [];

    renderBoard(
        board,
        state.fen,
        {

            flip:
                state.flip,

            lastMove:
                state.lastMove,

            selected:
                state.selectedSquare,

            targets,

            arrows: [...(state.magnusEnabled ? state.magnusArrows : []), ...state.userArrows],

            marks: [],

            onSquareClick:
                handleSquareClick,

            onSquareDown:
                handleSquareDown
        }
    );

    updateGameEndOverlay();
}


/* ============================================================
   BARABOSIK BOARD CLICK / DRAG INTERACTION
   ============================================================

   IMPORTANT:
   The drag/drop lifecycle below intentionally follows the
   working ChessMate HOME BOARD architecture:

       pointerdown
           â†“
       pointer state
           â†“
       movement threshold
           â†“
       floating piece
           â†“
       window pointermove
           â†“
       window pointerup
           â†“
       animate the SAME floating piece
           â†“
       commit chess move
           â†“
       rebuild board

   Only the DOM selectors/state are adapted for Barabosik's
   Book Reader board:
       .sq[data-sq="e4"]
       .pc
       state.fen
       renderChessBoard()
   ============================================================ */

let suppressNextChessClick = false;

/* ============================================================
/* ============================================================
   CHESS POSITION SNIPPER
   Native Windows Snipping Tool + Clipboard Bridge
   ============================================================ */

let chessPositionScanArmed = false;
let chessPositionSnipperTimer = null;
let chessPositionSnipperVersion = null;

const NATIVE_SCANNER_URL = "http://127.0.0.1:8765";

let nativeScanProcessing = false;

async function getNativeSnipVersion() {
    const response = await fetch(
        `${NATIVE_SCANNER_URL}/version?ts=${Date.now()}`,
        { cache: "no-store" }
    );

    if (!response.ok) {
        throw new Error(`Native scanner version HTTP ${response.status}`);
    }

    return Number(await response.text());
}

async function getNativeSnipImage() {
    const response = await fetch(
        `${NATIVE_SCANNER_URL}/image?ts=${Date.now()}`,
        { cache: "no-store" }
    );

    if (!response.ok) {
        throw new Error(`Native scanner image HTTP ${response.status}`);
    }

    return await response.blob();
}

function setFenSideToMove(fen, side) {
    if (!fen || typeof fen !== "string") {
        return fen;
    }

    const parts = fen.trim().split(/\s+/);

    if (parts.length < 2) {
        return fen;
    }

    parts[1] = side === "b" ? "b" : "w";

    return parts.join(" ");
}


function updateSideToMoveToggle() {
    const toggle =
        document.getElementById("sideToMoveToggle");

    const label =
        document.getElementById("sideToMoveLabel");

    if (!toggle || !label) {
        return;
    }

    const blackToMove =
        state.sideToMove === "b";

    toggle.checked = blackToMove;

    label.textContent =
        blackToMove
            ? "Black"
            : "White";
}


function setSideToMove(side) {
    state.sideToMove =
        side === "b" ? "b" : "w";

    state.fen =
        setFenSideToMove(
            state.fen,
            state.sideToMove
        );

    if (
        state.moveHistory &&
        state.moveHistory.length &&
        state.moveIndex >= 0
    ) {
        state.moveHistory[
            state.moveIndex
        ] = state.fen;
    }

    updateSideToMoveToggle();

    renderChessBoard();
}


function bindSideToMoveToggle() {
    const toggle =
        document.getElementById("sideToMoveToggle");

    if (!toggle) {
        console.warn(
            "[ChessMate] Side-to-move toggle not found."
        );
        return;
    }

    toggle.addEventListener(
        "change",
        () => {
            setSideToMove(
                toggle.checked
                    ? "b"
                    : "w"
            );
        }
    );

    updateSideToMoveToggle();
}


function applyScannedFen(fen) {
    if (!fen || typeof fen !== "string") {
        throw new Error("Scanner returned an invalid FEN.");
    }

    console.log("[ChessMate] Applying scanned FEN:", fen);

    fen = setFenSideToMove(
        fen,
        state.sideToMove
    );

    state.fen = fen;
    state.moveHistory = [fen];
    state.moveIndex = 0;
    state.lastMove = null;

    renderChessBoard();
    updateFenUI();
    renderMoveNotation();
    updateMoveButtons();
}

async function processNativeChessSnip() {
    if (nativeScanProcessing) return;

    nativeScanProcessing = true;

    try {
        console.log("[ChessMate] Reading captured board...");

        const blob = await getNativeSnipImage();

        console.log(
            "[ChessMate] Captured board:",
            blob.type,
            blob.size,
            "bytes"
        );

        const bitmap = await createImageBitmap(blob);

        try {
            console.log(
                "[ChessMate] Running board recognizer:",
                bitmap.width,
                "x",
                bitmap.height
            );

            const result = await scanBoardFenshot(blob);

            console.log("[ChessMate] Scanner result:", result);

            if (!result || !result.fen) {
                throw new Error("Chess board could not be recognized.");
            }

            console.log("[ChessMate] Recognized FEN:", result.fen);

            if (result.confidence !== undefined) {
                console.log(
                    "[ChessMate] Recognition confidence:",
                    result.confidence
                );
            }

            if (result.minConfidence !== undefined) {
                console.log(
                    "[ChessMate] Minimum confidence:",
                    result.minConfidence
                );
            }

            console.log(
                "[ChessMate] Recognition reliable:",
                result.reliable
            );

            if (result.reliable === false) {
                console.warn(
                    "[ChessMate] Recognition rejected because confidence is too low.",
                    result
                );

                alert(
                    "Chess position detected, but recognition confidence is too low.\\n\\n" +
                    "Min confidence: " + Number(result.minConfidence ?? 0).toFixed(3) + "\\n" +
                    "Mean confidence: " + Number(result.meanConfidence ?? 0).toFixed(3) + "\\n\\n" +
                    "Predicted FEN:\\n" + (result.fen || "n/a") + "\\n\\n" +
                    "Please select the complete chessboard more tightly and try again."
                );

                return;
            }

            applyScannedFen(result.fen);

            if (result.plausible === false) {
                console.warn(
                    "[ChessMate] Position was recognized, but plausibility is low."
                );
            }
        } finally {
            if (typeof bitmap.close === "function") {
                bitmap.close();
            }
        }
    } catch (error) {
        console.error("[ChessMate] Position scan failed:", error);

        alert(
            "Could not recognize the chess position.\n\n" +
            "Make sure you selected the complete chessboard and try again."
        );
    } finally {
        nativeScanProcessing = false;
    }
}

async function startNativeChessSnipper() {
    try {
        const version = await getNativeSnipVersion();

        console.log(
            "[ChessMate] Direct native scanner connected. Version:",
            version
        );

        return true;
    } catch (error) {
        console.warn(
            "[ChessMate] Native scanner is not running:",
            error
        );

        return false;
    }
}

async function armChessPositionSnipper() {
    if (nativeScanProcessing) {
        console.log("[ChessMate] Scanner is already processing.");
        return;
    }

    try {
        const previousVersion = await getNativeSnipVersion();

        console.log(
            "[ChessMate] Starting direct screen scan. Previous version:",
            previousVersion
        );

        const response = await fetch(
            `${NATIVE_SCANNER_URL}/scan?ts=${Date.now()}`,
            {
                method: "GET",
                cache: "no-store"
            }
        );

        if (!response.ok) {
            throw new Error(
                `Could not start native scanner: HTTP ${response.status}`
            );
        }

        console.log(
            "[ChessMate] Select the complete chessboard with the mouse."
        );

        const startedAt = Date.now();

        const poll = async () => {
            try {
                const currentVersion = await getNativeSnipVersion();

                if (currentVersion > previousVersion) {
                    console.log(
                        "[ChessMate] New board capture detected:",
                        currentVersion
                    );

                    await processNativeChessSnip();
                    return;
                }

                if (Date.now() - startedAt > 60000) {
                    console.warn("[ChessMate] Scanner timed out.");
                    return;
                }

                setTimeout(poll, 250);
            } catch (error) {
                console.error(
                    "[ChessMate] Scanner polling failed:",
                    error
                );
            }
        };

        setTimeout(poll, 250);
    } catch (error) {
        console.error(
            "[ChessMate] Could not start position scanner:",
            error
        );

        alert(
            "ChessMate cannot connect to the native screen scanner.\n\n" +
            "Make sure ChessMateSnipper.exe is running."
        );
    }
}

startNativeChessSnipper();

function bindPositionScannerButton() {
    const button = document.getElementById("scanPositionButton");

    if (!button) {
        console.warn("[ChessMate] scanPositionButton not found.");
        return;
    }

    button.addEventListener("click", async () => {
        console.log("[ChessMate] Scan Position button clicked.");
        await armChessPositionSnipper();
    });

    console.log("[ChessMate] Scan Position button connected.");
}

if (document.readyState === "loading") {
    document.addEventListener(
        "DOMContentLoaded",
        () => {
            bindPositionScannerButton();
            bindSideToMoveToggle();
        },
        { once: true }
    );
} else {
    bindPositionScannerButton();
    bindSideToMoveToggle();
}
const MOVE_ANIMATION_MS = 200;

const DRAG_THRESHOLD_PX = 5;

let bookReaderPointerState = null;
let bookReaderAnimationRunning = false;


/* ============================================================
   BOARD HELPERS
   ============================================================ */

function getBookReaderSquareElement(square) {

    if (!board || !square) {
        return null;
    }

    return board.querySelector(
        `.sq[data-sq="${square}"]`
    );
}


function getBookReaderPieceElement(square) {

    const squareElement =
        getBookReaderSquareElement(square);

    return squareElement
        ? squareElement.querySelector(".pc")
        : null;
}


function getBookReaderSquareAtPoint(
    clientX,
    clientY
) {

    if (!board) {
        return null;
    }

    const rect =
        board.getBoundingClientRect();

    if (
        clientX < rect.left ||
        clientX >= rect.right ||
        clientY < rect.top ||
        clientY >= rect.bottom
    ) {
        return null;
    }

    const size =
        rect.width / 8;

    let col =
        Math.floor(
            (clientX - rect.left) /
            size
        );

    let row =
        Math.floor(
            (clientY - rect.top) /
            size
        );

    col = Math.max(
        0,
        Math.min(7, col)
    );

    row = Math.max(
        0,
        Math.min(7, row)
    );

    /*
     * Barabosik's renderer reverses the displayed
     * coordinates when flip=true.
     */
    if (state.flip) {
        row = 7 - row;
        col = 7 - col;
    }

    return (
        "abcdefgh"[col] +
        (8 - row)
    );
}


function isBookReaderLegalMove(
    from,
    to
) {

    if (!from || !to) {
        return false;
    }

    try {

        const chess =
            new Chess(state.fen);

        return chess
            .moves({
                square: from,
                verbose: true
            })
            .some(
                move =>
                    move.to === to
            );

    } catch {
        return false;
    }
}


/* ============================================================
   CLEANUP
   ============================================================ */

function removeBookReaderDragPiece(
    piece
) {
    
    /*
     * Restore the original board piece after drag/cancel.
     */
    document
        .querySelectorAll(
            ".book-reader-drag-source-hidden .pc"
        )
        .forEach(
            element => {
                element.style.removeProperty(
                    "display"
                );

                element.style.removeProperty(
                    "opacity"
                );

                element.style.removeProperty(
                    "visibility"
                );
            }
        );

    document
        .querySelectorAll(
            ".book-reader-drag-source-hidden"
        )
        .forEach(
            element => {
                element.classList.remove(
                    "book-reader-drag-source-hidden"
                );
            }
        );


    if (piece) {
        piece.remove();
    }

    document
        .querySelectorAll(
            ".piece-drag-layer, .piece-animation"
        )
        .forEach(
            element => {

                if (
                    element !== piece
                ) {
                    element.remove();
                }
            }
        );
}


function cleanupBookReaderPointer() {

    window.removeEventListener(
        "pointermove",
        bookReaderPointerMove
    );

    window.removeEventListener(
        "pointerup",
        bookReaderPointerUp
    );

    window.removeEventListener(
        "pointercancel",
        bookReaderPointerCancel
    );
}


/* ============================================================
   START DRAG
   ============================================================ */

console.log("CHESSMATE_DRAG_DEBUG_V2");

function startBookReaderDrag(
    event
) {

    if (
        !bookReaderPointerState ||
        bookReaderPointerState.dragging ||
        bookReaderPointerState.mode !==
            "piece"
    ) {
        return;
    }

    const from =
        bookReaderPointerState.from;

    const sourceSquare =
        getBookReaderSquareElement(
            from
        );

    if (!sourceSquare) {
        return;
    }

    const sourcePiece =
        sourceSquare.querySelector(
            ".pc"
        );

    if (!sourcePiece) {
        return;
    }

    const rect =
        sourcePiece.getBoundingClientRect();

    /*
     * EXACT HOME-BOARD BEHAVIOUR:
     * create an independent floating copy,
     * slightly larger than the board piece.
     */
    const dragScale = 1.10;

    const floating =
        sourcePiece.cloneNode(true);

    floating.classList.add(
        "piece-drag-layer"
    );

    floating.style.position =
        "fixed";

    floating.style.left =
        "0px";

    floating.style.top =
        "0px";

    floating.style.width =
        `${rect.width * dragScale}px`;

    floating.style.height =
        `${rect.height * dragScale}px`;

    floating.style.pointerEvents =
        "none";

    floating.style.zIndex =
        "10000";

    floating.style.transition =
        "none";

    floating.style.transformOrigin =
        "center center";

    floating.style.filter =
        "drop-shadow(0 8px 10px rgba(0,0,0,0.28))";

    document.body.appendChild(
        floating
    );

    /*
     * Hide the original board piece while it is being dragged.
     * This prevents the duplicate piece seen previously.
     */
    /*
     * Hide the original board piece completely while the
     * floating drag copy follows the pointer.
     */
    sourceSquare.classList.add(
        "book-reader-drag-source-hidden"
    );

    /*
     * Hide the EXACT original piece element.
     * display:none prevents the board renderer/CSS from
     * visually showing a second copy underneath the drag clone.
     */
    sourcePiece.remove();

    bookReaderPointerState.dragging =
        true;

    bookReaderPointerState.movingPiece =
        floating;

    bookReaderPointerState.pieceWidth =
        rect.width * dragScale;

    bookReaderPointerState.pieceHeight =
        rect.height * dragScale;

    moveBookReaderFloatingPiece(
        event.clientX,
        event.clientY
    );
}


/* ============================================================
   MOVE FLOATING PIECE
   ============================================================ */

function moveBookReaderFloatingPiece(
    x,
    y
) {

    const pointer =
        bookReaderPointerState;

    if (
        !pointer ||
        !pointer.movingPiece
    ) {
        return;
    }

    const halfWidth =
        pointer.pieceWidth / 2;

    const halfHeight =
        pointer.pieceHeight / 2;

    pointer.movingPiece.style.transform =
        `translate3d(
            ${x - halfWidth}px,
            ${y - halfHeight}px,
            0
        )`;
}


/* ============================================================
   DRAG HOVER
   ============================================================ */

function updateBookReaderDragHover(
    square
) {

    if (!board) {
        return;
    }

    board
        .querySelectorAll(
            ".drag-hover"
        )
        .forEach(
            element => {

                element.classList.remove(
                    "drag-hover"
                );
            }
        );

    const pointer =
        bookReaderPointerState;

    if (
        !pointer ||
        !pointer.dragging ||
        !square
    ) {
        return;
    }

    if (
        isBookReaderLegalMove(
            pointer.from,
            square
        )
    ) {

        getBookReaderSquareElement(
            square
        )?.classList.add(
            "drag-hover"
        );
    }
}


/* ============================================================
   POINTER DOWN
   ============================================================ */

// User arrow gesture: one right-button drag from source to destination.
if (!window.__chessMateReaderArrowDragBound) {
    window.__chessMateReaderArrowDragBound = true;

    document.addEventListener("pointerup", (event) => {
        if (state.userArrowStart === null ||
            state.userArrowPointerId !== event.pointerId) {
            return;
        }

        const from = state.userArrowStart;
        state.userArrowStart = null;
        state.userArrowPointerId = null;

        const target = document.elementFromPoint(event.clientX, event.clientY);
        const squareElement = target?.closest("#readerBoard [data-sq]");
        const to = squareElement?.dataset.sq;

        if (!from || !to || from === to) return;

        state.suppressNextArrowContextMenu = true;
        window.setTimeout(() => {
            state.suppressNextArrowContextMenu = false;
        }, 700);

        const existing = state.userArrows.findIndex(
            (arrow) => arrow.from === from && arrow.to === to
        );

        if (existing >= 0) {
            state.userArrows.splice(existing, 1);
        } else {
            state.userArrows.push({ from, to, color: "#e64b4b" });
        }

        renderChessBoard();
    });

    document.addEventListener("pointercancel", (event) => {
        if (state.userArrowPointerId !== event.pointerId) return;
        state.userArrowStart = null;
        state.userArrowPointerId = null;
    });
}

function handleSquareDown(
    square,
    event
) {
    if (event.button === 0 && state.userArrows.length > 0) {
        state.userArrows = [];
        renderChessBoard();
    }


    if (
        bookReaderAnimationRunning
    ) {
        return;
    }

    if (event.pointerType === "mouse" && event.button === 2) {
        event.preventDefault();
        state.userArrowStart = square;
        state.userArrowPointerId = event.pointerId;
        return;
    }

    if (
        event.pointerType === "mouse" &&
        event.button !== 0
    ) {
        return;
    }

    try {

        const chess =
            new Chess(state.fen);

        const piece =
            chess.get(square);

        if (
            !piece ||
            piece.color !== chess.turn()
        ) {
            return;
        }

        /*
         * If a square was already selected and this is a legal
         * destination, this is still allowed to be handled by
         * the normal click handler. The drag system only starts
         * after the 5px movement threshold.
         */

        bookReaderPointerState = {

            mode: "piece",

            from: square,

            startX:
                event.clientX,

            startY:
                event.clientY,

            dragging: false,

            movingPiece: null,

            pieceWidth: 0,

            pieceHeight: 0
        };

        /*
         * Match the home board:
         * immediately select the friendly piece.
         */
        state.selectedSquare =
            square;

        renderChessBoard();

        event.preventDefault();

        window.addEventListener(
            "pointermove",
            bookReaderPointerMove
        );

        window.addEventListener(
            "pointerup",
            bookReaderPointerUp
        );

        window.addEventListener(
            "pointercancel",
            bookReaderPointerCancel
        );

    } catch (error) {

        console.error(
            "Book Reader drag start failed:",
            error
        );

        bookReaderPointerState =
            null;

        cleanupBookReaderPointer();
    }
}


/* ============================================================
   POINTER MOVE
   ============================================================ */

function bookReaderPointerMove(
    event
) {

    const pointer =
        bookReaderPointerState;

    if (
        !pointer ||
        bookReaderAnimationRunning
    ) {
        return;
    }

    const dx =
        event.clientX -
        pointer.startX;

    const dy =
        event.clientY -
        pointer.startY;

    const distance =
        Math.sqrt(
            dx * dx +
            dy * dy
        );

    /*
     * EXACT HOME-BOARD STYLE:
     * do not start dragging until the pointer moves
     * more than the small threshold.
     */
    if (
        !pointer.dragging &&
        distance > DRAG_THRESHOLD_PX
    ) {

        startBookReaderDrag(
            event
        );
    }

    if (
        !pointer.dragging
    ) {
        return;
    }

    event.preventDefault();

    moveBookReaderFloatingPiece(
        event.clientX,
        event.clientY
    );

    const target =
        getBookReaderSquareAtPoint(
            event.clientX,
            event.clientY
        );

    updateBookReaderDragHover(
        target
    );
}


/* ============================================================
   POINTER UP
   ============================================================ */

function bookReaderPointerUp(
    event
) {

    const pointer =
        bookReaderPointerState;

    if (
        !pointer ||
        bookReaderAnimationRunning
    ) {
        return;
    }

    /*
     * Save the pointer state before cleanup.
     */
    bookReaderPointerState =
        null;

    cleanupBookReaderPointer();

    if (board) {

        board
            .querySelectorAll(
                ".drag-hover"
            )
            .forEach(
                element => {

                    element.classList.remove(
                        "drag-hover"
                    );
                }
            );
    }

    /*
     * If the user only clicked without moving,
     * DO NOT perform the move here.
     *
     * board.js will fire its normal click event,
     * which is handled by handleSquareClick().
     */
    if (
        !pointer.dragging
    ) {
        return;
    }

    event.preventDefault();
    event.stopPropagation();

    /*
     * Prevent board.js's click event from immediately
     * running after this drag.
     */
    suppressNextChessClick =
        true;

    const target =
        getBookReaderSquareAtPoint(
            event.clientX,
            event.clientY
        );

    /*
     * Invalid / outside-board drop:
     * remove floating piece and restore board.
     */
    if (
        !target ||
        target === pointer.from ||
        !isBookReaderLegalMove(
            pointer.from,
            target
        )
    ) {

        removeBookReaderDragPiece(
            pointer.movingPiece
        );

        state.selectedSquare =
            null;

        renderChessBoard();

        return;
    }

    /*
     * Animate THE SAME floating piece created by
     * startBookReaderDrag().
     */
    animateBookReaderMove(
        pointer.from,
        target,
        pointer.movingPiece
    );
}


/* ============================================================
   POINTER CANCEL
   ============================================================ */

function bookReaderPointerCancel() {

    const pointer =
        bookReaderPointerState;

    if (!pointer) {
        return;
    }

    bookReaderPointerState =
        null;

    cleanupBookReaderPointer();

    removeBookReaderDragPiece(
        pointer.movingPiece
    );

    state.selectedSquare =
        null;

    renderChessBoard();
}


/* ============================================================
   MOVE ANIMATION
   ============================================================ */

function animateBookReaderMove(
    from,
    to,
    draggedPiece = null
) {

    if (
        bookReaderAnimationRunning
    ) {
        return;
    }

    if (
        !isBookReaderLegalMove(
            from,
            to
        )
    ) {
        removeBookReaderDragPiece(
            draggedPiece
        );

        state.selectedSquare =
            null;

        renderChessBoard();

        return;
    }

    const sourceSquare =
        getBookReaderSquareElement(
            from
        );

    const targetSquare =
        getBookReaderSquareElement(
            to
        );

    if (
        !sourceSquare ||
        !targetSquare
    ) {
        removeBookReaderDragPiece(
            draggedPiece
        );

        state.selectedSquare =
            null;

        renderChessBoard();

        return;
    }

    const sourcePiece =
        sourceSquare.querySelector(
            ".pc"
        );

    /*
     * Click move:
     * create a floating piece exactly like the home board.
     */
    let movingPiece =
        draggedPiece;

    const sourceRect =
        sourceSquare.getBoundingClientRect();

    const targetRect =
        targetSquare.getBoundingClientRect();

    if (!movingPiece) {

        if (!sourcePiece) {
            return;
        }

        movingPiece =
            sourcePiece.cloneNode(
                true
            );

        movingPiece.classList.add(
            "piece-animation"
        );

        movingPiece.style.position =
            "fixed";

        movingPiece.style.left =
            "0px";

        movingPiece.style.top =
            "0px";

        movingPiece.style.width =
            `${sourceRect.width}px`;

        movingPiece.style.height =
            `${sourceRect.height}px`;

        movingPiece.style.pointerEvents =
            "none";

        movingPiece.style.zIndex =
            "10000";

        movingPiece.style.transition =
            "none";

        movingPiece.style.transform =
            `translate3d(
                ${sourceRect.left}px,
                ${sourceRect.top}px,
                0
            )`;

        movingPiece.style.transformOrigin =
            "center center";

        movingPiece.style.filter =
            "drop-shadow(0 5px 7px rgba(0,0,0,0.22))";

        document.body.appendChild(
            movingPiece
        );

    } else {

        /*
         * Drag move:
         * REUSE the floating piece.
         * Never create a second copy.
         */
        movingPiece.classList.remove(
            "piece-drag-layer"
        );

        movingPiece.classList.add(
            "piece-animation"
        );

        movingPiece.style.transition =
            "none";

        movingPiece.style.filter =
            "drop-shadow(0 5px 7px rgba(0,0,0,0.22))";
    }

    /*
     * Hide the original source piece.
     */
    if (sourcePiece) {
        sourcePiece.style.opacity =
            "0";
    }

    /*
     * Hide the destination piece during the animation.
     * This is especially important for captures.
     */
    const capturedPiece =
        targetSquare.querySelector(
            ".pc"
        );

    if (capturedPiece) {
        capturedPiece.style.opacity =
            "0";
    }

    const targetX =
        targetRect.left +
        targetRect.width / 2;

    const targetY =
        targetRect.top +
        targetRect.height / 2;

    /*
     * Keep the actual floating piece dimensions during
     * the release animation. This prevents the drag piece
     * from jumping or resizing when the mouse is released.
     */
    const movingRect =
        movingPiece.getBoundingClientRect();

    const finalX =
        targetX -
        movingRect.width / 2;

    const finalY =
        targetY -
        movingRect.height / 2;

    bookReaderAnimationRunning =
        true;

    /*
     * Force layout exactly like the home board.
     */
    void movingPiece.offsetWidth;

    /*
     * Chess.com-like smooth movement.
     */
    requestAnimationFrame(
        () => {

            requestAnimationFrame(
                () => {

                    movingPiece.style.transition =
                        `transform ${MOVE_ANIMATION_MS}ms cubic-bezier(.22,.61,.36,1)`;

                    movingPiece.style.transformOrigin =
                        "center center";

                    movingPiece.style.transform =
                        `translate3d(
                            ${finalX}px,
                            ${finalY}px,
                            0
                        )`;
                }
            );
        }
    );

    /*
     * Commit state AFTER the visual animation.
     */
    setTimeout(
        () => {

            let moveSucceeded =
                false;

            try {

                const chess =
                    new Chess(state.fen);

                const move =
                    chess.move({
                        from,
                        to,
                        promotion: "q"
                    });

                if (move) {

                    state.fen =
                        chess.fen();

                    const playedMove = {
                        from:
                            move.from,

                        to:
                            move.to
                    };

                    /*
                     * If the user had gone backward in the
                     * move timeline, discard the future.
                     */
                    if (
                        state.moveIndex <
                        state.moveHistory.length - 1
                    ) {

                        state.moveHistory =
                            state.moveHistory.slice(
                                0,
                                state.moveIndex + 1
                            );
                    }

                    state.moveHistory.push(
                        state.fen
                    );

                    state.moveIndex =
                        state.moveHistory.length - 1;

                    state.lastMove =
                        playedMove;

                    moveSucceeded =
                        true;
                }

            } catch (error) {

                console.error(
                    "Book Reader move failed:",
                    error
                );
            }

            /*
             * Remove the SAME temporary piece.
             */
            removeBookReaderDragPiece(
                movingPiece
            );

            bookReaderAnimationRunning =
                false;

            state.selectedSquare =
                null;

            /*
             * Rebuild the actual Barabosik board
             * from the new FEN.
             */
            renderChessBoard();

            updateFenUI();
            renderMoveNotation();
            updateMoveButtons();

            if (!moveSucceeded) {
                console.warn(
                    "Book Reader move was not committed."
                );
            }

        },
        MOVE_ANIMATION_MS
    );
}


/* ============================================================
   CLICK TO MOVE
   ============================================================ */

function handleSquareClick(
    square
) {

    /*
     * A completed drag produces a click event afterwards.
     * Ignore exactly that click.
     */
    if (
        suppressNextChessClick
    ) {

        suppressNextChessClick =
            false;

        return;
    }

    if (
        bookReaderAnimationRunning
    ) {
        return;
    }

    try {

        const chess =
            new Chess(state.fen);

        /*
         * Nothing selected:
         * select a friendly piece.
         */
        if (
            !state.selectedSquare
        ) {

            const piece =
                chess.get(square);

            if (!piece) {
                return;
            }

            if (
                piece.color !==
                chess.turn()
            ) {
                return;
            }

            state.selectedSquare =
                square;

            renderChessBoard();

            return;
        }

        /*
         * Clicking the selected square clears selection.
         */
        if (
            state.selectedSquare ===
            square
        ) {

            state.selectedSquare =
                null;

            renderChessBoard();

            return;
        }

        const from =
            state.selectedSquare;

        /*
         * Legal click-to-move.
         *
         * Use the SAME animation engine as drag/drop,
         * but without a dragged piece.
         */
        if (
            isBookReaderLegalMove(
                from,
                square
            )
        ) {

            animateBookReaderMove(
                from,
                square,
                null
            );

            return;
        }

        /*
         * Invalid destination:
         * if another friendly piece was clicked,
         * select that piece instead.
         */
        const clickedPiece =
            chess.get(square);

        if (
            clickedPiece &&
            clickedPiece.color ===
            chess.turn()
        ) {

            state.selectedSquare =
                square;

            renderChessBoard();

            return;
        }

        state.selectedSquare =
            null;

        renderChessBoard();

    } catch (error) {

        console.error(
            "Book Reader click move failed:",
            error
        );
    }
}


/* ============================================================
   END OF HOME-BOARD-STYLE PIECE INTERACTION
   ============================================================ */

/* ============================================================
   MOVE NOTATION
   ============================================================ */

function notationFromTransition(
    beforeFen,
    afterFen
) {

    try {

        const before =
            new Chess(beforeFen);

        const moves =
            before.moves({
                verbose: true
            });

        for (
            const candidate of moves
        ) {

            try {

                const test =
                    new Chess(
                        beforeFen
                    );

                test.move(
                    candidate
                );

                if (
                    test.fen() ===
                    afterFen
                ) {

                    return candidate.san;
                }

            } catch {
                /* Ignore candidate */
            }
        }

    } catch {
        /* Ignore */
    }

    return "";
}


function renderMoveNotation() {

    if (!moveNotation) {
        return;
    }

    const history =
        state.moveHistory || [];


    if (history.length <= 1) {

        moveNotation.innerHTML = `
            <div class="move-notation-empty">
                No moves played yet
            </div>
        `;

        if (moveNotationCount) {

            moveNotationCount.textContent =
                "0 moves";
        }

        return;
    }


    const moves = [];


    for (
        let i = 1;
        i < history.length;
        i++
    ) {

        moves.push(
            notationFromTransition(
                history[i - 1],
                history[i]
            )
        );
    }


    let html = "";


    for (
        let i = 0;
        i < moves.length;
        i += 2
    ) {

        const number =
            Math.floor(i / 2) + 1;

        html += `
            <div class="notation-row">

                <span>
                    ${number}.
                </span>

                <span>
                    ${moves[i] || ""}
                </span>

                <span>
                    ${moves[i + 1] || ""}
                </span>

            </div>
        `;
    }


    moveNotation.innerHTML =
        html;


    if (moveNotationCount) {

        const count =
            moves.length;

        moveNotationCount.textContent =
            `${count} ${
                count === 1
                    ? "move"
                    : "moves"
            }`;
    }


    moveNotation.scrollTop =
        moveNotation.scrollHeight;
}


/* ============================================================
   MOVE HISTORY
   ============================================================ */

function restoreHistoryPosition(
    index
) {

    if (
        index < 0 ||
        index >=
            state.moveHistory.length
    ) {
        return;
    }

    state.moveIndex =
        index;

    state.fen =
        state.moveHistory[index];

    state.lastMove =
        null;

    state.selectedSquare =
        null;

    renderChessBoard();

    updateFenUI();

    updateMoveButtons();
}


function firstMove() {

    restoreHistoryPosition(0);
}


function previousMove() {

    restoreHistoryPosition(
        state.moveIndex - 1
    );
}


function nextMove() {

    restoreHistoryPosition(
        state.moveIndex + 1
    );
}


function lastMove() {

    restoreHistoryPosition(
        state.moveHistory.length - 1
    );
}


function updateMoveButtons() {

    const first =
        document.querySelector(
            "[data-action='first']"
        );

    const previous =
        document.querySelector(
            "[data-action='prev']"
        );

    const next =
        document.querySelector(
            "[data-action='next']"
        );

    const last =
        document.querySelector(
            "[data-action='last']"
        );


    if (first) {

        first.disabled =
            state.moveIndex <= 0;
    }

    if (previous) {

        previous.disabled =
            state.moveIndex <= 0;
    }

    if (next) {

        next.disabled =
            state.moveIndex >=
            state.moveHistory.length - 1;
    }

    if (last) {

        last.disabled =
            state.moveIndex >=
            state.moveHistory.length - 1;
    }
}


/* ============================================================
   FEN
   ============================================================ */

function updateFenUI() {

    if (!fenDisplay) {
        return;
    }

    fenDisplay.textContent =
        state.fen;
}


/* ============================================================
   BOARD ACTIONS
   ============================================================ */

function resetBoard() {

    state.fen =
        START_FEN;

    state.moveHistory =
        [START_FEN];

    state.moveIndex =
        0;

    state.lastMove =
        null;

    state.selectedSquare =
        null;

    renderChessBoard();

    updateFenUI();

    renderMoveNotation();

    updateMoveButtons();
}


function clearBoard() {

    const emptyFen =
        "4k3/8/8/8/8/8/8/4K3 w - - 0 1";

    state.fen =
        emptyFen;

    state.moveHistory =
        [emptyFen];

    state.moveIndex =
        0;

    state.lastMove =
        null;

    state.selectedSquare =
        null;

    renderChessBoard();

    updateFenUI();

    renderMoveNotation();

    updateMoveButtons();
}


function flipBoard() {

    state.flip =
        !state.flip;

    renderChessBoard();

    if (typeof updateBookEvalOrientation === "function") {
        updateBookEvalOrientation();
    }

    if (
        state.magnusEnabled &&
        bookMagnus.booted
    ) {
        restartBookLive();
    }
}


/* ============================================================
   PAGE UI
   ============================================================ */

function updatePageUI() {

    if (pageCurrent) {

        pageCurrent.value =
            state.page;
    }

    if (pageTotal) {

        pageTotal.textContent =
            state.totalPages;
    }

    if (pageSlider) {

        pageSlider.value =
            state.page;
    }

    updatePdfViewer();
}


/* ============================================================
   CHESSMATE BOOK PAGE MEMORY
   Remembers the last page separately for every book.
   ============================================================ */

function getBookPageKey(bookId) {

    return `chessmate:lastPage:${bookId}`;
}


function getSavedBookPage(bookId) {

    if (!bookId) {
        return 1;
    }

    try {

        const saved =
            Number(
                localStorage.getItem(
                    getBookPageKey(bookId)
                )
            );

        return Number.isFinite(saved) &&
            saved >= 1
            ? saved
            : 1;

    } catch (error) {

        console.warn(
            "[ChessMate] Could not read saved book page:",
            error
        );

        return 1;
    }
}


function saveBookPage(bookId, pageNumber) {

    if (!bookId) {
        return;
    }

    try {

        localStorage.setItem(
            getBookPageKey(bookId),
            String(pageNumber)
        );

    } catch (error) {

        console.warn(
            "[ChessMate] Could not save book page:",
            error
        );
    }
}


/* ============================================================
   PAGE / POSITION LOADING
   ============================================================ */

async function loadPage(
    pageNumber
) {

    pageNumber =
        Math.max(
            1,
            Math.min(
                state.totalPages,
                Number(pageNumber)
            )
        );


    state.page =
        pageNumber;

    saveBookPage(
        BOOK_ID,
        state.page
    );

    updatePageUI();


    try {

        const response =
            await fetch(
                `${API_BASE}/books/` +
                `${encodeURIComponent(BOOK_ID)}` +
                `/pages/${pageNumber}`
            );


        if (!response.ok) {

            throw new Error(
                `HTTP ${response.status}`
            );
        }


        const data =
            await response.json();


        state.positions =
            Array.isArray(
                data.positions
            )
                ? data.positions
                : [];


        state.positionIndex =
            0;


        /*
         * IMPORTANT:
         *
         * Changing the PDF page must NOT reset
         * the ChessMate board.
         *
         * PDF navigation and the interactive
         * chessboard are independent surfaces.
         *
         * Detected positions for the current
         * PDF page remain available in
         * state.positions.
         *
         * The current interactive board state
         * is intentionally preserved.
         */

        updateFenUI();
        updateMoveButtons();
        updateSideToMoveToggle();

    } catch (error) {

        console.error(
            "Book page loading failed:",
            error
        );
    }
}


/* ============================================================
   PAGE NAVIGATION
   ============================================================ */

function previousPage() {

    loadPage(
        state.page - 1
    );
}


function nextPage() {

    loadPage(
        state.page + 1
    );
}


/* ============================================================
   BUTTON BINDING
   ============================================================ */

function bind(
    selector,
    handler
) {

    const button =
        document.querySelector(
            selector
        );

    if (!button) {
        return;
    }

    button.addEventListener(
        "click",
        handler
    );
}


/* Move controls */

bind(
    "[data-action='first']",
    firstMove
);

bind(
    "[data-action='prev']",
    previousMove
);

bind(
    "[data-action='next']",
    nextMove
);

bind(
    "[data-action='last']",
    lastMove
);


/* Board controls */

bind(
    "[data-action='reset']",
    resetBoard
);

bind(
    "#resetBoardButton",
    resetBoard
);

bind(
    "[data-action='flip']",
    flipBoard
);

bind(
    "[data-action='clear']",
    clearBoard
);


/* PDF page controls */

bind(
    "[data-action='page-prev']",
    previousPage
);

bind(
    "[data-action='page-next']",
    nextPage
);


/* ============================================================
   DIRECT PAGE JUMP
   ============================================================ */

const pageNumberInput =
    document.getElementById(
        "pageNumberInput"
    );

if (pageNumberInput) {

    pageNumberInput.addEventListener(
        "keydown",
        event => {

            if (event.key !== "Enter") {
                return;
            }

            const requestedPage =
                Number(
                    pageNumberInput.value
                );

            if (!Number.isFinite(requestedPage)) {

                pageNumberInput.value =
                    state.page;

                return;
            }

            const targetPage =
                Math.max(
                    1,
                    Math.min(
                        state.totalPages,
                        Math.floor(requestedPage)
                    )
                );

            pageNumberInput.value =
                targetPage;

            loadPage(
                targetPage
            );
        }
    );

    pageNumberInput.addEventListener(
        "focus",
        () => {
            pageNumberInput.select();
        }
    );

    pageNumberInput.addEventListener(
        "blur",
        () => {
            pageNumberInput.value =
                state.page;
        }
    );
}

/* ============================================================
   PAGE SLIDER
   ============================================================ */

if (pageSlider) {

    pageSlider.addEventListener(
        "input",
        event => {

            loadPage(
                Number(
                    event.target.value
                )
            );
        }
    );
}


/* ============================================================
   KEYBOARD
   ============================================================ */

document.addEventListener(
    "keydown",
    event => {

        if (
            event.target instanceof
            HTMLInputElement
        ) {
            return;
        }


        if (
            event.key ===
            "ArrowLeft"
        ) {

            previousMove();

        } else if (
            event.key ===
            "ArrowRight"
        ) {

            nextMove();

        } else if (
            event.key.toLowerCase() ===
            "f"
        ) {

            flipBoard();
        }
    }
);


/* ============================================================
   BACK TO CHESSMATE
   ============================================================ */

const backButton =
    document.getElementById(
        "backToChessMate"
    );

if (backButton) {

    backButton.addEventListener(
        "click",
        () => {

            window.location.href =
                "./index.html";
        }
    );
}


/* ============================================================
   DRAGGABLE BOOK / BOARD DIVIDER
   ============================================================ */

function setupResizer() {

    const main =
        document.querySelector(
            ".book-reader-main"
        );

    const resizer =
        document.getElementById(
            "readerResizer"
        );

    if (
        !main ||
        !resizer
    ) {
        return;
    }


    let dragging = false;


    const MIN_BOOK =
        420;

    const MIN_BOARD =
        420;


    function setBookWidth(
        clientX
    ) {

        const rect =
            main.getBoundingClientRect();

        if (!rect.width) {
            return;
        }


        let width =
            clientX -
            rect.left;


        const max =
            rect.width -
            MIN_BOARD -
            28;


        width =
            Math.max(
                MIN_BOOK,
                Math.min(
                    max,
                    width
                )
            );


        const percentage =
            (width /
                rect.width) *
            100;


        main.style.setProperty(
            "--book-panel-width",
            `${percentage}%`
        );
    }


    function pointerDown(
        event
    ) {

        event.preventDefault();

        dragging = true;

        main.classList.add(
            "resizing"
        );

        resizer.classList.add(
            "dragging"
        );

        resizer.setPointerCapture(
            event.pointerId
        );
    }


    function pointerMove(
        event
    ) {

        if (!dragging) {
            return;
        }

        setBookWidth(
            event.clientX
        );
    }


    function pointerUp(
        event
    ) {

        if (!dragging) {
            return;
        }

        dragging = false;

        main.classList.remove(
            "resizing"
        );

        resizer.classList.remove(
            "dragging"
        );

        try {

            resizer.releasePointerCapture(
                event.pointerId
            );

        } catch {}
    }


    resizer.addEventListener(
        "pointerdown",
        pointerDown
    );

    resizer.addEventListener(
        "pointermove",
        pointerMove
    );

    resizer.addEventListener(
        "pointerup",
        pointerUp
    );

    resizer.addEventListener(
        "pointercancel",
        pointerUp
    );


    resizer.addEventListener(
        "dblclick",
        () => {

            main.style.setProperty(
                "--book-panel-width",
                "52%"
            );
        }
    );


    resizer.addEventListener(
        "keydown",
        event => {

            const current =
                parseFloat(
                    getComputedStyle(
                        main
                    ).getPropertyValue(
                        "--book-panel-width"
                    )
                ) || 52;


            if (
                event.key ===
                "ArrowLeft"
            ) {

                event.preventDefault();

                main.style.setProperty(
                    "--book-panel-width",
                    `${Math.max(
                        35,
                        current - 2
                    )}%`
                );

            } else if (
                event.key ===
                "ArrowRight"
            ) {

                event.preventDefault();

                main.style.setProperty(
                    "--book-panel-width",
                    `${Math.min(
                        70,
                        current + 2
                    )}%`
                );
            }
        }
    );
}


/* ============================================================
   INITIALIZE
   ============================================================ */

updatePageUI();

updateFenUI();

renderChessBoard();

renderMoveNotation();

updateMoveButtons();

setupResizer();

loadPage(
    getSavedBookPage(BOOK_ID)
);

/* ============================================================
   CHESSMATE BOOK READER — MAGNUS
   ============================================================ */

const BOOK_ENGINE_URL = () =>
    new URL(
        "../vendor/magnus/magnus-18-lite-single.js",
        import.meta.url
    );

const BOOK_LIVE_DEPTH = 20;

const bookMagnus = {
    engine: null,
    booted: false,
    booting: false,
    generation: 0,
    timer: null,
    lastCp: 0,
    lastMate: null
};

const readerEvalBar =
    document.getElementById("readerEvalBar");

const readerEvalFill =
    document.getElementById("readerEvalFill");

const readerEvalNum =
    document.getElementById("readerEvalNum");

const magnusToggle =
    document.getElementById("magnusToggle");


/* ============================================================
   TOGGLE
   ============================================================ */

function syncMagnusToggle() {

    if (!magnusToggle) {
        return;
    }

    magnusToggle.checked =
        !!state.magnusEnabled;

    const control =
        document.getElementById(
            "magnusControl"
        );

    if (control) {
        control.classList.toggle(
            "is-on",
            !!state.magnusEnabled
        );
    }
}


/* ============================================================
   EVALUATION BAR
   ============================================================ */

function bookWinPercent(cp, mate) {

    if (mate != null) {
        return mate > 0 ? 100 : 0;
    }

    return Math.max(
        0,
        Math.min(
            100,
            winPct(cp || 0)
        )
    );
}


function bookEvalText(cp, mate) {

    if (mate != null) {
        return "M" + Math.abs(mate);
    }

    if (
        Math.abs(cp || 0) >=
        MATE_CP
    ) {
        return "#";
    }

    return (
        Math.abs(cp || 0) / 100
    ).toFixed(1);
}


function updateBookEvalOrientation() {

    if (readerEvalFill) {

        readerEvalFill.style.transformOrigin =
            state.flip
                ? "top"
                : "bottom";
    }

    if (readerEvalBar) {

        readerEvalBar.classList.toggle(
            "evalbar-flipped",
            !!state.flip
        );
    }

    if (readerEvalNum) {

        const wp =
            bookWinPercent(
                bookMagnus.lastCp,
                bookMagnus.lastMate
            );

        const whiteAdvantage =
            wp >= 50;

        const whiteIsBottom =
            !state.flip;

        const putBottom =
            whiteAdvantage ===
            whiteIsBottom;

        readerEvalNum.className =
            "evalnum " +
            (
                putBottom
                    ? "bot"
                    : "top"
            );
    }
}


function updateBookEvalBar(
    cp,
    mate
) {

    if (
        !readerEvalFill ||
        !readerEvalNum
    ) {
        return;
    }

    bookMagnus.lastCp =
        cp || 0;

    bookMagnus.lastMate =
        mate;

    const wp =
        bookWinPercent(
            cp,
            mate
        );

    readerEvalFill.style.transform =
        "scaleY(" +
        (wp / 100) +
        ")";

    readerEvalNum.textContent =
        bookEvalText(
            cp,
            mate
        );

    updateBookEvalOrientation();
}


function clearBookEval() {

    bookMagnus.lastCp = 0;
    bookMagnus.lastMate = null;

    if (readerEvalFill) {

        readerEvalFill.style.transform =
            "scaleY(.5)";
    }

    if (readerEvalNum) {
        readerEvalNum.textContent = "—";
    }

    updateBookEvalOrientation();
}


/* ============================================================
   BEST MOVE ARROW
   ============================================================ */

function setMagnusBestArrow(line) {

    if (
        !state.magnusEnabled ||
        !line
    ) {
        state.magnusArrows = [];
        return;
    }

    const move =
        line.move ||
        (
            Array.isArray(line.pv)
                ? line.pv[0]
                : null
        );

    if (
        !move ||
        !/^[a-h][1-8][a-h][1-8]/.test(move)
    ) {
        state.magnusArrows = [];
        return;
    }

    state.magnusArrows = [
        {
            from: move.slice(0, 2),
            to: move.slice(2, 4)
        }
    ];
}


/* ============================================================
   LIVE SEARCH
   ============================================================ */

function restartBookLive() {

    clearTimeout(
        bookMagnus.timer
    );

    ++bookMagnus.generation;

    if (
        !state.magnusEnabled
    ) {

        state.magnusArrows = [];

        if (bookMagnus.engine) {
            bookMagnus.engine.stopLive();
        }

        clearBookEval();

        return;
    }

    if (
        !bookMagnus.booted ||
        !bookMagnus.engine ||
        !state.fen ||
        document.hidden
    ) {
        return;
    }

    const generation =
        bookMagnus.generation;

    
    bookMagnus.lastFen = state.fen;
state.magnusArrows = [];

    bookMagnus.timer =
        setTimeout(
            async () => {

                if (
                    generation !==
                    bookMagnus.generation
                ) {
                    return;
                }

                try {

                    await bookMagnus.engine.stopLive();

                    if (
                        generation !==
                        bookMagnus.generation
                    ) {
                        return;
                    }

                    if (
                        !state.magnusEnabled
                    ) {
                        return;
                    }

                    bookMagnus.engine.live(
                        state.fen,
                        {
                            multipv: 1,
                            depth: BOOK_LIVE_DEPTH,
                            infinite: true,

                            onUpdate:
                                (lines) => {

                                    if (
                                        generation !==
                                        bookMagnus.generation
                                    ) {
                                        return;
                                    }

                                    if (
                                        !state.magnusEnabled ||
                                        !lines ||
                                        !lines.length
                                    ) {
                                        return;
                                    }

                                    const top =
                                        lines[0];

                                    updateBookEvalBar(
                                        top.cp,
                                        top.mate
                                    );

                                    setMagnusBestArrow(
                                        top
                                    );

                                    /*
                                     * Render the existing
                                     * Barabosik board.
                                     */
                                    
                                    /*
                                     * Do not rebuild the board while
                                     * a piece is being dragged.
                                     *
                                     * Magnus updates are asynchronous.
                                     * renderBoard() recreates the board
                                     * pieces and can create a duplicate
                                     * underneath the floating piece.
                                     */
                                    if (
                                        bookReaderPointerState &&
                                        bookReaderPointerState.dragging
                                    ) {
                                        return;
                                    }

renderBoard(
                                        board,
                                        state.fen,
                                        {
                                            flip:
                                                state.flip,

                                            lastMove:
                                                state.lastMove,

                                            selected:
                                                state.selectedSquare,

                                            targets:
                                                state.selectedSquare
                                                    ? legalTargets(
                                                        state.fen,
                                                        state.selectedSquare
                                                    )
                                                    : [],

                                            arrows: [
                                                ...(state.magnusEnabled ? state.magnusArrows : []),
                                                ...state.userArrows
                                            ],

                                            marks: [],

                                            onSquareClick:
                                                handleSquareClick,

                                            onSquareDown:
                                                handleSquareDown
                                        }
                                    );
                                }
                        }
                    );

                } catch (error) {

                    console.error(
                        "[ChessMate] Magnus live error:",
                        error
                    );
                }

            },
            90
        );
}


/* ============================================================
   BOOT
   ============================================================ */

async function bootBookMagnus() {

    if (
        !state.magnusEnabled
    ) {
        return;
    }

    if (
        bookMagnus.booted ||
        bookMagnus.booting
    ) {
        restartBookLive();
        return;
    }

    bookMagnus.booting = true;

    try {

        console.log(
            "[ChessMate] Starting Magnus..."
        );

        bookMagnus.engine =
            new Engine(
                BOOK_ENGINE_URL()
            );

        await bookMagnus.engine.boot();

        bookMagnus.booted = true;

        console.log(
            "[ChessMate] Magnus READY"
        );

        updateBookEvalBar(
            0,
            null
        );

        restartBookLive();

    } catch (error) {

        console.error(
            "[ChessMate] Magnus BOOT FAILED:",
            error
        );

    } finally {

        bookMagnus.booting = false;
    }
}


/* ============================================================
   MAGNUS ON / OFF
   ============================================================ */

function toggleMagnus() {

    state.magnusEnabled =
        !!magnusToggle.checked;

    syncMagnusToggle();

    ++bookMagnus.generation;

    clearTimeout(
        bookMagnus.timer
    );

    if (
        !state.magnusEnabled
    ) {

        state.magnusArrows = [];

        if (bookMagnus.engine) {
            bookMagnus.engine.stopLive();
        }

        clearBookEval();

        renderChessBoard();

        console.log(
            "[ChessMate] Magnus OFF"
        );

        return;
    }

    console.log(
        "[ChessMate] Magnus ON"
    );

    if (
        bookMagnus.booted
    ) {
        restartBookLive();
    }
    else {
        bootBookMagnus();
    }
}


/* ============================================================
   FLIP HOOK
   ============================================================ */

function updateMagnusAfterFlip() {

    updateBookEvalOrientation();

    /*
     * Re-render using the same Barabosik board
     * with the current flipped orientation.
     */
    if (
        state.magnusEnabled &&
        state.magnusArrows.length
    ) {

        renderBoard(
            board,
            state.fen,
            {
                flip:
                    state.flip,

                lastMove:
                    state.lastMove,

                selected:
                    state.selectedSquare,

                targets:
                    state.selectedSquare
                        ? legalTargets(
                            state.fen,
                            state.selectedSquare
                        )
                        : [],

                arrows: [
                    ...state.magnusArrows,
                    ...state.userArrows
                ],

                marks: [],

                onSquareClick:
                    handleSquareClick,

                onSquareDown:
                    handleSquareDown
            }
        );
    }
}


/* ============================================================
   TOGGLE EVENT
   ============================================================ */

if (magnusToggle) {

    magnusToggle.addEventListener(
        "change",
        toggleMagnus
    );

    syncMagnusToggle();
}


/* ============================================================
   VISIBILITY
   ============================================================ */

document.addEventListener(
    "visibilitychange",
    () => {

        if (document.hidden) {

            ++bookMagnus.generation;

            clearTimeout(
                bookMagnus.timer
            );

            if (bookMagnus.engine) {
                bookMagnus.engine.stopLive();
            }

        }
        else if (
            state.magnusEnabled
        ) {

            restartBookLive();
        }
    }
);


/* ============================================================
   START
   ============================================================ */

updateBookEvalOrientation();

setTimeout(
    () => {

        if (
            state.magnusEnabled
        ) {
            bootBookMagnus();
        }

    },
    300
);





/* ============================================================
   CHESSMATE CONTINUOUS MAGNUS POSITION WATCHER
   ============================================================ */

bookMagnus.lastFen = null;

bookMagnus.positionWatcher =
    setInterval(
        () => {

            if (
                !state.magnusEnabled ||
                !bookMagnus.booted ||
                document.hidden ||
                !state.fen
            ) {
                return;
            }

            if (
                bookMagnus.lastFen !== state.fen
            ) {

                bookMagnus.lastFen =
                    state.fen;

                console.log(
                    "[ChessMate] Magnus: position changed -> restarting analysis"
                );

                restartBookLive();
            }

        },
        300
    );




/* ============================================================
   CHESSMATE PDF.JS VIEWER
   ============================================================ */

let pdfDocument = null;

let pdfZoom = 1;

let pdfFitMode = true;

let pdfRendering = false;

let pdfRenderQueued = false;

async function loadChessMatePdf() {

    try {

        pdfjsLib.GlobalWorkerOptions.workerSrc =
            "../node_modules/pdfjs-dist/build/pdf.worker.mjs";

        const url =
            `${API_BASE}/books/` +
            `${encodeURIComponent(BOOK_ID)}` +
            `/pdf`;

        console.log(
            "ChessMate PDF.js loading:",
            url
        );

        pdfDocument =
            await pdfjsLib.getDocument({ url: url }).promise;

        window.pdfjsLibReady = true;

        const totalPages =
            document.getElementById(
                "pdfTotalPages"
            );

        if (totalPages) {

            totalPages.textContent =
                String(pdfDocument.numPages);
        }

        await updatePdfViewer();

        console.log(
            "ChessMate PDF.js ready:",
            pdfDocument.numPages,
            "pages"
        );

    } catch (error) {

        console.error(
            "ChessMate PDF.js failed:",
            error
        );

    }
}

function queuePdfRender() {

    if (pdfRendering) {

        pdfRenderQueued = true;

        return;
    }

    pdfRendering = true;

    updatePdfViewer()
        .finally(() => {

            pdfRendering = false;

            if (pdfRenderQueued) {

                pdfRenderQueued = false;

                queuePdfRender();
            }
        });
}

function pdfZoomIn() {

    pdfFitMode = false;

    pdfZoom =
        Math.min(
            3,
            pdfZoom + 0.1
        );

    queuePdfRender();
}

function pdfZoomOut() {

    pdfFitMode = false;

    pdfZoom =
        Math.max(
            0.3,
            pdfZoom - 0.1
        );

    queuePdfRender();
}

function pdfFitPage() {

    pdfFitMode = true;

    queuePdfRender();
}

function pdfPreviousPage() {

    if (
        typeof previousPage ===
        "function"
    ) {

        previousPage();

    } else {

        loadPage(
            state.page - 1
        );
    }
}

function pdfNextPage() {

    if (
        typeof nextPage ===
        "function"
    ) {

        nextPage();

    } else {

        loadPage(
            state.page + 1
        );
    }
}

function setupPdfJsControls() {

    const zoomIn =
        document.getElementById(
            "pdfZoomIn"
        );

    const zoomOut =
        document.getElementById(
            "pdfZoomOut"
        );

    const fit =
        document.getElementById(
            "pdfFitPage"
        );

    const previous =
        document.getElementById(
            "pdfPrevPage"
        );

    const next =
        document.getElementById(
            "pdfNextPage"
        );

    if (zoomIn) {
        zoomIn.addEventListener(
            "click",
            pdfZoomIn
        );
    }

    if (zoomOut) {
        zoomOut.addEventListener(
            "click",
            pdfZoomOut
        );
    }

    if (fit) {
        fit.addEventListener(
            "click",
            pdfFitPage
        );
    }

    if (previous) {
        previous.addEventListener(
            "click",
            pdfPreviousPage
        );
    }

    if (next) {
        next.addEventListener(
            "click",
            pdfNextPage
        );
    }

    window.addEventListener(
        "resize",
        () => {

            if (pdfFitMode) {
                queuePdfRender();
            }
        }
    );
}

window.pdfjsLibReady = false;

setupPdfJsControls();

setTimeout(
    loadChessMatePdf,
    100
);





/* ============================================================
   CHESSMATE MOVE NOTATION AUTO SCROLL
   ============================================================ */

(() => {

    const notation = document.getElementById("moveNotation");

    if (!notation) {
        console.warn("[ChessMate] Move notation element not found.");
        return;
    }

    const scrollToLatestMove = () => {
        requestAnimationFrame(() => {
            notation.scrollTop = notation.scrollHeight;
        });
    };

    const observer = new MutationObserver(() => {
        scrollToLatestMove();
    });

    observer.observe(notation, {
        childList: true,
        subtree: true
    });

    window.chessMateScrollMoves = scrollToLatestMove;

    console.log("[ChessMate] Move notation auto-scroll enabled.");

})();



/* =========================================================
   CHESSMATE BOOK LIBRARY — UI + BOOK LIST
   ========================================================= */


/* ============================================================
   CHESSMATE BOOK LIBRARY — BOOK SWITCHING
   ============================================================ */

async function switchBook(bookId) {

    if (!bookId) {
        return;
    }

    if (bookId === BOOK_ID) {
        return;
    }

    console.log(
        "[ChessMate Library] Switching book:",
        bookId
    );

    try {

        const response =
            await fetch(
                `${API_BASE}/books/` +
                `${encodeURIComponent(bookId)}`
            );

        if (!response.ok) {
            throw new Error(
                `HTTP ${response.status}`
            );
        }

        const book =
            await response.json();

        BOOK_ID =
            book.id;

        state.page =
            getSavedBookPage(
                book.id
            );

        state.totalPages =
            Number(book.total_pages) || 1;

        state.positions =
            [];

        state.positionIndex =
            0;

        state.fen =
            START_FEN;

        state.moveHistory =
            [START_FEN];

        state.moveIndex =
            0;

        state.lastMove =
            null;

        state.selectedSquare =
            null;

        updatePageUI();

        const title =
            document.querySelector(
                ".book-panel .panel-title"
            );

        if (title) {
            title.textContent =
                book.name;
        }

        pdfDocument =
            null;

        window.pdfjsLibReady =
            false;

        await loadChessMatePdf();

        await loadPage(
            getSavedBookPage(
                BOOK_ID
            )
        );

        if (
            state.magnusEnabled &&
            bookMagnus.booted
        ) {
            restartBookLive();
        }

        if (
            typeof window.loadLibraryBooks ===
            "function"
        ) {
            window.loadLibraryBooks();
        }

        console.log(
            "[ChessMate Library] Book switched successfully:",
            BOOK_ID
        );

    } catch (error) {

        console.error(
            "[ChessMate Library] Failed to switch book:",
            error
        );
    }
}

window.switchBook =
    switchBook;


/* ============================================================
   CHESSMATE BOOK LIBRARY — UI + BOOK LIST
   ============================================================ */

(function initBookLibrary() {
    const menuButton = document.getElementById("libraryMenuButton");
    const overlay = document.getElementById("libraryOverlay");
    const backdrop = document.getElementById("libraryBackdrop");
    const closeButton = document.getElementById("libraryCloseButton");
    const booksContainer = document.getElementById("libraryBooks");
    const emptyState = document.getElementById("libraryEmpty");
    const countElement = document.getElementById("libraryCount");

    if (!menuButton || !overlay || !backdrop || !closeButton) {
        console.warn("Library UI elements not found.");
        return;
    }

    function openLibrary() {
        overlay.classList.add("open");
        overlay.setAttribute("aria-hidden", "false");
        loadLibraryBooks();
    }

    function closeLibrary() {
        overlay.classList.remove("open");
        overlay.setAttribute("aria-hidden", "true");
    }

    async function loadLibraryBooks() {
        try {
            const response = await fetch(`${API_BASE}/books`);

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }

            const data = await response.json();
            const books = Array.isArray(data.books) ? data.books : [];

            booksContainer.innerHTML = "";

            if (countElement) {
                countElement.textContent = `${books.length} / 15`;
            }

            if (emptyState) {
                emptyState.hidden = books.length !== 0;
            }

            books.forEach((book) => {
                const item = document.createElement("button");
                item.type = "button";
                item.className = "library-book-item";

                if (book.id === BOOK_ID) {
                    item.classList.add("active");
                }

                item.innerHTML = `
                    <span class="library-book-icon">??</span>
                    <span class="library-book-info">
                        <span class="library-book-name"></span>
                        <span class="library-book-status">
                            ${book.id === BOOK_ID ? "Currently open" : "Open book"}
                        </span>
                    </span>
                `;

                const nameElement = item.querySelector(".library-book-name");
                nameElement.textContent = book.name;

                item.addEventListener("click", async () => {
                    if (book.id === BOOK_ID) {
                        closeLibrary();
                        return;
                    }

                    closeLibrary();

                    if (typeof window.switchBook === "function") {
                        await window.switchBook(book.id);
                    } else {
                        console.warn("switchBook() is not available yet.");
                    }
                });

                booksContainer.appendChild(item);
            });
        } catch (error) {
            console.error("Failed to load book library:", error);

            booksContainer.innerHTML = `
                <div class="library-error">
                    Unable to load books.
                </div>
            `;
        }
    }

    menuButton.addEventListener("click", openLibrary);
    closeButton.addEventListener("click", closeLibrary);
    backdrop.addEventListener("click", closeLibrary);

    document.addEventListener("keydown", (event) => {
        if (event.key === "Escape" && overlay.classList.contains("open")) {
            closeLibrary();
        }
    });

    window.loadLibraryBooks = loadLibraryBooks;
})();




/* ============================================================
   CHESSMATE BOOK LIBRARY — PDF UPLOAD
   ============================================================ */

(function initLibraryUpload() {

    const uploadButton =
        document.getElementById(
            "libraryUploadButton"
        );

    const closeButton =
        document.getElementById(
            "libraryCloseButton"
        );

    if (!uploadButton) {
        console.warn(
            "[ChessMate Library] Upload button not found."
        );

        return;
    }

    const fileInput =
        document.createElement("input");

    fileInput.type =
        "file";

    fileInput.accept =
        ".pdf,application/pdf";

    fileInput.style.display =
        "none";

    document.body.appendChild(
        fileInput
    );


    uploadButton.addEventListener(
        "click",
        () => {

            if (
                document.getElementById(
                    "libraryCount"
                )?.textContent
            ) {

                const countText =
                    document.getElementById(
                        "libraryCount"
                    ).textContent;

                const currentCount =
                    Number(
                        countText.split("/")[0]
                    );

                if (
                    Number.isFinite(currentCount) &&
                    currentCount >= 15
                ) {

                    alert(
                        "Your Library already contains 15 books. Remove a book before uploading another."
                    );

                    return;
                }
            }

            fileInput.value =
                "";

            fileInput.click();
        }
    );


    fileInput.addEventListener(
        "change",
        async () => {

            const file =
                fileInput.files?.[0];

            if (!file) {
                return;
            }

            if (
                !file.name
                    .toLowerCase()
                    .endsWith(".pdf")
            ) {

                alert(
                    "Please select a PDF file."
                );

                return;
            }

            const originalText =
                uploadButton.textContent;

            uploadButton.disabled =
                true;

            uploadButton.textContent =
                "Uploading...";


            try {

                const formData =
                    new FormData();

                formData.append(
                    "file",
                    file
                );


                const response =
                    await fetch(
                        `${API_BASE}/books/upload`,
                        {
                            method: "POST",
                            body: formData
                        }
                    );


                const data =
                    await response.json();


                if (!response.ok) {

                    throw new Error(
                        data.error ||
                        `Upload failed (HTTP ${response.status})`
                    );
                }


                console.log(
                    "[ChessMate Library] Upload successful:",
                    data.book
                );


                if (
                    typeof window.loadLibraryBooks ===
                    "function"
                ) {

                    await window.loadLibraryBooks();
                }


                if (
                    data.book &&
                    typeof window.switchBook ===
                    "function"
                ) {

                    await window.switchBook(
                        data.book.id
                    );
                }


                if (closeButton) {
                    closeButton.click();
                }


            } catch (error) {

                console.error(
                    "[ChessMate Library] Upload failed:",
                    error
                );

                alert(
                    error.message ||
                    "Failed to upload the book."
                );

            } finally {

                uploadButton.disabled =
                    false;

                uploadButton.textContent =
                    originalText;
            }
        }
    );

})();

















