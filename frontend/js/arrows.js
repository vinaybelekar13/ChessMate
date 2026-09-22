// ChessMate arrow system — one place that knows how an arrow looks and where it goes.
//
// Every arrow is described by a ROLE (what it MEANS), and the role decides colour,
// weight and stacking. That is what makes the board's markings a language instead of a
// pile of colours: green = a move that works, red = a move that fails, blue = a tactical
// relationship, and the user's own arrows keep their familiar right-drag colours.
//
//   best     the engine's best move                   green, firm
//   pv       further engine lines                     blue-grey, faint
//   correct  the right move in a training exercise    strong green
//   wrong    the move that was played and failed      red
//   motif    a tactical relationship (fork, pin...)   blue; `dashed` = the line behind
//   user     drawn by hand                            per-modifier colour (a.color)
//
// Geometry is in BOARD UNITS (the SVG's viewBox is 0..8 — one unit is one square), so
// shaft width, arrowhead size and the knight's elbow all scale with the board for free.
// Nothing here knows a pixel size. Arrows start at the centre of the origin square and
// the head lands on the centre of the target, on the final leg.

const NS = "http://www.w3.org/2000/svg";

export const ROLE = {
  wrong:   { color: "#e0392b", opacity: 0.88, shaft: 0.15, head: 0.42, half: 0.19, z: 0 },
  pv:      { color: "#4a8fd6", opacity: 0.55, shaft: 0.11, head: 0.36, half: 0.16, z: 1 },
  motif:   { color: "#2f86e0", opacity: 0.9,  shaft: 0.14, head: 0.40, half: 0.18, z: 2 },
  best:    { color: "#5aa02c", opacity: 0.92, shaft: 0.16, head: 0.42, half: 0.19, z: 3 },
  correct: { color: "#3f9f2a", opacity: 0.95, shaft: 0.17, head: 0.44, half: 0.2,  z: 4 },
  user:    { color: "#f7b34c", opacity: 0.9,  shaft: 0.15, head: 0.40, half: 0.18, z: 5 },
};

function sqCR(square, flip) {
  const file = square.charCodeAt(0) - 97, rank = +square[1];
  return { c: flip ? 7 - file : file, r: flip ? rank - 1 : 8 - rank };
}
const mk = (tag, attrs) => {
  const n = document.createElementNS(NS, tag);
  for (const k in attrs) n.setAttribute(k, attrs[k]);
  return n;
};

function drawArrow(svg, a, flip) {
  const role = ROLE[a.role] ? a.role : "user";
  const st = ROLE[role];
  const f = sqCR(a.from, flip), t = sqCR(a.to, flip);
  const x1 = f.c + 0.5, y1 = f.r + 0.5, x2 = t.c + 0.5, y2 = t.r + 0.5;
  const col = a.color || st.color;
  const op = a.opacity != null ? a.opacity : st.opacity;
  const { head, half: halfW, shaft } = st;

  // A knight's arrow turns a right angle — long leg first, then the short one into the
  // target — so it reads as a knight rather than as a bishop cutting across squares.
  const dc = t.c - f.c, dr = t.r - f.r;
  const isKnight = Math.abs(dc) + Math.abs(dr) === 3 && dc !== 0 && dr !== 0;
  const elbow = !isKnight ? null : Math.abs(dr) === 2 ? { x: x1, y: y2 } : { x: x2, y: y1 };

  const hx = elbow ? elbow.x : x1, hy = elbow ? elbow.y : y1;
  const ang = Math.atan2(y2 - hy, x2 - hx);
  const tipx = x2 - Math.cos(ang) * 0.08, tipy = y2 - Math.sin(ang) * 0.08;
  const bx = tipx - Math.cos(ang) * head, by = tipy - Math.sin(ang) * head;

  const pts = (elbow ? [[x1, y1], [elbow.x, elbow.y]] : [[x1, y1]]).concat([[bx, by]]);
  const line = mk("polyline", {
    points: pts.map((p) => p[0] + "," + p[1]).join(" "), fill: "none", stroke: col,
    "stroke-width": shaft, "stroke-linecap": a.dashed ? "butt" : "round", "stroke-linejoin": "round", opacity: op,
    "data-role": role,
  });
  if (a.dashed) line.setAttribute("stroke-dasharray", "0.22 0.15");
  svg.appendChild(line);

  const lx = bx + Math.cos(ang + Math.PI / 2) * halfW, ly = by + Math.sin(ang + Math.PI / 2) * halfW;
  const rx = bx - Math.cos(ang + Math.PI / 2) * halfW, ry = by - Math.sin(ang + Math.PI / 2) * halfW;
  svg.appendChild(mk("polygon", {
    points: tipx + "," + tipy + " " + lx + "," + ly + " " + rx + "," + ry,
    fill: col, opacity: op, "data-role": role,
  }));
}

/** Build the arrows layer (or null when there is nothing to draw). */
export function buildArrows(arrows = [], marks = [], flip = false) {
  if (!arrows.length && !marks.length) return null;
  const svg = document.createElementNS(NS, "svg");
  svg.setAttribute("class", "arrows");
  svg.setAttribute("viewBox", "0 0 8 8");
  svg.setAttribute("aria-hidden", "true");
  for (const m of marks) {
    const s = sqCR(m.square, flip);
    svg.appendChild(mk("circle", {
      cx: s.c + 0.5, cy: s.r + 0.5, r: 0.46, fill: "none", stroke: m.color || "#15781b",
      "stroke-width": 0.07, opacity: 0.9, "data-role": "user",
    }));
  }
  // Stack by meaning, and drop exact duplicates (an engine arrow under a motif arrow
  // for the same move would just thicken it).
  const seen = new Set();
  const ordered = arrows
    .map((a, i) => ({ a, i, z: (ROLE[a.role] || ROLE.user).z }))
    .sort((p, q) => p.z - q.z || p.i - q.i)
    .filter(({ a }) => { const k = (a.role || "user") + a.from + a.to + (a.color || ""); if (seen.has(k)) return false; seen.add(k); return true; });
  for (const { a } of ordered) drawArrow(svg, a, flip);
  return svg;
}

/** Replace ONLY the arrows layer of a board. The squares (and any drag in progress) are left alone,
 *  so live engine updates can repaint arrows many times a second without rebuilding the board. */
export function setArrows(boardEl, arrows, marks, flip) {
  const old = boardEl.querySelector(":scope > svg.arrows");
  if (old) old.remove();
  const svg = buildArrows(arrows, marks, flip);
  if (svg) boardEl.appendChild(svg);
}
