from pathlib import Path

p = Path("js/book-reader.js")

data = p.read_bytes()
s = data.decode("latin-1")

old = '''function resetBoard() {
    state.fen = START_FEN;
    state.moveHistory = [START_FEN];
    state.moveIndex = 0;
    state.lastMove = null;
    state.selectedSquare = null;
    renderChessBoard();
    updateFenUI();
    renderMoveNotation();
    updateMoveButtons();
}'''

new = '''function resetBoard() {
    state.fen = START_FEN;
    state.sideToMove = "w";
    state.moveHistory = [START_FEN];
    state.moveIndex = 0;
    state.lastMove = null;
    state.selectedSquare = null;
    state.positionIndex = 0;

    updateSideToMoveToggle();
    renderChessBoard();
    updateFenUI();
    renderMoveNotation();
    updateMoveButtons();
}'''

if 'state.sideToMove = "w";' in s[s.find("function resetBoard()"):s.find("function resetBoard()") + 1000]:
    print("RESET_FUNCTION_ALREADY_UPDATED")
elif old not in s:
    print("RESET_FUNCTION_TARGET_NOT_FOUND")
else:
    s = s.replace(old, new, 1)
    p.write_bytes(s.encode("latin-1"))
    print("RESET_BOARD_FUNCTION_UPDATED")
