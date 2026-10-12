from pathlib import Path

p = Path("css/book-reader.css")
s = p.read_text(encoding="cp1252").lstrip("\ufeff")

css = r'''

/* ============================================================
   CHESS POSITION SNIPPER OVERLAY
   Hidden until the scanner is explicitly opened.
   ============================================================ */

.position-snipper-overlay {
    position: fixed !important;
    inset: 0 !important;

    width: 100vw !important;
    height: 100vh !important;

    display: none !important;

    z-index: 99999 !important;

    margin: 0 !important;
    padding: 0 !important;

    box-sizing: border-box !important;

    background: rgba(0, 0, 0, 0.18) !important;
    cursor: crosshair !important;
}

/* JavaScript opens the overlay by removing aria-hidden */
.position-snipper-overlay[aria-hidden="false"] {
    display: block !important;
}

/* Top information bar */
.position-snipper-topbar {
    position: absolute !important;

    top: 18px !important;
    left: 50% !important;

    transform: translateX(-50%) !important;

    display: flex !important;
    align-items: center !important;
    gap: 16px !important;

    padding: 10px 14px !important;

    border-radius: 10px !important;

    background: rgba(25, 25, 25, 0.92) !important;
    color: #ffffff !important;

    box-sizing: border-box !important;

    pointer-events: none !important;
}

.position-snipper-title {
    font-size: 14px !important;
    font-weight: 700 !important;
    white-space: nowrap !important;
}

.position-snipper-hint {
    font-size: 12px !important;
    opacity: 0.75 !important;
    white-space: nowrap !important;
}

/* Cancel must remain clickable */
.position-snipper-cancel {
    pointer-events: auto !important;

    height: 32px !important;
    padding: 0 14px !important;

    border: 0 !important;
    border-radius: 7px !important;

    background: #7fbe45 !important;
    color: #ffffff !important;

    font-size: 12px !important;
    font-weight: 600 !important;

    cursor: pointer !important;
}

/* Selection rectangle */
.position-snipper-selection {
    position: fixed !important;

    display: block !important;

    border: 2px solid #7fbe45 !important;

    background: rgba(127, 190, 69, 0.08) !important;

    pointer-events: none !important;

    box-sizing: border-box !important;

    z-index: 100000 !important;
}

/* Respect the HTML hidden attribute */
.position-snipper-selection[hidden] {
    display: none !important;
}

/* Selection dimensions */
.position-snipper-size {
    position: absolute !important;

    top: -26px !important;
    left: 0 !important;

    padding: 4px 7px !important;

    border-radius: 4px !important;

    background: rgba(25, 25, 25, 0.9) !important;
    color: #ffffff !important;

    font-size: 11px !important;
    line-height: 1 !important;

    white-space: nowrap !important;
}

'''

p.write_text(s.rstrip() + css, encoding="cp1252")

print("SCANNER_OVERLAY_CSS_FIXED")
