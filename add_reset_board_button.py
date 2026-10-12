from pathlib import Path

p = Path("book-reader.html")

data = p.read_bytes()

old = b'''<div class="chessmate-board-actions">'''

new = b'''<div class="chessmate-board-actions">
            <button
                id="resetBoardButton"
                class="button-90"
                type="button"
                title="Reset board to starting position"
            >Reset</button>'''

if b'id="resetBoardButton"' in data:
    print("RESET_BUTTON_ALREADY_EXISTS")
elif old not in data:
    print("TARGET_NOT_FOUND")
else:
    data = data.replace(old, new, 1)
    p.write_bytes(data)
    print("RESET_BOARD_BUTTON_ADDED")
