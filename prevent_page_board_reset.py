from pathlib import Path

p = Path("js/book-reader.js")

data = p.read_bytes()
s = data.decode("latin-1")

start_marker = "        const detected ="
end_marker = "    } catch (error) {"

start = s.find(start_marker)

if start == -1:
    print("LOAD_PAGE_START_NOT_FOUND")
    raise SystemExit

end = s.find(end_marker, start)

if end == -1:
    print("LOAD_PAGE_CATCH_NOT_FOUND")
    raise SystemExit

old = s[start:end]

new = '''        /*
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

'''

s = s[:start] + new + s[end:]

p.write_bytes(s.encode("latin-1"))

print("PAGE_CHANGE_NO_LONGER_RESETS_BOARD")
