from pathlib import Path

p = Path("js/book-reader.js")

data = p.read_bytes()
s = data.decode("latin-1")

if "function updateGameEndOverlay()" in s:
    print("GAME_END_OVERLAY_FUNCTION_ALREADY_PRESENT")
    raise SystemExit(0)

marker = "function renderChessBoard()"

pos = s.find(marker)

if pos == -1:
    raise SystemExit("RENDER_CHESS_BOARD_NOT_FOUND")

function_code = r'''/* ============================================================
   GAME END OVERLAY
   ============================================================ */

function updateGameEndOverlay() {

    const overlay =
        document.getElementById("readerGameOverlay");

    const title =
        document.getElementById("readerGameOverlayTitle");

    const subtitle =
        document.getElementById("readerGameOverlaySubtitle");

    if (!overlay || !title || !subtitle) {
        return;
    }

    let chess;

    try {
        chess = new Chess(state.fen);
    } catch (error) {
        overlay.classList.remove("is-visible");
        overlay.setAttribute("aria-hidden", "true");
        return;
    }

    let gameType = null;
    let gameSubtitle = "";

    /*
     * CHECKMATE
     *
     * chess.turn() is the side that is checkmated.
     * Therefore the opposite side wins.
     */
    if (
        typeof chess.isCheckmate === "function" &&
        chess.isCheckmate()
    ) {

        gameType = "CHECKMATE";

        const winner =
            chess.turn() === "w"
                ? "Black wins"
                : "White wins";

        gameSubtitle = winner;

    } else if (
        typeof chess.isStalemate === "function" &&
        chess.isStalemate()
    ) {

        gameType = "STALEMATE";
        gameSubtitle = "No legal moves";

    } else if (
        typeof chess.isDraw === "function" &&
        chess.isDraw()
    ) {

        gameType = "DRAW";
        gameSubtitle = "Game drawn";
    }

    /*
     * Normal position:
     * completely hide the overlay.
     */
    if (!gameType) {

        overlay.classList.remove("is-visible");
        overlay.setAttribute("aria-hidden", "true");

        return;
    }

    title.textContent = gameType;
    subtitle.textContent = gameSubtitle;

    overlay.classList.add("is-visible");
    overlay.setAttribute("aria-hidden", "false");
}


'''

s = s[:pos] + function_code + s[pos:]

p.write_bytes(s.encode("latin-1"))

print("GAME_END_OVERLAY_FUNCTION_ADDED")
