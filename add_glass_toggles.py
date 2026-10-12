from pathlib import Path

p = Path("css/book-reader.css")

data = p.read_bytes()
s = data.decode("latin-1")

if "CHESSMATE MINIMAL GLASS TOGGLES" in s:
    print("GLASS_TOGGLE_CSS_ALREADY_ADDED")
    raise SystemExit

css = r'''

/* ============================================================
   CHESSMATE MINIMAL GLASS TOGGLES
   White/Black + Magnus
   ============================================================ */

/* Shared toggle sizing */
#sideToMoveToggle + .toggle,
#magnusControl #magnusToggle + .toggle {

    position: relative !important;

    width: 42px !important;
    height: 22px !important;

    flex: 0 0 42px !important;

    display: inline-flex !important;
    align-items: center !important;

    border-radius: 999px !important;

    cursor: pointer !important;

    background:
        linear-gradient(
            180deg,
            rgba(255,255,255,.075),
            rgba(255,255,255,.025)
        ) !important;

    border:
        1px solid rgba(255,255,255,.16) !important;

    box-shadow:
        inset 0 1px 0 rgba(255,255,255,.10),
        inset 0 -1px 0 rgba(0,0,0,.20),
        0 2px 8px rgba(0,0,0,.22) !important;

    backdrop-filter: blur(10px) saturate(120%) !important;
    -webkit-backdrop-filter: blur(10px) saturate(120%) !important;

    transition:
        background .22s ease,
        border-color .22s ease,
        box-shadow .22s ease,
        transform .14s ease !important;
}


/* Remove old decorative switch elements */
#sideToMoveToggle + .toggle::before,
#sideToMoveToggle + .toggle::after,
#magnusControl #magnusToggle + .toggle::before,
#magnusControl #magnusToggle + .toggle::after {

    display: none !important;
    content: none !important;
}


/* Shared glass knob */
#sideToMoveToggle + .toggle .toggle__handler,
#magnusControl #magnusToggle + .toggle .toggle__handler {

    position: absolute !important;

    top: 3px !important;
    left: 3px !important;

    width: 14px !important;
    height: 14px !important;

    margin: 0 !important;

    border-radius: 50% !important;

    background:
        linear-gradient(
            145deg,
            rgba(255,255,255,.95),
            rgba(220,220,220,.72)
        ) !important;

    border:
        1px solid rgba(255,255,255,.72) !important;

    box-shadow:
        0 2px 5px rgba(0,0,0,.35),
        inset 0 1px 1px rgba(255,255,255,.65) !important;

    transform: translateX(0) !important;

    transition:
        transform .24s cubic-bezier(.22,.8,.25,1),
        background .2s ease,
        box-shadow .2s ease !important;

    will-change: transform !important;
}


/* Remove old moon/star/crater graphics */
#sideToMoveToggle + .toggle .crater,
#sideToMoveToggle + .toggle .star,
#magnusControl #magnusToggle + .toggle .crater,
#magnusControl #magnusToggle + .toggle .star {

    display: none !important;
}


/* ============================================================
   ON STATE
   ============================================================ */

#sideToMoveToggle:checked + .toggle,
#magnusControl #magnusToggle:checked + .toggle {

    background:
        linear-gradient(
            180deg,
            rgba(139,210,76,.30),
            rgba(139,210,76,.13)
        ) !important;

    border-color:
        rgba(139,210,76,.58) !important;

    box-shadow:
        inset 0 1px 0 rgba(255,255,255,.16),
        0 0 0 1px rgba(139,210,76,.08),
        0 3px 12px rgba(139,210,76,.16) !important;
}


#sideToMoveToggle:checked + .toggle .toggle__handler,
#magnusControl #magnusToggle:checked + .toggle .toggle__handler {

    transform: translateX(20px) !important;

    background:
        linear-gradient(
            145deg,
            #ffffff,
            #d9f5bd
        ) !important;

    border-color:
        rgba(190,235,150,.95) !important;

    box-shadow:
        0 2px 6px rgba(0,0,0,.32),
        0 0 8px rgba(139,210,76,.28),
        inset 0 1px 1px rgba(255,255,255,.8) !important;
}


/* ============================================================
   OFF STATE
   ============================================================ */

#sideToMoveToggle:not(:checked) + .toggle,
#magnusControl #magnusToggle:not(:checked) + .toggle {

    opacity: .78 !important;
}


#sideToMoveToggle:not(:checked) + .toggle .toggle__handler,
#magnusControl #magnusToggle:not(:checked) + .toggle .toggle__handler {

    background:
        linear-gradient(
            145deg,
            rgba(255,255,255,.82),
            rgba(180,180,180,.62)
        ) !important;
}


/* ============================================================
   HOVER
   ============================================================ */

#sideToMoveToggle + .toggle:hover,
#magnusControl #magnusToggle + .toggle:hover {

    transform: translateY(-1px) !important;

    border-color:
        rgba(255,255,255,.30) !important;

    box-shadow:
        inset 0 1px 0 rgba(255,255,255,.12),
        0 4px 14px rgba(0,0,0,.28) !important;
}


#sideToMoveToggle:checked + .toggle:hover,
#magnusControl #magnusToggle:checked + .toggle:hover {

    border-color:
        rgba(139,210,76,.72) !important;

    box-shadow:
        0 0 0 1px rgba(139,210,76,.10),
        0 4px 16px rgba(139,210,76,.18) !important;
}


/* ============================================================
   PRESS ANIMATION
   ============================================================ */

#sideToMoveToggle + .toggle:active,
#magnusControl #magnusToggle + .toggle:active {

    transform: scale(.94) !important;
}


#sideToMoveToggle + .toggle:active .toggle__handler,
#magnusControl #magnusToggle + .toggle:active .toggle__handler {

    transform: translateX(0) scale(.92) !important;
}


#sideToMoveToggle:checked + .toggle:active .toggle__handler,
#magnusControl #magnusToggle:checked + .toggle:active .toggle__handler {

    transform: translateX(20px) scale(.92) !important;
}


/* ============================================================
   FOCUS
   ============================================================ */

#sideToMoveToggle:focus-visible + .toggle,
#magnusControl #magnusToggle:focus-visible + .toggle {

    outline: 2px solid rgba(139,210,76,.55) !important;
    outline-offset: 3px !important;
}


/* ============================================================
   LABELS
   ============================================================ */

.side-to-move-control,
#magnusControl {

    display: inline-flex !important;

    align-items: center !important;

    gap: 8px !important;
}


#sideToMoveLabel,
.magnus-title {

    font-size: 12px !important;

    font-weight: 600 !important;

    letter-spacing: .01em !important;

    color:
        rgba(255,255,255,.78) !important;

    white-space: nowrap !important;

    transition:
        color .2s ease,
        opacity .2s ease !important;
}


/* Active Magnus label */
#magnusControl #magnusToggle:checked ~ .toggle,
#magnusControl #magnusToggle:checked ~ .magnus-title {

    color: rgba(255,255,255,.94) !important;
}


/* Active side-to-move label */
#sideToMoveToggle:checked ~ #sideToMoveLabel {

    color: rgba(255,255,255,.94) !important;
}


/* ============================================================
   COMPACT ALIGNMENT INSIDE BOARD ACTIONS
   ============================================================ */

.analysis-panel .chessmate-board-actions {

    gap: 8px !important;
}


.analysis-panel .chessmate-board-actions .magnus-control,
.analysis-panel .chessmate-board-actions .side-to-move-control {

    min-height: 32px !important;

    padding:
        0 3px !important;

    border-radius: 10px !important;

    transition:
        background .2s ease !important;
}


.analysis-panel .chessmate-board-actions .magnus-control:hover,
.analysis-panel .chessmate-board-actions .side-to-move-control:hover {

    background:
        rgba(255,255,255,.035) !important;
}
'''

p.write_bytes((s + css).encode("latin-1"))

print("MINIMAL_GLASS_TOGGLES_ADDED")
