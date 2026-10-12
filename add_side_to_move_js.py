from pathlib import Path

p = Path("js/book-reader.js")
s = p.read_text(encoding="cp1252")

# ------------------------------------------------------------
# 1. Add sideToMove to state
# ------------------------------------------------------------

needle = '''    moveIndex: 0,
    magnusEnabled: true,'''

replacement = '''    moveIndex: 0,
    sideToMove: "w",
    magnusEnabled: true,'''

if needle not in s:
    raise SystemExit("STATE BLOCK NOT FOUND")

s = s.replace(needle, replacement, 1)


# ------------------------------------------------------------
# 2. Add side-to-move functions
# ------------------------------------------------------------

needle = '''function applyScannedFen(fen) {'''

helper = '''function setFenSideToMove(fen, side) {
    if (!fen || typeof fen !== "string") {
        return fen;
    }

    const parts = fen.trim().split(/\\\\s+/);

    if (parts.length < 2) {
        return fen;
    }

    parts[1] = side === "b" ? "b" : "w";

    return parts.join(" ");
}


function updateSideToMoveButtons() {
    const whiteButton =
        document.getElementById("whiteToMoveButton");

    const blackButton =
        document.getElementById("blackToMoveButton");

    if (!whiteButton || !blackButton) {
        return;
    }

    const whiteActive =
        state.sideToMove === "w";

    whiteButton.classList.toggle(
        "active",
        whiteActive
    );

    blackButton.classList.toggle(
        "active",
        !whiteActive
    );

    whiteButton.setAttribute(
        "aria-pressed",
        String(whiteActive)
    );

    blackButton.setAttribute(
        "aria-pressed",
        String(!whiteActive)
    );
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
        state.moveHistory.length
    ) {
        state.moveHistory[
            state.moveIndex
        ] = state.fen;
    }

    updateSideToMoveButtons();
    renderChessBoard();
}


function bindSideToMoveButtons() {
    const whiteButton =
        document.getElementById("whiteToMoveButton");

    const blackButton =
        document.getElementById("blackToMoveButton");

    if (!whiteButton || !blackButton) {
        console.warn(
            "[ChessMate] Side-to-move buttons not found."
        );
        return;
    }

    whiteButton.addEventListener(
        "click",
        () => setSideToMove("w")
    );

    blackButton.addEventListener(
        "click",
        () => setSideToMove("b")
    );

    updateSideToMoveButtons();
}


function applyScannedFen(fen) {'''

if needle not in s:
    raise SystemExit("applyScannedFen() NOT FOUND")

s = s.replace(needle, helper, 1)


# ------------------------------------------------------------
# 3. Make scanned FEN respect selected side
# ------------------------------------------------------------

needle = '''    console.log("[ChessMate] Applying scanned FEN:", fen);

    state.fen = fen;'''

replacement = '''    console.log("[ChessMate] Applying scanned FEN:", fen);

    fen = setFenSideToMove(
        fen,
        state.sideToMove
    );

    state.fen = fen;'''

if needle not in s:
    raise SystemExit("SCANNED FEN BLOCK NOT FOUND")

s = s.replace(needle, replacement, 1)


# ------------------------------------------------------------
# 4. Bind side buttons at DOM ready
# ------------------------------------------------------------

needle = '''if (document.readyState === "loading") {
    document.addEventListener(
        "DOMContentLoaded",
        bindPositionScannerButton'''

replacement = '''if (document.readyState === "loading") {
    document.addEventListener(
        "DOMContentLoaded",
        () => {
            bindPositionScannerButton();
            bindSideToMoveButtons();
        }'''

if needle not in s:
    raise SystemExit("DOM READY BLOCK NOT FOUND")

s = s.replace(needle, replacement, 1)

# Preserve the existing file encoding.
p.write_text(s, encoding="cp1252")

print("SIDE_TO_MOVE_JS_ADDED")
