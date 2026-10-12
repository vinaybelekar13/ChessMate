from pathlib import Path

p = Path("js/book-reader.js")
s = p.read_text(encoding="cp1252")

old = '''} else {
    bindPositionScannerButton();
}
const MOVE_ANIMATION_MS = 200;'''

new = '''} else {
    bindPositionScannerButton();
    bindSideToMoveToggle();
}
const MOVE_ANIMATION_MS = 200;'''

if old not in s:
    raise SystemExit("EXACT INITIALIZATION BLOCK NOT FOUND")

p.write_text(
    s.replace(old, new, 1),
    encoding="cp1252"
)

print("SIDE_TO_MOVE_ELSE_BINDING_FIXED")
