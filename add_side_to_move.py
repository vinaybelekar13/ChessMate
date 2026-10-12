from pathlib import Path

p = Path("book-reader.html")
s = p.read_text(encoding="utf-8")

needle = '''    <button
        class="btn-donate"
        id="scanPositionButton"
        type="button"
        title="Scan a chess position from your screen"
    >⛶</button>'''

replacement = needle + '''

        <div class="side-to-move-control" aria-label="Side to move">
            <button
                id="whiteToMoveButton"
                class="side-to-move-button active"
                type="button"
                aria-pressed="true"
            >
                ♔ White
            </button>

            <button
                id="blackToMoveButton"
                class="side-to-move-button"
                type="button"
                aria-pressed="false"
            >
                ♚ Black
            </button>
        </div>'''

if needle not in s:
    raise SystemExit("SCAN BUTTON BLOCK NOT FOUND")

p.write_text(s.replace(needle, replacement, 1), encoding="utf-8")
print("SIDE_TO_MOVE_HTML_ADDED")
