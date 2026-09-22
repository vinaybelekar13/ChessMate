// ChessMate - tactic pattern detection (fork, double attack, pin, skewer,
// discovered attack), computed from the ACTUAL position.
//
// Nothing here is hard-coded to a square. Given the position before a move, the
// position after it and the move's from/to squares, this reads the board and reports
// which named tactic the move creates, which of the mover's pieces make it, and which
// enemy pieces are its targets — so a UI can draw arrows to the real pieces and a
// coach can say "Nb4 attacks the queen on d3 and the rook on a2" and be right.
//
// Same philosophy as js/motifs.js (docs/NOTES.md, "Move motifs"): decided statically
// from the position, never from the engine's choice of reply, and precision over
// recall. A fork that the opponent can simply capture the forking piece out of is not
// a fork; a "pin" by a piece that hangs is not offered. Silence beats a wrong name.
//
// Pure functions on FEN strings. No DOM, no engine, no chess.js — the board geometry
// is small enough to own outright, which keeps this usable from the UI, the domain
// layer, and plain `node` tests alike.

const FILES = "abcdefgh";
const VALUE = { p: 1, n: 3, b: 3, r: 5, q: 9, k: 100 };
export const PIECE_NAME = { p: "pawn", n: "knight", b: "bishop", r: "rook", q: "queen", k: "king" };
const LETTER = { n: "N", b: "B", r: "R", q: "Q", k: "K", p: "" };

const KNIGHT_STEPS = [[-2, -1], [-2, 1], [-1, -2], [-1, 2], [1, -2], [1, 2], [2, -1], [2, 1]];
const KING_STEPS = [[-1, -1], [-1, 0], [-1, 1], [0, -1], [0, 1], [1, -1], [1, 0], [1, 1]];
const DIAG = [[-1, -1], [-1, 1], [1, -1], [1, 1]];
const ORTH = [[-1, 0], [1, 0], [0, -1], [0, 1]];
const dirsFor = (t) => (t === "b" ? DIAG : t === "r" ? ORTH : t === "q" ? DIAG.concat(ORTH) : []);

// ---------- board ----------
// board[r][c], r = 0 is rank 8, c = 0 is file a. Cell: { t: "n", col: "w" } or null.
// (The colour key is `col`, not `c`: hits carry a column `c` too, and a spread of one
// over the other silently turned squares into "NaN".)
function parseBoard(fen) {
  const rows = String(fen).split(" ")[0].split("/");
  if (rows.length !== 8) return null;
  const board = [];
  for (const row of rows) {
    const line = [];
    for (const ch of row) {
      if (/\d/.test(ch)) for (let i = 0; i < +ch; i++) line.push(null);
      else line.push({ t: ch.toLowerCase(), col: ch === ch.toUpperCase() ? "w" : "b" });
    }
    if (line.length !== 8) return null;
    board.push(line);
  }
  return board;
}
const name = (r, c) => FILES[c] + (8 - r);
const rc = (sq) => [8 - +sq[1], sq.charCodeAt(0) - 97];
const inb = (r, c) => r >= 0 && r < 8 && c >= 0 && c < 8;
const other = (c) => (c === "w" ? "b" : "w");

// Squares a piece attacks — "attack" in the chess sense: every square it could capture
// on, and every square of its own colour it defends. Sliders stop at (and include) the
// first piece they meet. Pins are deliberately ignored: a pinned piece still attacks.
function attacksFrom(board, r, c) {
  const p = board[r][c];
  if (!p) return [];
  const out = [];
  const step = (dr, dc) => { const rr = r + dr, cc = c + dc; if (inb(rr, cc)) out.push([rr, cc]); };
  if (p.t === "n") KNIGHT_STEPS.forEach(([dr, dc]) => step(dr, dc));
  else if (p.t === "k") KING_STEPS.forEach(([dr, dc]) => step(dr, dc));
  else if (p.t === "p") { const d = p.col === "w" ? -1 : 1; step(d, -1); step(d, 1); }
  else {
    for (const [dr, dc] of dirsFor(p.t)) {
      let rr = r + dr, cc = c + dc;
      while (inb(rr, cc)) {
        out.push([rr, cc]);
        if (board[rr][cc]) break;
        rr += dr; cc += dc;
      }
    }
  }
  return out;
}

// Every piece of `color` that attacks (r,c). Returns [{ r, c, t }].
function attackersOf(board, r, c, color) {
  const res = [];
  for (let rr = 0; rr < 8; rr++) {
    for (let cc = 0; cc < 8; cc++) {
      const p = board[rr][cc];
      if (!p || p.col !== color || (rr === r && cc === c)) continue;
      if (attacksFrom(board, rr, cc).some(([a, b]) => a === r && b === c)) res.push({ r: rr, c: cc, t: p.t });
    }
  }
  return res;
}

