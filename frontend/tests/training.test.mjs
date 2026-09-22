// The Coach -> Training loop, driven the way a person would: click a critical mistake, open the queue,
// (Section labels such as "Why?" are uppercased by CSS, so their DOM text is mixed case: match case-insensitively.)
// try a position, get it wrong, read why, try again, get it right, move on, go back to the analysis.
import { suite, open, review } from "./lib/harness.mjs";

const t = suite("training");
const { browser, page, errors } = await open({ viewport: { width: 1440, height: 900 } });
await page.click("#loadSample");
await page.waitForTimeout(300);
await page.selectOption("#depthSel", "12");
await review(page);
await page.waitForTimeout(400);

const st = (expr) => page.evaluate(expr);
const training = () => st("(() => { const t = __state.training; return t && { phase: t.phase, idx: t.idx, resolved: t.resolved, checking: t.checking, fen: t.item.fen, exp: t.item.expectedMove, from: t.item.expectedFrom, to: t.item.expectedTo, concept: t.item.concept }; })()");
const roles = () => page.evaluate(() => {
  const n = {}; document.querySelectorAll("#board svg.arrows polyline").forEach((p) => { const r = p.getAttribute("data-role"); n[r] = (n[r] || 0) + 1; });
  return n;
});

// ---------- the coach ----------
const crit = await page.locator(".cv2-critbtn").count();
t.ok("the coach lists the critical mistakes, each a button", crit >= 1, crit + " rows");
const firstCrit = await st(`(() => { const b = document.querySelector('.cv2-critbtn'); return { text: b.textContent.replace(/\\s+/g,' ').trim(), aria: b.getAttribute('aria-label'), label: b.querySelector('.bdg').textContent }; })()`);
t.ok("each one says the move, the class (as a word) and the loss — not colour alone",
  /\d+\.{1,3}\S+/.test(firstCrit.text) && /Blunder|Mistake|Inaccuracy/.test(firstCrit.label) && /−\d+%/.test(firstCrit.text) && /lost \d+ percent/.test(firstCrit.aria), firstCrit.text);
await page.click(".cv2-critbtn >> nth=0");
await page.waitForTimeout(400);
const jumped = await st(`(() => { const a = document.querySelector('.mv.active'); const m = __state.moves[__state.ply - 1]; return { ply: __state.ply, san: m && m.san, active: a && a.dataset.ply, cur: a && a.getAttribute('aria-current') }; })()`);
t.ok("clicking a critical mistake jumps the board to that move", jumped.ply > 0 && String(jumped.ply) === jumped.active && jumped.cur === "true", JSON.stringify(jumped));

const tabs = await st("({ hidden: document.getElementById('rightTabs').classList.contains('hidden'), count: document.getElementById('trainCount').textContent })");
t.ok("the Training tab shows how many positions there are", !tabs.hidden && +tabs.count >= 1, JSON.stringify(tabs));
const total = +tabs.count;

// ---------- entering training mode ----------
await page.click('.rtab[data-rtab="training"]');
t.ok("the queue lists positions with a concept, a difficulty and a Try it button", (await page.locator(".train-item .train-try").count()) === total);
await page.click(".train-try >> nth=0");
await page.waitForTimeout(500);
let s = await training();
const mode = await st(`(() => { const vis = (id) => { const e = document.getElementById(id); return e && e.getBoundingClientRect().height > 0; };
  const b = document.getElementById('board').getBoundingClientRect(); const bn = document.getElementById('trainBanner').getBoundingClientRect();
  return { body: document.body.classList.contains('training-mode'), live: vis('live'), moves: vis('movelist'), coach: vis('coachV2Card'), lower: vis('lower'), bar: vis('trainBar'), banner: vis('trainBanner'),
    prog: document.getElementById('trainProg').textContent, boardSquare: Math.abs(b.width - b.height) < 1.5, bannerBesideBoard: bn.left >= b.right - 1, flip: __state.flip, color: __state.training.item.color }; })()`);
