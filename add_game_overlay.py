from pathlib import Path

p = Path("book-reader.html")
data = p.read_bytes()
s = data.decode("latin-1")

marker = '<div id="readerBoard"'

if 'id="chessmateGameOverlay"' in s:
    print("OVERLAY_HTML_ALREADY_EXISTS")
elif marker not in s:
    print("READER_BOARD_MARKER_NOT_FOUND")
else:
    overlay = '''
<div
    id="chessmateGameOverlay"
    class="chessmate-game-overlay hidden"
    aria-hidden="true"
>
    <div class="chessmate-game-overlay-card">
        <div
            id="chessmateGameOverlayTitle"
            class="chessmate-game-overlay-title"
        >
            CHECKMATE
        </div>

        <div
            id="chessmateGameOverlaySubtitle"
            class="chessmate-game-overlay-subtitle"
        >
            Game over
        </div>
    </div>
</div>
'''

    s = s.replace(
        marker,
        overlay + "\n" + marker,
        1
    )

    p.write_bytes(s.encode("latin-1"))
    print("BOOK_READER_OVERLAY_HTML_ADDED")
