// The workspace must adapt — not merely survive — to browser zoom and window size.
//
// A browser zoom level changes nothing except the CSS viewport: at 125% on a 1440x900 window the page
// lays out in 1152x720 CSS pixels. So "zoom 67%..150% x window 1920x1080..1280x720" is exactly a
// matrix of CSS viewports (window / zoom), and that is what is set here. For each one we measure the
// real layout and check the properties the design promises, rather than comparing screenshots.
import { suite, open, review } from "./lib/harness.mjs";

const t = suite("workspace");
const { browser, page, errors } = await open({ viewport: { width: 1440, height: 900 } });
await page.click("#loadSample");
await page.waitForTimeout(300);
await page.selectOption("#depthSel", "12");
await review(page);
await page.waitForTimeout(400);

const WINDOWS = [[1920, 1080], [1600, 900], [1440, 900], [1366, 768], [1280, 720]];
const ZOOMS = [67, 80, 90, 100, 110, 125, 150];

const measure = () => page.evaluate(() => {
  const R = (sel) => { const e = document.querySelector(sel); if (!e) return null; const r = e.getBoundingClientRect(); return { l: r.left, t: r.top, r: r.right, b: r.bottom, w: r.width, h: r.height }; };
  const cs = (sel, p) => getComputedStyle(document.querySelector(sel))[p];
  const arrow = document.querySelector("#board svg.arrows");
  return {
    vw: innerWidth, vh: innerHeight,
    overflowX: document.documentElement.scrollWidth - document.documentElement.clientWidth,
    board: R("#board"), card: R(".boardcard"), mid: R(".midcol"), coach: R(".rightcol"), grid: R("#workspace"),
    movelist: R("#movelist"), lower: R("#lower"), controls: R(".controls"),
    svg: arrow ? (() => { const r = arrow.getBoundingClientRect(); return { w: r.width, vb: arrow.getAttribute("viewBox") }; })() : null,
    san: parseFloat(cs(".mv .san", "fontSize")), rootFs: parseFloat(getComputedStyle(document.documentElement).fontSize),
    innerOverflow: [".midcol", ".rightcol", ".movescard"].map((s) => { const e = document.querySelector(s); return e.scrollWidth - e.clientWidth; }),
  };
});

const problems = [];
const rows = [];
for (const [ww, wh] of WINDOWS) {
  for (const z of ZOOMS) {
    const vw = Math.round(ww / (z / 100)), vh = Math.round(wh / (z / 100));
    await page.setViewportSize({ width: vw, height: vh });
    await page.waitForTimeout(120);
    const m = await measure();
    const tag = ww + "x" + wh + " @" + z + "% (" + vw + "x" + vh + " css)";
    const bad = (why) => problems.push(tag + ": " + why);
    const desktop = vw >= 700;      // board and analysis side by side
    const three = vw >= 1000;       // ...and the coach beside them too (below 1000 it is a row underneath)

    if (m.overflowX > 1) bad("horizontal overflow " + m.overflowX + "px");
    if (Math.abs(m.board.w - m.board.h) > 1) bad("board not square " + m.board.w.toFixed(1) + "x" + m.board.h.toFixed(1));
    if (m.svg && (Math.abs(m.svg.w - m.board.w) > 1 || m.svg.vb !== "0 0 8 8")) bad("arrow layer does not track the board");
    if (m.innerOverflow.some((o) => o > 1)) bad("a column overflows sideways " + m.innerOverflow.join(","));
    if (m.san < 13) bad("move text is " + m.san + "px");
    if (m.movelist.r > vw + 1 || m.movelist.l < -1) bad("move list off screen");

    if (desktop) {
      // The primary workspace fits the viewport (the board and its controls, at least), unless the
      // window is so short that the board's own minimum size wins.
      const minBoard = 17 * m.rootFs;
      if (m.card.b > vh + 1 && m.board.w > minBoard + 2) bad("board card runs off the bottom (" + Math.round(m.card.b) + " > " + vh + ")");
      // The analysis (moves + engine) is always beside the board. The coach is beside it too on a normal
      // desktop; on a medium window it is a full-width row directly underneath, never stranded further away.
      if (m.mid.l < m.board.r - 1) bad("analysis is not beside the board");
      if (three && m.coach.l < m.board.r - 1) bad("coach is not beside the board");
      if (!three && (m.coach.t < m.card.b - 2 || m.coach.t - m.card.b > 40)) bad("coach row is not directly under the workspace (" + Math.round(m.coach.t - m.card.b) + "px)");
      // Nothing stranded: the lower row starts right where the workspace ends.
      if (m.lower.t - m.grid.b > 40) bad("gap of " + Math.round(m.lower.t - m.grid.b) + "px between workspace and lower row");
    }
    if (three) {
      // Three columns, side by side, not overlapping, sharing a top edge.
      if (!(m.board.r <= m.mid.l + 1 && m.mid.r <= m.coach.l + 1)) bad("columns overlap or are out of order");
      if (Math.abs(m.mid.t - m.coach.t) > 2 || Math.abs(m.card.t - m.mid.t) > 2) bad("columns do not share a top edge");
      // The board is the visual anchor: the biggest column, and a real share of the width.
      if (m.card.w * m.card.h < m.mid.w * m.mid.h * 0.9) bad("board is not the largest area");
      if (m.board.w < m.grid.w * 0.30) bad("board is only " + Math.round(m.board.w / m.grid.w * 100) + "% of the workspace width");
      // ...and it is as big as it can be: it runs the full height of the workspace, unless the other two
      // columns are already down to their minimum widths (then it is width-limited, correctly).
      const gap = m.grid.b - m.card.b;
      if (gap > 4 && m.mid.w > 20.5 * m.rootFs) bad("blank " + Math.round(gap) + "px under the board although the columns beside it have room to give");
    }
    rows.push(tag + " -> board " + Math.round(m.board.w) + "px, cols " + (three ? "3" : desktop ? "2" : "1"));
  }
}
t.ok("no layout problems across " + WINDOWS.length * ZOOMS.length + " window x zoom combinations",
  problems.length === 0, problems.length ? problems.slice(0, 8).join("  ||  ") : "all 35 coherent");
