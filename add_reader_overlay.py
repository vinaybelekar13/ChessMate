from pathlib import Path
import re

p = Path("book-reader.html")

data = p.read_bytes()
s = data.decode("latin-1")

pattern = re.compile(
    r'<div\s+'
    r'id=["\']readerBoard["\']\s+'
    r'class=["\']board["\']\s+'
    r'aria-label=["\']Chess board["\']\s*'
    r'></div>',
    re.IGNORECASE
)

replacement = '''<div class="chessmate-board-shell">
                        <div
                            id="readerBoard"
                            class="board"
                            aria-label="Chess board"
                        ></div>

                        <div
                            id="readerGameOverlay"
                            class="chessmate-game-overlay"
                            aria-hidden="true"
                        >
                            <div class="chessmate-game-overlay-card">
                                <div
                                    id="readerGameOverlayTitle"
                                    class="chessmate-game-overlay-title"
                                ></div>

                                <div
                                    id="readerGameOverlaySubtitle"
                                    class="chessmate-game-overlay-subtitle"
                                ></div>
                            </div>
                        </div>
                    </div>'''

s2, count = pattern.subn(replacement, s, count=1)

if count != 1:
    print("READER_BOARD_REGEX_NOT_FOUND")
    raise SystemExit(1)

p.write_bytes(s2.encode("latin-1"))

print("READER_GAME_OVERLAY_HTML_ADDED")
