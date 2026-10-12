from pathlib import Path

p = Path("css/book-reader.css")
s = p.read_text(encoding="utf-8")

css = r'''

/* ============================================================
   SIDE TO MOVE TOGGLE
   ============================================================ */

.side-to-move-control {
    display: inline-flex;
    align-items: center;
    gap: 3px;
    padding: 3px;
    margin-left: 8px;
    border: 1px solid rgba(255, 255, 255, 0.12);
    border-radius: 10px;
    background: rgba(255, 255, 255, 0.05);
}

.side-to-move-button {
    border: 0;
    border-radius: 7px;
    padding: 7px 11px;
    background: transparent;
    color: rgba(255, 255, 255, 0.55);
    font-size: 12px;
    font-weight: 600;
    cursor: pointer;
    transition:
        background 0.18s ease,
        color 0.18s ease,
        transform 0.12s ease;
}

.side-to-move-button:hover {
    color: rgba(255, 255, 255, 0.9);
    background: rgba(255, 255, 255, 0.07);
}

.side-to-move-button.active {
    background: rgba(255, 255, 255, 0.14);
    color: #ffffff;
}

.side-to-move-button:active {
    transform: scale(0.96);
}

'''

if ".side-to-move-control" in s:
    print("SIDE_TO_MOVE_CSS_ALREADY_EXISTS")
else:
    p.write_text(s + css, encoding="utf-8")
    print("SIDE_TO_MOVE_CSS_ADDED")