console.log(rows.filter((_, i) => i % 7 === 3).join("\n"));   // the 100% row of each window, for the record

// A real phone, portrait and landscape: one column, no sideways scroll, a board that is width-limited.
for (const [w, h, label] of [[390, 844, "phone portrait"], [844, 390, "phone landscape"], [768, 1024, "tablet portrait"]]) {
  await page.setViewportSize({ width: w, height: h });
  await page.waitForTimeout(150);
  const m = await measure();
  t.ok(label + ": no sideways scroll, square board that fits the width",
    m.overflowX <= 1 && Math.abs(m.board.w - m.board.h) <= 1 && m.board.r <= w + 1,
    "overflowX=" + m.overflowX + " board=" + Math.round(m.board.w) + " of " + w);
}

// Arrows scale with the board: the same arrow, drawn on a small board and a big one, has the same
// proportions (its stroke is a fixed fraction of the board, because it is measured in board units).
await page.setViewportSize({ width: 1600, height: 900 });
await page.waitForTimeout(150);
const ratio = async () => page.evaluate(() => {
  const line = document.querySelector('#board svg.arrows polyline');
  if (!line) return null;
  const board = document.getElementById("board").getBoundingClientRect().width;
  const sw = parseFloat(line.getAttribute("stroke-width")) * (board / 8);   // rendered px of a viewBox unit
  return { board, strokePx: sw, fraction: sw / board };
});
await page.evaluate(() => document.querySelector('.mv[data-ply="1"]').click());
await page.waitForTimeout(600);           // engine arrows arrive
const big = await ratio();
await page.setViewportSize({ width: 1100, height: 640 });
await page.waitForTimeout(200);
const small = await ratio();
t.ok("arrow thickness stays proportional to the board across sizes",
  !!big && !!small && big.board > small.board + 20 && Math.abs(big.fraction - small.fraction) < 1e-6,
  big && small ? "board " + Math.round(big.board) + "px -> " + Math.round(small.board) + "px, stroke " + big.strokePx.toFixed(1) + "px -> " + small.strokePx.toFixed(1) + "px" : "no arrows drawn");

t.ok("no page errors during the whole matrix", errors.length === 0, errors.slice(0, 2).join(" || ") || "clean");
await browser.close();
t.finish();
