from pathlib import Path

p = Path("js/book-reader.js")
s = p.read_text(encoding="cp1252")

start = s.find("function updateSideToMoveButtons()")
end = s.find("function applyScannedFen(fen)")

if start == -1 or end == -1 or end <= start:
    raise SystemExit("OLD SIDE-TO-MOVE JS BLOCK NOT FOUND")

new_block = '''function updateSideToMoveToggle() {
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


'''

s = s[:start] + new_block + s[end:]

# Make sure DOM initialization uses the new toggle.
s = s.replace(
    "bindSideToMoveButtons();",
    "bindSideToMoveToggle();"
)

p.write_text(s, encoding="cp1252")

print("SIDE_TO_MOVE_TOGGLE_JS_REPLACED")