// First occupied square along a ray, and the first occupied square BEYOND it.
function rayHits(board, r, c, dr, dc) {
  const hits = [];
  let rr = r + dr, cc = c + dc;
  while (inb(rr, cc) && hits.length < 2) {
    if (board[rr][cc]) hits.push({ r: rr, c: cc, ...board[rr][cc] });
    rr += dr; cc += dc;
  }
  return hits;
}

// ---------- judgement helpers ----------

// Could the enemy simply take the piece on (r,c)? True when the capture is at least an
// even trade for them: the piece is undefended, or something no more valuable can take
// it. The king can only take a piece that nothing defends. This is what kills the
// commonest false fork — a queen "forking" from a square the enemy queen just takes.
function refutable(board, r, c, us) {
  const me = board[r][c];
  const them = other(us);
  const support = attackersOf(board, r, c, us).length;
  return attackersOf(board, r, c, them).some((e) =>
    e.t === "k" ? support === 0 : (support === 0 || VALUE[e.t] <= VALUE[me.t]));
}

// Is `target` (an enemy non-king piece at r,c) genuinely winnable by the piece `att`
// (at ar,ac)? Free (undefended) or worth more than the attacker (a trade up). If our
// side also supports the square, the enemy king cannot recapture there.
function winnable(board, r, c, att, us) {
  const them = other(us);
  const target = board[r][c];
  const supported = attackersOf(board, r, c, us).some((a) => !(a.r === att.r && a.c === att.c));
  const defenders = attackersOf(board, r, c, them).filter((d) => !(supported && d.t === "k"));
  return defenders.length === 0 || VALUE[target.t] > VALUE[att.t];
}

const nameOf = (t) => PIECE_NAME[t] || "piece";
const onSq = (t, sq) => "the " + nameOf(t) + " on " + sq;
function list(items) {
  if (items.length <= 1) return items.join("");
  return items.slice(0, -1).join(", ") + " and " + items[items.length - 1];
}

// ---------- the detectors ----------
// Each returns a pattern object or null. `M` = { r, c, t, sq } is the piece that moved,
// standing on its destination in the AFTER board.

// Enemy pieces the mover attacks that are worth going after: the king (check), or a
// non-pawn piece that is free or worth more than the attacker.
function winnableTargets(board, M, us) {
  const them = other(us);
  const out = [];
  for (const [r, c] of attacksFrom(board, M.r, M.c)) {
    const p = board[r][c];
    if (!p || p.col !== them) continue;
    if (p.t === "k") { out.push({ r, c, t: "k", sq: name(r, c), check: true }); continue; }
    if (VALUE[p.t] < 3) continue;
    if (winnable(board, r, c, M, us)) out.push({ r, c, t: p.t, sq: name(r, c) });
  }
  return out.sort((a, b) => VALUE[b.t] - VALUE[a.t]);
}

function detectFork(before, after, M, from, us, san) {
  if (refutable(after, M.r, M.c, us)) return null;
  const now = winnableTargets(after, M, us);
  if (now.length < 2) return null;
  // The move must ADD to what the piece already threatened from where it stood, or
  // it isn't the move that made the fork.
  const [fr, fc] = rc(from);
  const wasThere = new Set();
  if (before[fr][fc]) {
    const prior = winnableTargets(before, { ...before[fr][fc], r: fr, c: fc }, us);
    prior.forEach((t) => wasThere.add(t.sq));
  }
  if (now.every((t) => wasThere.has(t.sq))) return null;
  const targets = now.slice(0, 3);
  const hasKing = targets.some((t) => t.t === "k");
  const kind = M.t === "n" || M.t === "p" || hasKing ? "fork" : "double-attack";
  const names = targets.map((t) => onSq(t.t, t.sq));
  const text = hasKing
    ? (san || "The move") + " gives check and attacks " + list(names.filter((_, i) => targets[i].t !== "k")) + "."
    : (san || "The move") + " attacks " + list(names) + ".";
  return {
    kind,
    label: kind === "fork" ? "FORK" : "DOUBLE ATTACK",
    check: hasKing,
    attacker: { sq: M.sq, t: M.t },
    targets: targets.map((t) => ({ sq: t.sq, t: t.t, role: "target" })),
    arrows: targets.map((t) => ({ from: M.sq, to: t.sq })),
    text,
    idea: kind === "fork"
      ? "One piece attacks two things at once, and the opponent can only deal with one of them."
      : "A single move creates two threats, and the opponent can only meet one of them.",
  };
}

