from pathlib import Path

p = Path("js/book-reader.js")

data = p.read_bytes()
s = data.decode("latin-1")

start = s.find("function renderChessBoard()")

if start == -1:
    raise SystemExit("RENDER_CHESS_BOARD_NOT_FOUND")

# Find the renderBoard call inside this function.
render_start = s.find("    renderBoard(", start)

if render_start == -1:
    raise SystemExit("RENDER_BOARD_CALL_NOT_FOUND")

# Find the closing `);` of renderBoard().
render_end = s.find("    );", render_start)

if render_end == -1:
    raise SystemExit("RENDER_BOARD_CALL_END_NOT_FOUND")

render_end += len("    );")

# Find the next function-closing brace after renderBoard().
function_end = s.find("\n}", render_end)

if function_end == -1:
    raise SystemExit("RENDER_CHESS_BOARD_CLOSING_BRACE_NOT_FOUND")

# Make sure this really is the expected function area.
preview = s[start:function_end + 2]

if "onSquareClick" not in preview or "handleSquareClick" not in preview:
    raise SystemExit("UNEXPECTED_RENDER_CHESS_BOARD_STRUCTURE")

if "updateGameEndOverlay();" in preview:
    print("GAME_END_OVERLAY_ALREADY_CONNECTED")
    raise SystemExit(0)

insertion = '''

    updateGameEndOverlay();'''

s = (
    s[:render_end]
    + insertion
    + s[function_end:]
)

p.write_bytes(s.encode("latin-1"))

print("GAME_END_OVERLAY_CONNECTED")
