from pathlib import Path

p = Path("book-reader.html")
s = p.read_text(encoding="utf-8")

old = '''        <div class="side-to-move-control" aria-label="Side to move">
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

new = '''        <div class="side-to-move-control" aria-label="Side to move">
            <span
                id="sideToMoveLabel"
                class="side-to-move-label"
            >White</span>

            <div class="toggle">
                <input
                    id="sideToMoveToggle"
                    type="checkbox"
                    aria-label="Toggle side to move"
                />
                <label for="sideToMoveToggle"></label>
            </div>
        </div>'''

if old not in s:
    raise SystemExit("OLD SIDE-TO-MOVE HTML NOT FOUND")

p.write_text(
    s.replace(old, new, 1),
    encoding="utf-8"
)

print("SIDE_TO_MOVE_HTML_REPLACED")