// A slider whose line runs through TWO enemy pieces: a pin if the one behind is worth
// more (the front piece is stuck shielding it), a skewer if the one in front is worth
// more (it must step aside and expose the one behind).
function detectLine(before, after, M, from, us, san) {
  if (!"brq".includes(M.t)) return null;
  const them = other(us);
  // Never call it a tactic if the mover just hangs.
  const hanging = attackersOf(after, M.r, M.c, them).length > 0 && attackersOf(after, M.r, M.c, us).length === 0;
  if (hanging) return null;
  const [fr, fc] = rc(from);
  const results = [];
  for (const [dr, dc] of dirsFor(M.t)) {
    const [f1, f2] = rayHits(after, M.r, M.c, dr, dc);
    if (!f1 || !f2 || f1.col !== them || f2.col !== them) continue;
    // Was this same line already held from the origin square? Then this move didn't make it.
    if (before[fr][fc] && dirsFor(before[fr][fc].t).some(([a, b]) => a === dr && b === dc)) {
      const prior = rayHits(before, fr, fc, dr, dc);
      if (prior[0] && prior[1] && prior[0].r === f1.r && prior[0].c === f1.c && prior[1].r === f2.r && prior[1].c === f2.c) continue;
    }
    const a1 = { sq: name(f1.r, f1.c), t: f1.t }, a2 = { sq: name(f2.r, f2.c), t: f2.t };
    const v1 = VALUE[f1.t], v2 = VALUE[f2.t];
    if (v2 > v1 && (f2.t === "k" || v2 >= 5)) {
      const absolute = f2.t === "k";
      results.push({
        kind: "pin",
        label: absolute ? "PIN" : "PIN",
        absolute,
        check: false,
        attacker: { sq: M.sq, t: M.t },
        targets: [{ ...a1, role: "pinned" }, { ...a2, role: "behind" }],
        arrows: [{ from: M.sq, to: a1.sq }, { from: a1.sq, to: a2.sq, dashed: true }],
        text: (san || "The move") + " pins " + onSq(a1.t, a1.sq) + " to " + onSq(a2.t, a2.sq) +
          (absolute ? " — it can't legally move." : " — if it moves, the " + nameOf(a2.t) + " is lost."),
        idea: "A pinned piece can't move without exposing the more valuable piece behind it.",
        _weight: v2,
      });
    } else if (v1 > v2 && v2 >= 3) {
      // the piece behind must actually be there for the taking
      if (!(winnable(after, f2.r, f2.c, M, us) || f1.t === "k")) continue;
      results.push({
        kind: "skewer",
        label: "SKEWER",
        check: f1.t === "k",
        attacker: { sq: M.sq, t: M.t },
        targets: [{ ...a1, role: "front" }, { ...a2, role: "behind" }],
        arrows: [{ from: M.sq, to: a1.sq }, { from: a1.sq, to: a2.sq, dashed: true }],
        text: (san || "The move") + " skewers " + onSq(a1.t, a1.sq) + " — once it moves, " +
          onSq(a2.t, a2.sq) + " is attacked" + (winnable(after, f2.r, f2.c, M, us) ? " and falls." : "."),
        idea: "A skewer attacks a valuable piece that has to move, exposing what stands behind it.",
        _weight: v1 + v2,
      });
    }
  }
  results.sort((a, b) => b._weight - a._weight);
  return results;
}

