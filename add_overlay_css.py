from pathlib import Path

p = Path("css/book-reader.css")

data = p.read_bytes()
s = data.decode("latin-1")

css = r'''

/* =========================================================
   CHESSMATE GAME END OVERLAY
   ========================================================= */

.chessmate-board-shell {
    position: relative;
}

.chessmate-game-overlay {
    position: absolute;
    inset: 0;

    display: flex;
    align-items: center;
    justify-content: center;

    padding: 24px;

    background: rgba(8, 10, 16, 0.28);
    backdrop-filter: blur(4px);
    -webkit-backdrop-filter: blur(4px);

    opacity: 0;
    visibility: hidden;
    pointer-events: none;

    transform: scale(0.96);

    transition:
        opacity 180ms ease,
        transform 220ms cubic-bezier(.2,.8,.2,1),
        visibility 180ms ease;

    z-index: 20;
}

.chessmate-game-overlay.is-visible {
    opacity: 1;
    visibility: visible;
    transform: scale(1);
}

.chessmate-game-overlay-card {
    min-width: min(260px, 82%);
    max-width: 88%;

    padding: 22px 28px;

    text-align: center;

    border: 1px solid rgba(255, 255, 255, 0.16);
    border-radius: 18px;

    background:
        linear-gradient(
            135deg,
            rgba(255, 255, 255, 0.13),
            rgba(255, 255, 255, 0.055)
        );

    box-shadow:
        0 18px 50px rgba(0, 0, 0, 0.42),
        inset 0 1px 0 rgba(255, 255, 255, 0.10);

    backdrop-filter: blur(18px) saturate(130%);
    -webkit-backdrop-filter: blur(18px) saturate(130%);
}

.chessmate-game-overlay-title {
    font-size: clamp(24px, 3vw, 38px);
    line-height: 1;
    font-weight: 800;
    letter-spacing: 0.14em;
    text-transform: uppercase;

    color: #ffffff;

    text-shadow:
        0 3px 18px rgba(0, 0, 0, 0.45);
}

.chessmate-game-overlay-subtitle {
    margin-top: 10px;

    font-size: 14px;
    line-height: 1.4;
    font-weight: 600;
    letter-spacing: 0.04em;

    color: rgba(255, 255, 255, 0.72);
}

.chessmate-game-overlay-subtitle:empty {
    display: none;
}
'''

if "/* =========================================================" in s and "CHESSMATE GAME END OVERLAY" in s:
    print("READER_OVERLAY_CSS_ALREADY_PRESENT")
    raise SystemExit(0)

p.write_bytes((s + css).encode("latin-1"))

print("READER_OVERLAY_CSS_ADDED")
