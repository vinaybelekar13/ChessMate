from pathlib import Path

p = Path("js/book-reader.js")

data = p.read_bytes()
s = data.decode("latin-1")

needle = '"[data-action=\'reset\']"'

pos = s.find(needle)

if pos == -1:
    print("RESET_SELECTOR_NOT_FOUND")
    raise SystemExit

# Find the closing ); belonging to this bind() call.
end = s.find(");", pos)

if end == -1:
    print("RESET_BIND_END_NOT_FOUND")
    raise SystemExit

end += 2

if '#resetBoardButton' in s:
    print("RESET_BUTTON_ALREADY_BOUND")
    raise SystemExit

addition = '''

bind(
    "#resetBoardButton",
    resetBoard
);'''

s = s[:end] + addition + s[end:]

p.write_bytes(s.encode("latin-1"))

print("RESET_BUTTON_BOUND")
