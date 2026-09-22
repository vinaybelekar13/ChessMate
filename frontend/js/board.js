// Renders a chess position from a FEN into a grid of squares, with last-move
// highlight, a classification badge, coordinates, and optional click-to-move.
import { CLASSES } from "./review.js?v=36";
import { glyphSvg } from "./glyphs.js?v=36";
import { setArrows } from "./arrows.js?v=37";
export { setArrows };

// cburnett SVG piece set (GPL). Path is relative to the HTML document base.
const PIECES = "vendor/pieces/cburnett/";

export function renderBoard(el, fen, opts = {}) {
  const { flip = false, lastMove = null, badge = null, hlClass = null, selected = null, targets = [], arrows = [],
    marks = [], onSquareClick = null, onSquareDown = null,
    check = null,        // square of a king in check
    mate = false,        // ...and it is checkmate
    overlay = [],        // [{ sq, role }] tactical / training highlights: attacker | target | line | correct | wrong | hint
  } = opts;
  const stm = fen.split(" ")[1] || "w";
  const rowsFen = fen.split(" ")[0].split("/");
  const grid = rowsFen.map((fr) => {
    const arr = [];
    for (const ch of fr) {
      if (/\d/.test(ch)) for (let i = 0; i < +ch; i++) arr.push(null);
      else arr.push(ch);
    }
    return arr;
  });

  el.innerHTML = "";
  for (let dr = 0; dr < 8; dr++) {
    for (let dc = 0; dc < 8; dc++) {
      const rr = flip ? 7 - dr : dr; // 0 = rank 8
      const cc = flip ? 7 - dc : dc; // 0 = file a
      const rankNum = 8 - rr;
      const file = "abcdefgh"[cc];
      const name = file + rankNum;
      const piece = grid[rr][cc];
      const light = (rr + cc) % 2 === 0;

      const sq = document.createElement("div");
      sq.className = "sq " + (light ? "l" : "d");
      sq.dataset.sq = name;
      if (lastMove && (name === lastMove.from || name === lastMove.to)) {
        sq.classList.add("hl");
        if (hlClass && CLASSES[hlClass]) {
          sq.classList.add("clshl");
          sq.style.setProperty("--hl-col", "var(" + CLASSES[hlClass].v + ")");
        }
      }
      if (selected === name) sq.classList.add("sel");
      // A questionable move gets a quiet warning ring on its destination (one soft pulse,
      // not a flashing board). Mistakes and blunders are stronger than inaccuracies.
      if (lastMove && name === lastMove.to && hlClass && ["inaccuracy", "mistake", "blunder"].includes(hlClass)) {
        sq.classList.add("warn", "warn-" + hlClass);
      }
      if (check && name === check) sq.classList.add(mate ? "mate" : "check");
      for (const o of overlay) if (o.sq === name) sq.classList.add("tg-" + o.role);

      if (piece) {
        const isWhite = piece === piece.toUpperCase();
        // Pieces of the side to move can be picked up and dragged.
        if (isWhite === (stm === "w")) sq.classList.add("grabbable");
        const pc = document.createElement("div");
        pc.className = "pc";
        pc.style.backgroundImage = "url('" + PIECES + (isWhite ? "w" : "b") + piece.toUpperCase() + ".svg')";
        sq.appendChild(pc);
      }
      if (targets.includes(name)) {
        const dot = document.createElement("div");
        dot.className = "target" + (piece ? " cap" : "");
        sq.appendChild(dot);
      }
      if (badge && name === badge.square) {
        const b = document.createElement("div");
        b.className = "badge";
        b.style.background = "var(" + CLASSES[badge.cls].v + ")";
        b.innerHTML = glyphSvg(badge.cls);   // SVG mark: centred by geometry, not by font luck
        b.dataset.g = CLASSES[badge.cls].g;
        sq.appendChild(b);
      }
      if (mate && check && name === check) {
        const mb = document.createElement("div");
        mb.className = "badge matebadge"; mb.textContent = "#"; mb.setAttribute("title", "Checkmate");
        sq.appendChild(mb);
      }
      if (dc === 0) {
        const c = document.createElement("div");
        c.className = "coord r"; c.textContent = rankNum; sq.appendChild(c);
      }
      if (dr === 7) {
        const c = document.createElement("div");
        c.className = "coord f"; c.textContent = file; sq.appendChild(c);
      }
      if (onSquareClick) sq.addEventListener("click", () => onSquareClick(name));
      if (onSquareDown) sq.addEventListener("pointerdown", (e) => onSquareDown(name, e));
      el.appendChild(sq);
    }
  }

  // Move arrows and square marks: drawn by js/arrows.js in board units, so they scale with the board.
  setArrows(el, arrows, marks, flip);
}
