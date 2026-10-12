from pathlib import Path

p = Path("css/book-reader.css")

data = p.read_bytes()
s = data.decode("latin-1")

css = r'''

/* ============================================================
   CHESSMATE GAME OVERLAY - BOARD SHELL LAYOUT FIX
   The shell replaces #readerBoard as the boardrow grid item.
   Keep it in the original board column and preserve the
   original square board dimensions.
   ============================================================ */

.book-reader-main
.reader-board-wrapper
.boardrow
.chessmate-board-shell {

    grid-column:
        2 !important;

    grid-row:
        1 !important;

    position:
        relative !important;

    width:
        100% !important;

    height:
        100% !important;

    min-width:
        0 !important;

    min-height:
        0 !important;

    aspect-ratio:
        1 / 1 !important;
}

.book-reader-main
.reader-board-wrapper
.boardrow
.chessmate-board-shell
#readerBoard.board {

    width:
        100% !important;

    height:
        100% !important;

    min-width:
        0 !important;

    min-height:
        0 !important;

    max-width:
        none !important;

    max-height:
        none !important;
}
'''

if "CHESSMATE GAME OVERLAY - BOARD SHELL LAYOUT FIX" in s:
    print("BOARD_SHELL_LAYOUT_FIX_ALREADY_PRESENT")
    raise SystemExit(0)

p.write_bytes((s + css).encode("latin-1"))

print("BOARD_SHELL_LAYOUT_FIX_ADDED")