// The moved piece stood between one of our sliders and an enemy piece, and now it's gone.
function detectDiscovered(before, after, M, from, us, san) {
  const [fr, fc] = rc(from);
  const found = [];
  for (let r = 0; r < 8; r++) {
    for (let c = 0; c < 8; c++) {
      const s = after[r][c];
      if (!s || s.col !== us || !"brq".includes(s.t) || (r === M.r && c === M.c)) continue;
      for (const [dr, dc] of dirsFor(s.t)) {
        const [was] = rayHits(before, r, c, dr, dc);
        if (!was || was.r !== fr || was.c !== fc) continue;          // the mover was the blocker
        const [now] = rayHits(after, r, c, dr, dc);
        if (!now || now.col === us) continue;                           // and now it's open onto the enemy
        if (now.r === M.r && now.c === M.c) continue;
        const slider = { r, c, t: s.t, sq: name(r, c) };
        if (now.t === "k") { found.push({ slider, tgt: now, check: true }); continue; }
        if (VALUE[now.t] >= 3 && winnable(after, now.r, now.c, slider, us)) found.push({ slider, tgt: now, check: false });
      }
    }
  }
  if (!found.length) return null;
  found.sort((a, b) => (b.check - a.check) || VALUE[b.tgt.t] - VALUE[a.tgt.t]);
  const d = found[0];
  const tsq = name(d.tgt.r, d.tgt.c);
  // Does the moved piece ALSO threaten something? Then it's a double attack / double check.
  const own = winnableTargets(after, M, us);
  const mCheck = own.some((t) => t.t === "k");
  const extra = own.filter((t) => t.sq !== tsq && !(d.check && t.t === "k")).slice(0, 2);
  const doubleCheck = d.check && mCheck;
  const arrows = [{ from: d.slider.sq, to: tsq }];
  const targets = [{ sq: tsq, t: d.tgt.t, role: "target" }];
  for (const t of (doubleCheck ? own.filter((x) => x.t === "k") : extra)) {
    arrows.push({ from: M.sq, to: t.sq });
    if (!targets.some((x) => x.sq === t.sq)) targets.push({ sq: t.sq, t: t.t, role: "target" });
  }
  const opened = "the " + nameOf(d.slider.t) + " on " + d.slider.sq;
  let text;
  if (doubleCheck) text = (san || "The move") + " is a double check — the " + nameOf(M.t) + " and " + opened + " both attack the king.";
  else if (d.check) text = (san || "The move") + " uncovers " + opened + ", which now gives check.";
  else text = (san || "The move") + " uncovers " + opened + ", which now attacks " + onSq(d.tgt.t, tsq) + ".";
  if (!doubleCheck && extra.length) text += " The " + nameOf(M.t) + " also attacks " + list(extra.map((t) => onSq(t.t, t.sq))) + ".";
  return {
    kind: doubleCheck ? "double-check" : extra.length ? "double-attack" : "discovered-attack",
    label: doubleCheck ? "DOUBLE CHECK" : extra.length ? "DOUBLE ATTACK" : d.check ? "DISCOVERED CHECK" : "DISCOVERED ATTACK",
    check: d.check,
    discovered: true,
    attacker: { sq: d.slider.sq, t: d.slider.t },
    mover: { sq: M.sq, t: M.t },
    targets,
    arrows,
    text,
    idea: doubleCheck
      ? "With two pieces checking at once, blocking or capturing can't help — the king has to move."
      : "Moving one piece uncovers an attack from another, so the opponent faces two problems in one move.",
  };
}

const PRIORITY = { "double-check": 0, fork: 1, skewer: 2, pin: 3, "double-attack": 4, "discovered-attack": 5 };

/**
 * Which named tactics does this move create?
 *
 * @param {object} m
 * @param {string} m.fenBefore  position before the move
 * @param {string} m.fenAfter   position after the move
 * @param {string} m.from       origin square ("g8")
 * @param {string} m.to         destination square ("f6")
 * @param {string} [m.san]      the move in SAN, used only to word the explanation
 * @returns {null | { primary, patterns }} patterns are ordered by importance. Each has
 *   { kind, label, text, idea, attacker:{sq,t}, targets:[{sq,t,role}], arrows:[{from,to,dashed?}] }.
 */
export function detectTactics({ fenBefore, fenAfter, from, to, san = null }) {
  const before = parseBoard(fenBefore), after = parseBoard(fenAfter);
  if (!before || !after || !from || !to) return null;
  const [tr, tc] = rc(to);
  const moved = after[tr] && after[tr][tc];
  if (!moved) return null;
  const us = moved.col;
  const M = { r: tr, c: tc, t: moved.t, sq: to };
  const patterns = [];

  const fork = detectFork(before, after, M, from, us, san);
  if (fork) patterns.push(fork);
  const lines = detectLine(before, after, M, from, us, san);
  if (lines && lines.length) patterns.push(lines[0]);
  const disc = detectDiscovered(before, after, M, from, us, san);
  if (disc) patterns.push(disc);

  if (!patterns.length) return null;
  patterns.forEach((p) => { delete p._weight; });
  patterns.sort((a, b) => PRIORITY[a.kind] - PRIORITY[b.kind]);
  return { primary: patterns[0], patterns, color: us };
}

/**
 * The squares and arrows to draw for a detected tactic: the mover's square, every
 * target square, and one arrow per relationship. Kept here so every surface (analysis,
 * training, coach) draws the same picture.
 */
export function tacticOverlay(tactic, moveTo = null) {
  if (!tactic) return { arrows: [], squares: [] };
  const p = tactic.primary || tactic;
  const squares = [];
  const seen = new Set();
  const add = (sq, role) => { if (sq && !seen.has(sq + role)) { seen.add(sq + role); squares.push({ sq, role }); } };
  add(moveTo || (p.mover ? p.mover.sq : p.attacker.sq), "attacker");
  if (p.discovered) add(p.attacker.sq, "attacker");
  for (const t of p.targets) add(t.sq, t.role === "pinned" || t.role === "behind" || t.role === "front" ? "line" : "target");
  return { arrows: p.arrows.map((a) => ({ ...a })), squares };
}

// A short SAN-ish label for a piece letter, exported for callers building text.
export const pieceLetter = (t) => LETTER[t] || "";
