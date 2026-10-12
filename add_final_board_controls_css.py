from pathlib import Path

p = Path("css/book-reader.css")
s = p.read_text(encoding="cp1252").lstrip("\ufeff")

css = r'''

/* ============================================================
   CHESSMATE FINAL BOARD CONTROL LAYOUT
   Added after all previous layout rules intentionally.
   ============================================================ */

/* Main control container */
.book-reader-main > .analysis-panel > .chessmate-board-controls {
    width: 100% !important;
    height: auto !important;
    min-height: 76px !important;

    display: flex !important;
    flex-direction: column !important;
    align-items: center !important;
    justify-content: flex-start !important;

    gap: 7px !important;
    margin: 8px 0 10px !important;
    padding: 0 !important;

    position: relative !important;
    box-sizing: border-box !important;
}

/* ------------------------------------------------------------
   ROW 1 — FIRST / PREVIOUS / NEXT / LAST
   ------------------------------------------------------------ */

.book-reader-main > .analysis-panel > .chessmate-board-controls
.chessmate-move-controls {
    width: auto !important;
    height: 34px !important;

    display: flex !important;
    flex-direction: row !important;
    align-items: center !important;
    justify-content: center !important;

    gap: 7px !important;
    margin: 0 !important;
    padding: 0 !important;
}

/* Navigation buttons — all identical */
.book-reader-main > .analysis-panel > .chessmate-board-controls
.chessmate-move-controls > .button-90 {
    width: 42px !important;
    min-width: 42px !important;
    max-width: 42px !important;

    height: 34px !important;
    min-height: 34px !important;
    max-height: 34px !important;

    padding: 0 !important;
    margin: 0 !important;

    display: inline-flex !important;
    align-items: center !important;
    justify-content: center !important;

    box-sizing: border-box !important;
}

/* ------------------------------------------------------------
   ROW 2 — FLIP / CLEAR / SCAN / SIDE / MAGNUS
   ------------------------------------------------------------ */

.book-reader-main > .analysis-panel > .chessmate-board-controls
.chessmate-board-actions {
    width: auto !important;
    height: 34px !important;

    display: flex !important;
    flex-direction: row !important;
    align-items: center !important;
    justify-content: center !important;

    gap: 7px !important;
    margin: 0 !important;
    padding: 0 !important;

    box-sizing: border-box !important;
}

/* Every normal action button gets exactly the same dimensions */
.book-reader-main > .analysis-panel > .chessmate-board-controls
.chessmate-board-actions > .button-90,

.book-reader-main > .analysis-panel > .chessmate-board-controls
.chessmate-board-actions > #scanPositionButton {
    width: 58px !important;
    min-width: 58px !important;
    max-width: 58px !important;

    height: 34px !important;
    min-height: 34px !important;
    max-height: 34px !important;

    padding: 0 !important;
    margin: 0 !important;

    display: inline-flex !important;
    align-items: center !important;
    justify-content: center !important;

    box-sizing: border-box !important;
}

/* ------------------------------------------------------------
   WHITE / BLACK SIDE-TO-MOVE
   ------------------------------------------------------------ */

.book-reader-main > .analysis-panel > .chessmate-board-controls
.side-to-move-control {
    width: 82px !important;
    min-width: 82px !important;
    max-width: 82px !important;

    height: 34px !important;
    min-height: 34px !important;

    display: inline-flex !important;
    align-items: center !important;
    justify-content: center !important;

    gap: 5px !important;
    margin: 0 !important;
    padding: 0 !important;

    box-sizing: border-box !important;
}

.book-reader-main > .analysis-panel > .chessmate-board-controls
.side-to-move-label {
    min-width: 30px !important;

    font-size: 10px !important;
    line-height: 1 !important;
    text-align: right !important;

    white-space: nowrap !important;
}

/* Our switch is deliberately NOT called .toggle.
   This prevents interference with Magnus. */

.book-reader-main > .analysis-panel
.side-to-move-toggle {
    position: relative !important;

    width: 42px !important;
    height: 20px !important;

    flex: 0 0 42px !important;

    display: flex !important;
    align-items: center !important;

    box-sizing: border-box !important;
}

.book-reader-main > .analysis-panel
.side-to-move-toggle input[type="checkbox"] {
    position: absolute !important;
    inset: 0 !important;

    width: 100% !important;
    height: 100% !important;

    opacity: 0 !important;
    cursor: pointer !important;

    margin: 0 !important;
    z-index: 10 !important;
}

.book-reader-main > .analysis-panel
.side-to-move-toggle label {
    position: relative !important;

    display: block !important;

    width: 42px !important;
    height: 20px !important;

    margin: 0 !important;
    padding: 0 !important;

    box-sizing: border-box !important;
}

.book-reader-main > .analysis-panel
.side-to-move-toggle label::before {
    content: "" !important;

    position: absolute !important;
    inset: 0 !important;

    width: 42px !important;
    height: 20px !important;

    border-radius: 10px !important;

    background: #bbb !important;

    box-shadow:
        inset 0 1px 2px rgb(0 0 0 / 25%),
        0 1px 3px rgb(0 0 0 / 20%) !important;

    transition: .25s ease !important;
}

.book-reader-main > .analysis-panel
.side-to-move-toggle label::after {
    content: "" !important;

    position: absolute !important;

    top: 2px !important;
    left: 2px !important;

    width: 16px !important;
    height: 16px !important;

    border-radius: 50% !important;

    background: #5b5656 !important;

    box-shadow:
        0 1px 2px rgb(0 0 0 / 45%) !important;

    transition: .25s ease !important;
}

.book-reader-main > .analysis-panel
.side-to-move-toggle input[type="checkbox"]:checked + label::before {
    background: #c0e7e3 !important;
}

.book-reader-main > .analysis-panel
.side-to-move-toggle input[type="checkbox"]:checked + label::after {
    left: 24px !important;
    background: #21bf73 !important;
}

/* ------------------------------------------------------------
   MAGNUS — same 34px height as every other control
   ------------------------------------------------------------ */

.book-reader-main > .analysis-panel > .chessmate-board-controls
.magnus-control {
    width: 82px !important;
    min-width: 82px !important;
    max-width: 82px !important;

    height: 34px !important;
    min-height: 34px !important;
    max-height: 34px !important;

    display: inline-flex !important;
    align-items: center !important;
    justify-content: center !important;

    gap: 5px !important;

    margin: 0 !important;
    padding: 0 !important;

    box-sizing: border-box !important;
}

.book-reader-main > .analysis-panel > .chessmate-board-controls
.magnus-title {
    font-size: 10px !important;
    line-height: 1 !important;
    white-space: nowrap !important;
}

/* Keep the existing Magnus switch compact */
.book-reader-main > .analysis-panel > .chessmate-board-controls
.magnus-toggle-wrapper {
    transform: scale(.72) !important;
    transform-origin: center !important;
}

/* Scanner overlay must NEVER occupy space in the control row */
.position-snipper-overlay {
    position: fixed !important;
}

/* Prevent the hidden legacy controls from creating spacing */
.book-reader-main > .analysis-panel > .board-tools,
.book-reader-main > .analysis-panel > .move-controls {
    display: none !important;
}

'''

p.write_text(s.rstrip() + css, encoding="cp1252")

print("FINAL_BOARD_CONTROLS_CSS_ADDED")