t.ok("Try it opens a dedicated mode: the analysis, coach and stats step aside",
  mode.body && mode.bar && mode.banner && !mode.live && !mode.moves && !mode.coach && !mode.lower, JSON.stringify(mode));
t.ok("the header says where you are: 'n / total'", mode.prog === "1 / " + total, mode.prog);
t.ok("the board stays square and the exercise sits right beside it", mode.boardSquare && mode.bannerBesideBoard);
t.ok("the board turns to the side that has to move", mode.flip === (mode.color === "b"), "flip=" + mode.flip + " color=" + mode.color);
const task = await page.locator(".tr-task").textContent();
t.ok("the task is stated plainly", /^Find the best move for (White|Black)\.$/.test(task), task);
t.ok("the engine stays silent while the position is unsolved (no arrows that would give the answer)",
  Object.keys(await roles()).length === 0 && !(await page.locator("#board svg.arrows").count()), JSON.stringify(await roles()));

// a hint points at the piece, not the destination
await page.click("#trHint");
const hinted = await page.locator(".sq.tg-hint").getAttribute("data-sq");
t.ok("Hint highlights the piece that has to move — not where it goes", hinted === s.from, hinted + " vs " + s.from);
// ---------- a wrong move ----------
const wrong = await page.evaluate(async () => {
  const { Chess } = await import("/vendor/chess.js?v=36");
  const it = __state.training.item, c = new Chess(it.fen);
  const ms = c.moves({ verbose: true }).filter((m) => !(m.from === it.expectedFrom && m.to === it.expectedTo));
  // prefer a move that leaves the moved piece to be taken for nothing, so the WHY has a concrete reason
  const hangs = ms.find((m) => { const d = new Chess(m.after); const enemy = m.color === "w" ? "b" : "w";
    return d.attackers(m.to, enemy).length > 0 && d.attackers(m.to, m.color).length === 0; });
  const pick = hangs || ms[0];
  return { from: pick.from, to: pick.to, san: pick.san, hangs: !!hangs };
});
await page.click(`[data-sq="${wrong.from}"]`);
await page.click(`[data-sq="${wrong.to}"]`);
await page.waitForSelector(".trainbanner.st-incorrect");
const inc = await st(`(() => { const b = document.getElementById('trainBanner'); const cs = getComputedStyle(b);
  return { text: b.textContent.replace(/\\s+/g,' '), border: cs.borderLeftColor, bg: cs.backgroundColor, icon: !!b.querySelector('.tr-vico svg') }; })()`);
t.ok("a wrong move turns the whole panel red, with an icon and the words INCORRECT MOVE",
  /INCORRECT MOVE/.test(inc.text) && inc.icon && /rgb\((23\d|2[0-4]\d), ?(6\d|7\d), ?(4\d|5\d)\)/.test(inc.border), inc.border);
t.ok("it shows the move that was played, marked as a mistake", new RegExp(wrong.san.replace(/[+]/g, "\\+") + "\\?").test(inc.text), wrong.san);
t.ok("it explains WHY and the CONSEQUENCE", /WHY\?/i.test(inc.text) && /CONSEQUENCE/i.test(inc.text));
if (wrong.hangs) t.ok("WHY names the concrete problem when the move hangs a piece", /can take it/.test(inc.text), inc.text.slice(0, 220));
const r1 = await roles();
t.ok("the wrong move is marked on the board: a red arrow and a red destination square",
  r1.wrong === 1 && (await page.locator(`.sq.tg-wrong[data-sq="${wrong.to}"]`).count()) === 1, JSON.stringify(r1));
await page.waitForFunction(() => __state.training && !__state.training.checking, null, { timeout: 60000 });
const after = await st(`document.getElementById('trainBanner').textContent.replace(/\\s+/g,' ')`);
t.ok("the engine's evidence arrives: an evaluation change and the opponent's best reply",
  /EVALUATION/i.test(after) && /best reply is/.test(after), after.slice(0, 300));
