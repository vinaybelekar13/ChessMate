from pathlib import Path
import re

p = Path("css/book-reader.css")
s = p.read_text(encoding="cp1252").lstrip("\ufeff")

# Remove the previously added side-to-move CSS rules,
# regardless of the surrounding comment formatting.
patterns = [
    r'\.side-to-move-control\s*\{.*?\}\s*',
    r'\.side-to-move-label\s*\{.*?\}\s*',
    r'\.side-to-move-button\s*\{.*?\}\s*',
    r'\.side-to-move-button:hover\s*\{.*?\}\s*',
    r'\.side-to-move-button\.active\s*\{.*?\}\s*',
    r'\.side-to-move-button:active\s*\{.*?\}\s*',
]

for pattern in patterns:
    s = re.sub(pattern, "", s, flags=re.DOTALL)

# Remove any old toggle rules from a previous attempt.
patterns_toggle = [
    r'\.toggle\s*\{.*?\}\s*',
    r'\.toggle input\[type="checkbox"\]\s*\{.*?\}\s*',
    r'\.toggle label\s*\{.*?\}\s*',
    r'\.toggle label:before\s*\{.*?\}\s*',
    r'\.toggle label:after\s*\{.*?\}\s*',
    r'\.toggle input\[type="checkbox"\]:checked \+ label:before\s*\{.*?\}\s*',
    r'\.toggle input\[type="checkbox"\]:checked \+ label:after\s*\{.*?\}\s*',
]

for pattern in patterns_toggle:
    s = re.sub(pattern, "", s, flags=re.DOTALL)

css = r'''

/* ============================================================
   MINIMAL SIDE TO MOVE TOGGLE
   ============================================================ */

.side-to-move-control {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    margin-left: 6px;
    height: 30px;
}

.side-to-move-label {
    min-width: 34px;
    color: rgba(255, 255, 255, 0.72);
    font-size: 10px;
    font-weight: 600;
    text-align: right;
    user-select: none;
}

.toggle {
    position: relative;
    width: 52px;
    height: 24px;
    display: flex;
    align-items: center;
    box-sizing: border-box;
}

.toggle input[type="checkbox"] {
    position: absolute;
    inset: 0;
    z-index: 10;
    width: 100%;
    height: 100%;
    cursor: pointer;
    opacity: 0;
    margin: 0;
}

.toggle label {
    position: relative;
    display: flex;
    width: 52px;
    height: 24px;
    align-items: center;
    box-sizing: border-box;
}

.toggle label:before {
    content: '';
    background: #bbb;
    width: 52px;
    height: 24px;
    display: inline-block;
    position: relative;
    border-radius: 12px;
    box-shadow:
        inset 0 1px 1px rgb(0 0 0 / 20%),
        inset 0 2px 5px rgb(0 0 0 / 25%),
        0 0 8px rgb(255 255 255 / 20%);
    box-sizing: border-box;
    transition: .3s cubic-bezier(0.52, -0.41, 0.55, 1.46);
}

.toggle label:after {
    content: '';
    position: absolute;
    top: 3px;
    left: 3px;
    width: 18px;
    height: 18px;
    border-radius: 50%;
    z-index: 2;
    box-sizing: border-box;
    background: #5b5656;
    border-left: 1px solid #756f6f;
    border-bottom: 1px solid #756f6f;
    box-shadow:
        0 2px 1px #343131,
        0 2px 5px rgb(52 49 49 / 50%),
        0 2px 10px rgb(0 0 0 / 25%);
    transition: .3s cubic-bezier(0.52, -0.41, 0.55, 1.46);
}

.toggle input[type="checkbox"]:checked + label:before {
    background: #c0e7e3;
}

.toggle input[type="checkbox"]:checked + label:after {
    background: #21bf73;
    border-left: none;
    border-right: 1px solid #37dc8d;
    border-bottom: 1px solid #37dc8d;
    box-shadow:
        0 2px 1px #167e4c,
        0 2px 5px rgb(22 126 76 / 50%),
        0 2px 10px rgb(0 0 0 / 25%);
    left: 31px;
}

'''

p.write_text(s.rstrip() + css, encoding="cp1252")

print("SIDE_TO_MOVE_CSS_REPLACED")
