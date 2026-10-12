from pathlib import Path

p = Path("js/book-reader.js")
s = p.read_text(encoding="cp1252")

# Make the binding function safe against duplicate listeners.
old = '''function bindSideToMoveToggle() {
    const toggle =
        document.getElementById("sideToMoveToggle");

    if (!toggle) {
        console.warn(
            "[ChessMate] Side-to-move toggle not found."
        );
        return;
    }

    toggle.addEventListener(
        "change",
        () => {
            setSideToMove(
                toggle.checked
                    ? "b"
                    : "w"
            );
        }
    );

    updateSideToMoveToggle();
}'''

new = '''function bindSideToMoveToggle() {
    const toggle =
        document.getElementById("sideToMoveToggle");

    if (!toggle) {
        console.warn(
            "[ChessMate] Side-to-move toggle not found."
        );
        return;
    }

    if (toggle.dataset.bound === "true") {
        updateSideToMoveToggle();
        return;
    }

    toggle.addEventListener(
        "change",
        () => {
            setSideToMove(
                toggle.checked
                    ? "b"
                    : "w"
            );
        }
    );

    toggle.dataset.bound = "true";

    updateSideToMoveToggle();
}'''

if old not in s:
    raise SystemExit("bindSideToMoveToggle BLOCK NOT FOUND")

s = s.replace(old, new, 1)


# Replace the old DOM-ready-only initialization with
# an initialization that works whether the DOM is already ready or not.
old_init = '''if (document.readyState === "loading") {
    document.addEventListener(
        "DOMContentLoaded",
        () => {
            bindPositionScannerButton();
            bindSideToMoveToggle();
        }
    );
}'''

new_init = '''function initializeChessMateControls() {
    bindPositionScannerButton();
    bindSideToMoveToggle();
}


if (document.readyState === "loading") {
    document.addEventListener(
        "DOMContentLoaded",
        initializeChessMateControls,
        { once: true }
    );
} else {
    initializeChessMateControls();
}'''

if old_init not in s:
    raise SystemExit("DOM INITIALIZATION BLOCK NOT FOUND")

s = s.replace(old_init, new_init, 1)

p.write_text(s, encoding="cp1252")

print("SIDE_TO_MOVE_FUNCTIONAL_FIX_APPLIED")
