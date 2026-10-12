from pathlib import Path

p = Path("js/book-reader.js")
s = p.read_text(encoding="cp1252")

old = 'const parts = fen.trim().split(/\\\\s+/);'
new = 'const parts = fen.trim().split(/\\s+/);'

if old not in s:
    raise SystemExit("FEN SPLIT LINE NOT FOUND")

s = s.replace(old, new, 1)

p.write_text(s, encoding="cp1252")

print("FEN_SIDE_TO_MOVE_REGEX_FIXED")