t.ok("the offered next steps are Try again and Show explanation", (await page.locator("#trAgain").count()) === 1 && (await page.locator("#trExplain").count()) === 1);
// the board is locked once the attempt is judged
await page.click(`[data-sq="${wrong.to}"]`);
t.ok("the board is locked after the attempt (no further moves until Try again)", (await page.locator(".sq.sel").count()) === 0);

// ---------- show the explanation ----------
await page.click("#trExplain");
await page.waitForTimeout(700);
const ex = await st(`document.getElementById('trainBanner').textContent.replace(/\\s+/g,' ')`);
const r2 = await roles();
t.ok("Show explanation reveals the answer with its idea and pattern",
  /THE ANSWER/i.test(ex) && new RegExp(s.exp.replace(/[+#]/g, "\\$&")).test(ex) && /THE IDEA/i.test(ex) && /PATTERN/i.test(ex), ex.slice(0, 200));
t.ok("...and draws it: the answer in green, plus the tactic's arrows when there is one",
  r2.correct === 1 && (await st("__state.training.tactic ? true : false") ? (r2.motif || 0) >= 1 : true), JSON.stringify(r2));

// ---------- try again, then get it right ----------
await page.click("#trAgain");
await page.waitForTimeout(500);
s = await training();
const reset = await st(`({ fen: __state.moves.length ? 'moved' : __state.startFen, arrows: document.querySelectorAll('#board svg.arrows').length })`);
t.ok("Try again puts the same position back, unsolved, with nothing drawn", s.phase === "task" && reset.fen === s.fen && reset.arrows === 0, JSON.stringify(reset));
await page.click(`[data-sq="${s.from}"]`);
await page.click(`[data-sq="${s.to}"]`);
await page.waitForSelector(".trainbanner.st-correct");
const ok = await st(`document.getElementById('trainBanner').textContent.replace(/\\s+/g,' ')`);
t.ok("the right move gets CORRECT, the idea, why it works, the pattern and a takeaway",
  /CORRECT/.test(ok) && /THE IDEA/i.test(ok) && /WHY IT WORKS|PATTERN/i.test(ok) && /TRAINING TAKEAWAY/i.test(ok), ok.slice(0, 260));
const r3 = await roles();
t.ok("...and the board explains it: the move in green, the tactic's arrows to the actual pieces",
  r3.correct === 1 && (await st("__state.training.tactic ? __state.training.tactic.primary.arrows.length : 0")) === (r3.motif || 0), JSON.stringify(r3));
const tg = await st(`(() => { const t = __state.training.tactic; if (!t) return null; const p = t.primary; return { targets: p.targets.map(x => x.sq), rings: [...document.querySelectorAll('.sq.tg-target, .sq.tg-line')].map(e => e.dataset.sq) }; })()`);
if (tg) t.ok("every target square of the tactic is ringed on the board", tg.targets.every((q) => tg.rings.includes(q)), JSON.stringify(tg));

// ---------- move on, then back to the analysis ----------
await page.click("#trSkip");
await page.waitForTimeout(500);
s = await training();
t.ok("Continue moves to the next position", s && s.idx === 1 && (await page.locator("#trainProg").textContent()) === "2 / " + total);
await page.click("#trainBack");
await page.waitForSelector("#summary:not(.hidden)", { timeout: 60000 });
await page.waitForTimeout(500);
const back = await st(`({ body: document.body.classList.contains('training-mode'), moves: document.querySelectorAll('.mv:not(.empty)').length,
  glyphs: document.querySelectorAll('.mv .cg').length, coach: !document.getElementById('coachV2Card').classList.contains('hidden'), mode: __state.mode, tab: document.getElementById('rightCol').dataset.tab })`);
t.ok("Back to analysis restores the game, its review and the coach exactly", !back.body && back.moves === 103 && back.glyphs === 103 && back.coach && back.mode === "analyze" && back.tab === "training", JSON.stringify(back));
t.ok("no page errors through the whole loop", errors.length === 0, errors.slice(0, 2).join(" || ") || "clean");
await browser.close();
t.finish();
