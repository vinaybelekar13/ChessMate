from pathlib import Path

p = Path("book-reader.html")
s = p.read_text(encoding="utf-8")

s = s.replace(
    '<div class="toggle">\n                <input\n                    id="sideToMoveToggle"',
    '<div class="side-to-move-toggle">\n                <input\n                    id="sideToMoveToggle"',
    1
)

p.write_text(s, encoding="utf-8")

print("SIDE_TO_MOVE_CLASS_FIXED")
