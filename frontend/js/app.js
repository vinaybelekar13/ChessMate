import { Chess } from "../vendor/chess.js?v=36";
import { Engine } from "./engine.js?v=36";
import { renderBoard, setArrows } from "./board.js?v=37";
import { icon, hydrateIcons } from "./icons.js?v=37";
import { detectTactics, tacticOverlay, PIECE_NAME } from "../src/chess/tactics.js?v=1";
import { reviewGame, detectOpening, CLASSES, CLASS_ORDER, winPct, MATE_CP } from "./review.js?v=36";
import {
  createGameAnalyzer,
  createPlayerModel,
  buildCoachReport,
  generateTrainingItems,
  MOTIF_CONCEPTS,
} from "../src/chess/index.js?v=3";
import { rollup } from "./motifs.js?v=36";
import { reviewKey, getCached, putCached } from "./cache.js?v=36";
import { renderMagnusBubble } from "./integration/magnus-coach-bubble.js";
import { drawCard, cardName } from "./card.js?v=36";
import { glyphSvg } from "./glyphs.js?v=36";
import { fetchGames, fetchGameByUrl, playerSide, outcomeFor, refToToken, tokenToUrl }
  from "./onlinegames.js?v=36";
import { lookupPosition, RATING_BANDS } from "./explorer.js?v=36";
import { scanBoard, gridToFen } from "./boardscan.js?v=36";
import { gameSummary } from "./summary.js?v=36";

const DEFAULT_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1";

// The AI Coach and Training panels are part of the workspace now, so the domain-layer
// review (GameAnalyzer -> coach report -> training items) is ON by default. It costs
// nothing extra: it reads the review the app was already running. ?coach=off (or
// ?coach=legacy) restores the old review-only path; ?coach=v2 still works, as before.
const _params = new URLSearchParams(window.location.search);
const USE_COACH_V2 = !["off", "legacy"].includes(_params.get("coach"));
const USE_GAME_ANALYZER = _params.get("analyzer") === "v2" || USE_COACH_V2;
window.__gameAnalyzerEnabled = USE_GAME_ANALYZER;
window.__coachV2Enabled = USE_COACH_V2;
window.__state = null;   // test hook (set below): lets the suite read the app state

// The game the app opens with (barab0s1k vs Niknerf, the one that started this project).
const SAMPLE_PGN = `[Event "Live Chess"]
[Site "Chess.com"]
[Date "2026.07.10"]
[White "Vinay"]
[Black "Parth"]
[Result "1-0"]
[WhiteElo "900"]
[BlackElo "308"]
[ECO "C46"]
[Termination "Vinay won on time"]

1. e4 e5 2. Nc3 Nc6 3. Nf3 Nf6 4. d4 exd4 5. Nxd4 Bb4 6. Nxc6 bxc6 7. Bd3 d5
8. exd5 O-O 9. O-O cxd5 10. Bg5 c6 11. Qf3 Bd6 12. Rae1 Rb8 13. b3 Bb4 14. Qg3 Be6
15. Qh4 h6 16. Bxh6 gxh6 17. Qxh6 Bxc3 18. Rxe6 Ne4 19. Rxe4 dxe4 20. Bxe4 f5
21. Bxf5 Rf7 22. Be6 Qf6 23. Bxf7+ Kxf7 24. Qh5+ Kg8 25. Qg4+ Kf8 26. Rd1 c5
27. Rd5 Re8 28. g3 Re5 29. Rd3 Ke7 30. Qd7+ Kf8 31. Qg4 Ke7 32. Qa4 Re1+
33. Kg2 Bd4 34. Qxa7+ Kf8 35. Qa8+ Kg7 36. Rf3 Qe6 37. Qf8+ Kg6 38. h4 c4
39. bxc4 Qxc4 40. h5+ Kh7 41. Rf7+ Qxf7 42. Qxf7+ Bg7 43. a4 Rd1 44. Qg6+ Kh8
45. Qe8+ Kh7 46. a5 Ra1 47. Qg6+ Kh8 48. a6 Be5 49. Qe8+ Kh7 50. Qxe5 Rxa6
51. Qc7+ Kh6 52. Qf7 1-0`;

// How deep the live panel searches before it stops. It is a ceiling, not a target:
// the search converges here and the worker goes idle, instead of running forever and
// holding a core at ~90% for as long as the tab is open. Deeper than the default
// review depth (14), and reached in a couple of seconds. See docs/NOTES.md.
const LIVE_DEPTH = 20;

const state = {
  engine: null, booted: false,
  headers: {}, moves: [], startFen: DEFAULT_FEN,
  ply: 0, flip: false,
  reviewed: false, reviewing: false, cancel: { cancelled: false },
  // Depth 16, not 14. The engine pool made the review ~3.5x faster, and the honest way
  // to spend that is on depth rather than on finishing sooner: depth is the one lever
  // that genuinely improves the analysis. A depth-16 review now costs less wall-clock
  // than a depth-14 one did before the pool.
  live: true, reviewDepth: 16, liveLines: 3,
  explore: null, selected: null,
  sound: true, opening: null,
  // The Chess.com / Lichess account whose games are listed, and which one is open.
  acct: { site: "chesscom", user: "", games: [], activeId: null, loading: false },
  // Where the open game came from, when it came from one of the sites. Lets a
  // share link point at the game instead of carrying its whole PGN.
  source: null,
  hasClocks: false,
  // Right-click annotations (like Chess.com): arrows and single-square marks the
  // user draws. Cleared on any left interaction or navigation. arrowPreview is
  // the transient one that follows the cursor mid-drag.
  userArrows: [], userMarks: [], arrowPreview: null,
  // The "Explain" walk-through: { ply, base, line:[uci], sans:[san], idx, eval, title }.
  explain: null,
  // What the board is FOR right now: reviewing a game ("analyze"), moving both
  // sides freely with the moves recorded ("solo"), or a game against a
  // strength-limited engine ("bot").
  mode: "analyze",
  botPick: "w",          // the side chosen in the setup card
  bot: null,             // { color, lvl, thinking, over, note } while a bot game exists
  editor: null,          // { grid, stm, flip, brush } while the position editor is open
  // ---- AI Coach / Training (?coach=v2), additive to everything above ----
  // The domain-layer report from the last completed GameAnalyzer review
  // (src/chess/game-analyzer.js), the structured coach data built from it
  // (src/chess/coach.js), and the training items generated from it
  // (src/chess/training.js). null until a review with analyzer=v2 runs.
  report: null,
  coachReport: null,
  trainingItems: [],
  // A session-level PlayerModel (src/chess/player-model.js) that accumulates
  // across every game analyzed in this tab, so recurring patterns and
  // cross-game coaching (buildCoachReport's second argument) can appear
  // from the second reviewed game onward. Kept in memory only - there is no
  // persistence yet (see docs/NOTES.md future-work notes).
  playerModel: USE_GAME_ANALYZER ? createPlayerModel() : null,
  ingestedReviewKeys: new Set(),   // review cache keys already folded into playerModel
  training: null,        // { item, idx, resolved, correct, ... } while practicing a training item
  overlay: null,         // { fen, arrows, squares }: a tactic / training explanation, tied to its position
  engineArrows: null,    // { fen, arrows }: the live engine's top lines
  engineArrowsOn: true,  // the eye button under the board
  showTactics: true,     // draw the tactic a move creates (fork, pin...) on the board
  pausedGame: null,      // { headers, moves, startFen, mode } saved while training is active
};
state.explorerBand = "club";   // which rating band the opening explorer shows
try {
  state.sound = localStorage.getItem("ca_sound") !== "0";
  state.acct.site = localStorage.getItem("ca_site") || "chesscom";
  state.acct.user = localStorage.getItem("ca_user") || "";
  state.explorerBand = localStorage.getItem("ca_explorer_band") || "club";
  state.engineArrowsOn = localStorage.getItem("ca_engine_arrows") !== "0";
} catch (e) { /* private mode */ }

window.__state = state;
const $ = (id) => document.getElementById(id);
const el = {};
["board","evalFill","evalNum","engineStatus","pgnInput","fenInput","depthSel","linesSel",
 "movelist","summary","counts","motifNote","hdrTitle","hdrMeta",
 "pWName","pBName","pWElo","pBElo","reviewBtn","progress","progressBar","progressTxt","readGlyph",
 "readMove","readSub","live","liveToggle","liveEval","liveDepth","liveLinesBox","exploreBar","phases","phaseRows","cardBtn","cardCopyBtn",
 "exploreTxt","explainBar","explainTxt","explainPrev","explainNext","explainDone","engineName","capW","capB","assessBox",
 "assessNote","assessBest","graphCard","evalGraph","openingName","soundToggle","shareBtn",
 "siteSel","userInput","loadUser","acctMsg","gameList",
 "shareBar","shareBtn2","shareKind","shareNote","timeCard","timeGraph","timeNote","accStrip",
 "impBar","impBody","impBarTxt","impToggle",
 "playSetup","botElo","botStart","pickWhite","pickBlack","playBar","playTxt","botResign","botRematch","soloReset",
 "explorerCard","explorerTitle","explorerRating","explorerBody","explorerNote",
 "editorCard","editorBoard","palette","edWhite","edBlack","edFlip","edClear","edStart","edAnalyze","edCancel","edErr","editNote",
 "scanFile","scanBtn","coachCard","coachBody",
 "coachV2Card","coachV2Body","trainingCard","trainingBody","trainBanner",
 "liveBadge","linesFold","bArrows","moveCard","trainBar","trainBack","trainProg","tacticBox","rightTabs","rightCol","trainCount",
 "reviewLabel","liveToggleTxt","bFlip"]
  .forEach((k) => (el[k] = $(k)));

// ---------- helpers ----------
function fmtEval(cp, mate) {
  if (mate != null) return (mate > 0 ? "#" : "#-") + Math.abs(mate);
  // checkmate already on the board: the game is over, so show the result
  if (Math.abs(cp || 0) >= MATE_CP) return cp > 0 ? "1-0" : "0-1";
  const v = (cp || 0) / 100;
  return (v > 0 ? "+" : "") + v.toFixed(2);
}
function wpFromNode(cp, mate) {
  if (mate != null) return mate > 0 ? 100 : 0;
  return winPct(cp || 0);
}
function currentFen() {
  if (state.explore) return state.explore.chess.fen();
  return state.ply === 0 ? state.startFen : state.moves[state.ply - 1].fenAfter;
}
function pvToSan(fen, uciList, max = 12) {
  const c = new Chess(fen);
  const out = [];
  for (const u of uciList.slice(0, max)) {
    try {
      const m = c.move({ from: u.slice(0, 2), to: u.slice(2, 4), promotion: u.slice(4, 5) || undefined });
      if (!m) break;
      out.push(m.san);
    } catch (e) { break; }
  }
  return out;
}
function formatPvSan(fen, sans) {
  const stmWhite = fen.split(" ")[1] === "w";
  let n = parseInt(fen.split(" ")[5] || "1", 10);
  let s = "", white = stmWhite;
  sans.forEach((san, i) => {
    if (white) s += (i ? " " : "") + n + ". " + san;
    else { s += (i === 0 ? n + "... " : " ") + san; n++; }
    white = !white;
  });
  return s;
}

// ---------- sounds (synthesized with WebAudio, no audio files) ----------
let audioCtx = null;
function audio() {
  if (!audioCtx) {
    const AC = window.AudioContext || window.webkitAudioContext;
    if (!AC) return null;
    audioCtx = new AC();
  }
  if (audioCtx.state === "suspended") audioCtx.resume();
  return audioCtx;
}
function blip({ freq = 240, dur = 0.08, gain = 0.13, noisy = false }) {
  if (!state.sound) return;
  const ctx = audio();
  if (!ctx) return;
  const t = ctx.currentTime;
  const g = ctx.createGain();
  g.gain.setValueAtTime(gain, t);
  g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
  g.connect(ctx.destination);
  if (noisy) { // capture: short filtered noise burst
    const len = Math.max(1, Math.floor(ctx.sampleRate * dur));
    const buf = ctx.createBuffer(1, len, ctx.sampleRate);
    const d = buf.getChannelData(0);
    for (let i = 0; i < len; i++) d[i] = (Math.random() * 2 - 1) * (1 - i / len);
    const src = ctx.createBufferSource();
    src.buffer = buf;
    const f = ctx.createBiquadFilter();
    f.type = "bandpass"; f.frequency.value = freq * 3;
    src.connect(f); f.connect(g); src.start(t); src.stop(t + dur);
  } else {     // move: soft pitch-dropping thock
    const o = ctx.createOscillator();
    o.type = "sine";
    o.frequency.setValueAtTime(freq, t);
    o.frequency.exponentialRampToValueAtTime(freq * 0.6, t + dur);
    o.connect(g); o.start(t); o.stop(t + dur);
  }
}
function playMoveSound(mv) {
  if (!mv) return;
  const san = mv.san || "";
  if (san.includes("#")) return blip({ freq: 500, dur: 0.18, gain: 0.16 });
  if (san.includes("+")) return blip({ freq: 420, dur: 0.10, gain: 0.14 });
  if (san.includes("x") || mv.captured) return blip({ freq: 200, dur: 0.10, gain: 0.18, noisy: true });
  if (san.startsWith("O-O")) return blip({ freq: 175, dur: 0.12, gain: 0.15 });
  blip({ freq: 240, dur: 0.075, gain: 0.12 });
}

// A short synthesized fanfare for the two rare classes, to go with the on-board
// flourish. Brilliant is a bright rising arpeggio with a high sparkle; Great is
// a warm two-note chime. Built with WebAudio like the move sounds — no files.
function celebrateSound(cls) {
  if (!state.sound || (cls !== "brilliant" && cls !== "great")) return;
  const ctx = audio();
  if (!ctx) return;
  const t0 = ctx.currentTime;
  const chime = (freq, at, dur, gain, type) => {
    const o = ctx.createOscillator(), g = ctx.createGain();
    o.type = type; o.frequency.value = freq;
    g.gain.setValueAtTime(0.0001, at);
    g.gain.exponentialRampToValueAtTime(gain, at + 0.012);
    g.gain.exponentialRampToValueAtTime(0.0001, at + dur);
    o.connect(g); g.connect(ctx.destination);
    o.start(at); o.stop(at + dur + 0.02);
  };
  if (cls === "brilliant") {
    [523.25, 659.25, 783.99, 1046.5].forEach((f, i) => chime(f, t0 + i * 0.075, 0.32, 0.16, "triangle"));
    chime(1567.98, t0 + 0.26, 0.5, 0.09, "sine");   // shimmer on top
  } else {
    chime(523.25, t0, 0.34, 0.15, "sine");
    chime(783.99, t0 + 0.1, 0.42, 0.15, "sine");     // up a fifth
  }
}

// ---------- share link ----------
let chipTimer = null;
function flashChip(msg) {
  el.engineStatus.textContent = msg;
  clearTimeout(chipTimer);
  chipTimer = setTimeout(() => {
    el.engineStatus.textContent = state.booted ? "ready" : "starting…";
  }, 1800);
}
// gzip <-> URL-safe base64, so a pasted-PGN link isn't thousands of characters.
const b64url = {
  from: (bytes) => {
    let bin = "";
    for (const b of bytes) bin += String.fromCharCode(b);
    return btoa(bin).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
  },
  to: (s) => {
    const bin = atob(s.replace(/-/g, "+").replace(/_/g, "/"));
    const bytes = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
    return bytes;
  },
};
async function gzip(text) {
  if (!window.CompressionStream) return null;
  const s = new Blob([text]).stream().pipeThrough(new CompressionStream("gzip"));
  return b64url.from(new Uint8Array(await new Response(s).arrayBuffer()));
}
async function gunzip(token) {
  const s = new Blob([b64url.to(token)]).stream().pipeThrough(new DecompressionStream("gzip"));
  return await new Response(s).text();
}

// Shortest link that can reopen what's on screen:
//   #g=  a pointer to the game on Chess.com / Lichess  (~70 chars)
//   #z=  the PGN, gzipped                              (~1/3 of raw)
//   #pgn= / #fen=  the older formats, still read below
async function buildShareLink() {
  const base = location.origin + location.pathname;
  const token = state.source ? refToToken(state.source) : null;
  if (token) return base + "#g=" + token;

  const pgn = el.pgnInput.value.trim();
  if (state.moves.length && pgn) {
    const z = await gzip(pgn);
    if (z) return base + "#z=" + z;
    return base + "#pgn=" + btoa(unescape(encodeURIComponent(pgn)));
  }
  if (state.startFen && state.startFen !== DEFAULT_FEN) {
    return base + "#fen=" + encodeURIComponent(state.startFen);
  }
  return base;
}
async function copyShareLink() {
  const url = await buildShareLink();
  try {
    await navigator.clipboard.writeText(url);
    flashChip("link copied");
    flashShare("Link copied");
  } catch (e) {
    window.prompt("Copy this link:", url);
  }
}

// Load a game/position that was shared via the URL hash.
async function loadFromHash() {
  const h = location.hash || "";
  try {
    if (h.startsWith("#g=")) {
      const url = tokenToUrl(decodeURIComponent(h.slice(3)));
      if (!url) return false;
      await openGameFromLink(url);
      return true;
    }
    if (h.startsWith("#z=")) {
      const pgn = await gunzip(h.slice(3));
      el.pgnInput.value = pgn;
      loadGame(parseGame(pgn));
      return true;
    }
    if (h.startsWith("#pgn=")) {
      const pgn = decodeURIComponent(escape(atob(h.slice(5))));
      el.pgnInput.value = pgn;
      loadGame(parseGame(pgn));
      return true;
    }
    if (h.startsWith("#fen=")) {
      const fen = decodeURIComponent(h.slice(5));
      new Chess(fen); // validates
      loadGame({ headers: { White: "Position", Black: "analysis" }, moves: [], startFen: fen });
      return true;
    }
  } catch (e) { /* fall through to empty board */ }
  return false;
}

// ---------- import card folding ----------
// With a game open the import form is just dead weight at the top of the page,
// pushing the board below the fold. Fold it to one line until it's wanted.
function setImportOpen(open) {
  el.impBody.classList.toggle("hidden", !open);
  el.impBar.classList.toggle("hidden", open);
  syncChrome();
}
// The workspace is sized to the viewport minus whatever sits above it. The folded import
// strip is the one variable piece of chrome, so CSS is told whether it is showing
// (body[data-strip]) and does the rest with calc().
function syncChrome() {
  const imp = document.querySelector(".import");
  const strip = imp && !imp.classList.contains("hidden") && !el.impBar.classList.contains("hidden");
  document.body.dataset.strip = strip ? "1" : "0";
}
function renderImportBar() {
  const h = state.headers;
  if (!state.moves.length) { setImportOpen(true); return; }
  const bits = [];
  if (h.Result) bits.push(h.Result);
  if (h.Date) bits.push(h.Date.replace(/\./g, "-"));
  el.impBarTxt.innerHTML = esc((h.White || "White") + " vs " + (h.Black || "Black")) +
    (bits.length ? ' <span class="dim">· ' + esc(bits.join(" · ")) + "</span>" : "");
  setImportOpen(false);
}

// ---------- share bar ----------
let shareTimer = null;
function flashShare(msg) {
  el.shareNote.textContent = msg;
  el.shareNote.classList.remove("hidden");
  clearTimeout(shareTimer);
  shareTimer = setTimeout(() => el.shareNote.classList.add("hidden"), 2200);
}
function renderShareBar() {
  const has = state.moves.length > 0 || state.startFen !== DEFAULT_FEN;
  el.shareBar.classList.toggle("hidden", !has);
  // A game we can point at needs no PGN in the link at all.
  el.shareKind.textContent = state.source
    ? "a short link straight to this game"
    : "a link that carries the whole game";
}

// ---------- import from a Chess.com / Lichess account ----------
function esc(s) {
  return String(s == null ? "" : s).replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
function fmtDate(d) {
  if (!(d instanceof Date) || isNaN(d)) return "";
  const sameYear = d.getFullYear() === new Date().getFullYear();
  return d.toLocaleDateString(undefined,
    sameYear ? { month: "short", day: "numeric" } : { year: "numeric", month: "short", day: "numeric" });
}
function setAcctMsg(text, isErr) {
  el.acctMsg.textContent = text || "";
  el.acctMsg.classList.toggle("err", !!isErr);
  el.acctMsg.classList.toggle("hidden", !text);
}

// The one import field takes either a username or a link to a single game.
// Anything that looks like a link is handled as one — including links we don't
// recognise, which then say so instead of being looked up as a username.
const looksLikeUrl = (s) => /^https?:\/\//i.test(s);

function loadFromInput() {
  const txt = el.userInput.value.trim();
  if (!txt || state.acct.loading) return;
  if (looksLikeUrl(txt)) openGameFromLink(txt);
  else loadAccountGames();
}

// Open the one game a Chess.com / Lichess link points at.
async function openGameFromLink(link) {
  state.acct.loading = true;
  el.loadUser.disabled = true;
  setAcctMsg("Fetching that game…", false);
  try {
    // A Chess.com link without ?username= (an /analysis/ one, say) can still be
    // found if we know whose game to look through — use the last account searched.
    const g = await fetchGameByUrl(link, {
      onProgress: (m) => setAcctMsg(m, false),
      fallbackUser: state.acct.user,
    });
    let parsed;
    try { parsed = parseGame(g.pgn); }
    catch (e) { throw new Error("Could not read that game's PGN."); }

    el.pgnInput.value = g.pgn;
    // Face the board towards whoever the link is about: the ?username= on a
    // Chess.com link, the /black suffix on a Lichess one, or the last account
    // searched if it happens to be one of the two players.
    const players = { white: parsed.headers.White || "", black: parsed.headers.Black || "" };
    const side = playerSide(players, g.user || state.acct.user);
    state.flip = side ? side === "b" : g.color === "black";

    loadGame(parsed);   // also clears the game-list highlight and the source
    state.source = g.ref || null;
    renderShareBar();
    setAcctMsg((players.white || "White") + " vs " + (players.black || "Black") + " — loaded.", false);
    document.querySelector(".boardcard").scrollIntoView({ block: "nearest", behavior: "smooth" });
  } catch (e) {
    setAcctMsg(e.message || "Could not open that game.", true);
  } finally {
    state.acct.loading = false;
    el.loadUser.disabled = false;
  }
}

async function loadAccountGames() {
  const site = el.siteSel.value;
  const user = el.userInput.value.trim();
  if (!user || state.acct.loading) return;
  state.acct.loading = true;
  el.loadUser.disabled = true;
  el.gameList.classList.add("hidden");
  setAcctMsg("Fetching games…", false);
  try {
    const games = await fetchGames(site, user, { max: 30 });
    state.acct = { site, user, games, activeId: null, loading: false };
    try {
      localStorage.setItem("ca_site", site);
      localStorage.setItem("ca_user", user);
    } catch (e) { /* private mode */ }
    setAcctMsg(games.length + " recent games — click one to open it.", false);
    renderGameList();
  } catch (e) {
    state.acct.games = [];
    setAcctMsg(e.message || "Could not load those games.", true);
  } finally {
    state.acct.loading = false;
    el.loadUser.disabled = false;
  }
}

const OUTCOME_GLYPH = { win: "W", loss: "L", draw: "½" };

function renderGameList() {
  const { games, user } = state.acct;
  el.gameList.innerHTML = "";
  el.gameList.classList.toggle("hidden", !games.length);
  for (const g of games) {
    const side = playerSide(g, user);
    const out = outcomeFor(g, user);
    const name = (who, elo, isMe) =>
      '<span class="' + (isMe ? "me" : "") + '">' + esc(who) + "</span>" +
      (elo ? ' <span class="el">' + elo + "</span>" : "");

    const row = document.createElement("div");
    row.className = "grow" + (g.id === state.acct.activeId ? " on" : "");
    row.innerHTML =
      '<span class="gres ' + out + '">' + OUTCOME_GLYPH[out] + "</span>" +
      '<div class="gmain">' +
        '<div class="gp">' + name(g.white, g.whiteElo, side === "w") +
          ' <span class="vs">vs</span> ' + name(g.black, g.blackElo, side === "b") + "</div>" +
        (g.opening ? '<div class="gop">' + esc(g.opening) + "</div>" : "") +
      "</div>" +
      '<div class="gmeta"><span class="tc">' + esc(g.timeClass || "") + "</span><br>" +
        esc(fmtDate(g.date)) + "</div>";
    row.addEventListener("click", () => openAccountGame(g));
    el.gameList.appendChild(row);
  }
}

function openAccountGame(g) {
  let parsed;
  try { parsed = parseGame(g.pgn); }
  catch (e) { setAcctMsg("Could not read that game's PGN.", true); return; }
  el.pgnInput.value = g.pgn;
  // Show the board from the perspective of the player whose games these are.
  state.flip = playerSide(g, state.acct.user) === "b";
  loadGame(parsed);                 // clears activeId and source
  state.acct.activeId = g.id;
  state.source = g.ref || null;
  renderGameList();
  renderShareBar();
  document.querySelector(".boardcard").scrollIntoView({ block: "nearest", behavior: "smooth" });
}

// ---------- captured material ----------
const PIECE_GLYPH = { p: "♟", n: "♞", b: "♝", r: "♜", q: "♛" };
const INIT = { p: 8, n: 2, b: 2, r: 2, q: 1 };
const PVAL = { p: 1, n: 3, b: 3, r: 5, q: 9 };

function countPieces(fen) {
  const w = { p: 0, n: 0, b: 0, r: 0, q: 0 }, b = { p: 0, n: 0, b: 0, r: 0, q: 0 };
  for (const ch of fen.split(" ")[0]) {
    const lc = ch.toLowerCase();
    if (w[lc] !== undefined) (ch === ch.toUpperCase() ? w : b)[lc]++;
  }
  return { w, b };
}
function capHtml(list, colorClass) {
  return list.map((t) => '<span class="cap ' + colorClass + '">' + PIECE_GLYPH[t] + "</span>").join("");
}
function renderMaterial(fen) {
  const { w, b } = countPieces(fen);
  const capByWhite = [], capByBlack = [];
  let diff = 0;
  for (const t of ["p", "n", "b", "r", "q"]) {
    for (let i = 0; i < INIT[t] - b[t]; i++) capByWhite.push(t); // black pieces White took
    for (let i = 0; i < INIT[t] - w[t]; i++) capByBlack.push(t); // white pieces Black took
    diff += PVAL[t] * (w[t] - b[t]);
  }
  el.capW.innerHTML = capHtml(capByWhite, "b") + (diff > 0 ? '<span class="adv">+' + diff + "</span>" : "");
  el.capB.innerHTML = capHtml(capByBlack, "w") + (diff < 0 ? '<span class="adv">+' + -diff + "</span>" : "");
}

const PIECE_LONG = { p: "a pawn", n: "a knight", b: "a bishop", r: "a rook", q: "your queen" };

// Plain-English, coach-style note for a classified move.
function coachNote(mv) {
  const b = mv.bestSan;
  const cap = mv.san.includes("x");
  const check = /[+#]/.test(mv.san);
  // If we can name WHY the move went wrong, lead with that — the ★ best move is
  // shown separately below. Falls back to the generic line when no motif fired.
  if (mv.motif && mv.motif.text) return mv.motif.text;
  switch (mv.cls) {
    // The rare good moves get the same specificity the bad ones do: name what was
    // offered, and how forced the find was. The "why" walk-through sits below.
    case "brilliant": return "A brilliant sacrifice — you offer " + (PIECE_LONG[mv.sacPiece] || "material") +
      ", and taking it doesn't save your opponent: the follow-up keeps you on top.";
    case "great": return "A great find — practically the only move that works here" +
      (mv.onlyGap ? ": anything else gives up " + mv.onlyGap + "% of your winning chances." : ".");
    case "best": return check ? "The sharpest move — you keep the pressure on."
      : cap ? "The best move — you grab the key material." : "The strongest move in the position.";
    case "good": return "A sound, solid move — nothing lost.";
    case "book": return "A well-known opening move.";
    case "inaccuracy": return "Slightly inaccurate" + (b ? " — " + b + " was a touch stronger." : ".");
    case "mistake": return "A mistake — this hands your opponent chances" + (b ? ". " + b + " was better." : ".");
    case "blunder": return "A blunder — this drops material or the game" + (b ? ". " + b + " was much stronger." : ".");
    default: return "";
  }
}

function renderAssessment() {
  const show = state.reviewed && state.ply > 0 && !state.explore;
  if (!show) { el.assessBox.classList.add("hidden"); return; }
  const mv = state.moves[state.ply - 1];
  el.assessNote.textContent = coachNote(mv);
  // Show the engine's move whenever it is GENUINELY better than what was played —
  // so good/excellent moves still say "★ Qf4 was best", but a move that already
  // matches (or beats) the engine's own line shows nothing. Comparing mover-POV
  // evals is what avoids the old paradox of labelling a WORSE move "best": the
  // played-move eval and the pre-move best-line eval come from different searches
  // and can cross near equality.
  const played = moverEval(mv.cpWhite, mv.mateWhite, mv.color);
  const best = moverEval(mv.bestCpWhite, mv.bestMateWhite, mv.color);
  if (mv.bestSan && mv.bestSan !== mv.san && best > played + 5) {
    el.assessBest.classList.remove("hidden");
    el.assessBest.classList.add("clickable");
    el.assessBest.innerHTML =
      '<span class="cg" style="--c:var(--best)">' + glyphSvg("best") + "</span> <b>" + mv.bestSan + "</b> was best" +
      (mv.bestLine && mv.bestLine.length ? '<span class="preview-hint">' + icon("hint") + 'Explain</span>' : "") +
      '<span class="evchip">' + fmtEval(mv.bestCpWhite, mv.bestMateWhite) + "</span>";
    el.assessBest.onclick = () => (mv.bestLine && mv.bestLine.length ? enterExplain(mv) : previewBest(mv));
  } else if ((mv.cls === "brilliant" || mv.cls === "great") && mv.afterLine && mv.afterLine.length) {
    // A brilliancy earns the same walk-through a blunder gets — but forwards: step
    // through the engine's line FROM AFTER the move and watch the sacrifice hold.
    el.assessBest.classList.remove("hidden");
    el.assessBest.classList.add("clickable");
    el.assessBest.innerHTML =
      '<span class="cg" style="--c:var(' + CLASSES[mv.cls].v + ')">' + glyphSvg(mv.cls) + "</span> " +
      "<b>See why it works</b>" +
      '<span class="preview-hint">' + icon("hint") + 'Explain</span>' +
      '<span class="evchip">' + fmtEval(mv.cpWhite, mv.mateWhite) + "</span>";
    el.assessBest.onclick = () => enterFollowUp(mv);
  } else { el.assessBest.classList.add("hidden"); el.assessBest.onclick = null; }
  el.assessBox.classList.remove("hidden");
}

// Play the engine's recommended move on the board (branch from the position
// before the played move) so the user can see where it goes and continue it.
function previewBest(mv) {
  if (!mv || !mv.bestFrom) return;
  playToken++;
  const chess = new Chess(mv.fenBefore);
  try { chess.move({ from: mv.bestFrom, to: mv.bestTo, promotion: mv.bestPromo || undefined }); }
  catch (e) { return; }
  state.explore = { base: mv.fenBefore, chess, arrow: { from: mv.bestFrom, to: mv.bestTo } };
  state.selected = null;
  el.exploreBar.classList.remove("hidden");
  renderExploreLine();
  drawBoard();
  animateMove(mv.bestFrom, mv.bestTo);
  playMoveSound({ san: mv.bestSan || "" });
  renderReadout(); renderAssessment(); restartLive();
}

// ---------- "Explain": walk an engine line one move at a time ----------
// For a move that wasn't best, step through the line the engine recommends INSTEAD
// (from before the move). For a brilliant/great move, step through the line that
// follows it, to see why it holds. Each ‹ › plays / takes back one move on the
// board. "Got it" returns to the review.
function enterWalkthrough(baseFen, uciLine, evalStr, title) {
  if (!uciLine || !uciLine.length) return;
  playToken++;
  const chess = new Chess(baseFen);
  const line = [], sans = [];
  for (const uci of uciLine) {
    let m;
    try { m = chess.move({ from: uci.slice(0, 2), to: uci.slice(2, 4), promotion: uci.slice(4, 5) || undefined }); }
    catch (e) { break; }
    if (!m) break;
    line.push(uci); sans.push(m.san);
    if (line.length >= 12) break;                 // enough to make the point, still digestible
  }
  if (!line.length) return;
  state.explain = { ply: state.ply, base: baseFen, line, sans, idx: 1, eval: evalStr, title };
  state.selected = null;
  el.exploreBar.classList.add("hidden");
  renderExplain(true);
}
function enterExplain(mv) {
  if (!mv) return;
  enterWalkthrough(mv.fenBefore, mv.bestLine, fmtEval(mv.bestCpWhite, mv.bestMateWhite), "The best line");
}
function enterFollowUp(mv) {
  if (!mv) return;
  enterWalkthrough(mv.fenAfter, mv.afterLine, fmtEval(mv.cpWhite, mv.mateWhite), "Why " + mv.san + " works");
}

function renderExplain(animate) {
  const ex = state.explain;
  if (!ex) return;
  const chess = new Chess(ex.base);
  let from = null, to = null;
  for (let i = 0; i < ex.idx; i++) {
    const u = ex.line[i];
    chess.move({ from: u.slice(0, 2), to: u.slice(2, 4), promotion: u.slice(4, 5) || undefined });
    from = u.slice(0, 2); to = u.slice(2, 4);
  }
  state.explore = { base: ex.base, chess, arrow: null };   // reuse the exploration board
  el.explainBar.classList.remove("hidden");
  const parts = ex.sans.map((s, i) => (i === ex.idx - 1 ? "<b>" + esc(s) + "</b>" : esc(s)));
  el.explainTxt.innerHTML = '<span class="bulb">' + icon("hint") + "</span> " + parts.join(" ") +
    ' <span class="evchip">' + ex.eval + "</span>";
  el.explainPrev.disabled = ex.idx <= 1;
  el.explainNext.disabled = ex.idx >= ex.line.length;
  drawBoard();
  if (animate && from) animateMove(from, to);
  renderReadout(); renderAssessment(); restartLive();
}

function explainStep(delta) {
  const ex = state.explain;
  if (!ex) return;
  const ni = Math.max(1, Math.min(ex.line.length, ex.idx + delta));
  if (ni === ex.idx) return;
  playToken++;
  const forward = ni > ex.idx;
  ex.idx = ni;
  renderExplain(forward);
  playMoveSound({ san: ex.sans[ex.idx - 1] });
}

function exitExplain() {
  const ply = state.explain ? state.explain.ply : state.ply;
  state.explain = null;
  state.explore = null;
  el.explainBar.classList.add("hidden");
  el.exploreBar.classList.add("hidden");
  goto(ply);
}

// Play the NEXT single move of an engine line (one click = one move). The engine
// then re-analyzes the new position, so clicking a line again continues it.
function playLine(fen, pv) {
  if (!pv || !pv.length) return;
  playToken++;
  // Continue the current line if this click starts from the current explore
  // position; otherwise begin a fresh line from `fen`.
  let base, chess;
  if (state.explore && state.explore.chess.fen() === fen) {
    base = state.explore.base;
    chess = state.explore.chess;
  } else {
    base = fen;
    chess = new Chess(fen);
  }
  const u = pv[0];
  let mv;
  try { mv = chess.move({ from: u.slice(0, 2), to: u.slice(2, 4), promotion: u.slice(4, 5) || undefined }); }
  catch (e) { return; }
  if (!mv) return;
  state.explore = { base, chess, arrow: { from: mv.from, to: mv.to } };
  state.selected = null;
  el.exploreBar.classList.remove("hidden");
  renderExploreLine();
  drawBoard();
  animateMove(mv.from, mv.to);
  playMoveSound(mv);
  renderReadout(); renderAssessment(); restartLive();
}

function cssVar(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || "#888";
}

// Win-probability line across the whole game with dots on notable moves.
function drawEvalGraph() {
  if (!state.reviewed || !state.moves.length) { el.graphCard.classList.add("hidden"); return; }
  el.graphCard.classList.remove("hidden");
  const cv = el.evalGraph;
  const W = Math.max(300, cv.getBoundingClientRect().width), H = 100;
  const dpr = window.devicePixelRatio || 1;
  cv.width = W * dpr; cv.height = H * dpr; cv.style.height = H + "px";
  const ctx = cv.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, W, H);

  const N = state.moves.length;
  const pts = [winPct(20)];
  for (const m of state.moves) pts.push(m.mateWhite != null ? (m.mateWhite > 0 ? 100 : 0) : winPct(m.cpWhite));
  const X = (i) => (i / N) * W;
  const Y = (v) => H - (v / 100) * H;

  ctx.fillStyle = cssVar("--panel2"); ctx.fillRect(0, 0, W, H);          // black-advantage ground
  ctx.beginPath(); ctx.moveTo(0, H);
  pts.forEach((v, i) => ctx.lineTo(X(i), Y(v)));
  ctx.lineTo(W, H); ctx.closePath();
  ctx.fillStyle = "#e9e7df"; ctx.fill();                                  // white-advantage area

  ctx.strokeStyle = "rgba(128,128,128,.45)"; ctx.setLineDash([4, 4]);
  ctx.beginPath(); ctx.moveTo(0, Y(50)); ctx.lineTo(W, Y(50)); ctx.stroke(); ctx.setLineDash([]);

  ctx.strokeStyle = "rgba(60,66,74,.55)"; ctx.lineWidth = 1;
  ctx.beginPath(); pts.forEach((v, i) => (i ? ctx.lineTo(X(i), Y(v)) : ctx.moveTo(X(i), Y(v)))); ctx.stroke();

  const notable = { brilliant: 1, great: 1, inaccuracy: 1, mistake: 1, blunder: 1 };
  state.moves.forEach((m, i) => {
    if (!notable[m.cls]) return;
    ctx.beginPath(); ctx.arc(X(i + 1), Y(pts[i + 1]), 3.4, 0, 7);
    ctx.fillStyle = cssVar(CLASSES[m.cls].v); ctx.fill();
    ctx.strokeStyle = "#fff"; ctx.lineWidth = 1.2; ctx.stroke();
  });

  const cx = X(state.ply);
  ctx.strokeStyle = cssVar("--accent"); ctx.lineWidth = 1.5;
  ctx.beginPath(); ctx.moveTo(cx, 0); ctx.lineTo(cx, H); ctx.stroke();
}

// Seconds spent on each move, one bar per move, coloured by how good the move
// was — so a blunder played in two seconds is impossible to miss.
function drawTimeGraph() {
  const show = state.hasClocks && state.moves.length;
  el.timeCard.classList.toggle("hidden", !show);
  if (!show) return;

  const cv = el.timeGraph;
  const W = Math.max(300, cv.getBoundingClientRect().width), H = 64;
  const dpr = window.devicePixelRatio || 1;
  cv.width = W * dpr; cv.height = H * dpr; cv.style.height = H + "px";
  const ctx = cv.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, W, H);

  const N = state.moves.length;
  const spents = state.moves.map((m) => (m.spent == null ? 0 : m.spent));
  // One long think shouldn't flatten everything else, so scale to the 95th
  // percentile and let the rare outlier clip at full height.
  const sorted = [...spents].sort((a, b) => a - b);
  const cap = Math.max(1, sorted[Math.floor(sorted.length * 0.95)] || 1);
  const pad = 2;
  const bw = Math.max(1, (W - pad * 2) / N - 1);

  ctx.fillStyle = cssVar("--panel2");
  ctx.fillRect(0, 0, W, H);

  state.moves.forEach((m, i) => {
    const x = pad + (i / N) * (W - pad * 2);
    const h = Math.min(1, spents[i] / cap) * (H - 8);
    ctx.fillStyle = state.reviewed ? cssVar(CLASSES[m.cls].v) : cssVar("--muted");
    ctx.globalAlpha = m.color === "w" ? 1 : 0.55;   // Black's moves sit dimmer
    ctx.fillRect(x, H - h, bw, h);
  });
  ctx.globalAlpha = 1;

  const cx = pad + (Math.max(0, state.ply - 1) / N) * (W - pad * 2) + bw / 2;
  ctx.strokeStyle = cssVar("--accent"); ctx.lineWidth = 1.5;
  ctx.beginPath(); ctx.moveTo(cx, 0); ctx.lineTo(cx, H); ctx.stroke();
}

// The line that turns clock data into an actual diagnosis: did the moves that
// went wrong get less thought than the rest? Errors = inaccuracy or worse; book
// moves are excluded from the comparison since theory is played instantly.
const WENT_WRONG = { inaccuracy: 1, mistake: 1, blunder: 1 };
function timeVerdict(color) {
  const mine = state.moves.filter((m) => m.color === color && m.spent != null && m.cls !== "book");
  const bad = mine.filter((m) => WENT_WRONG[m.cls]).map((m) => m.spent);
  const good = mine.filter((m) => !WENT_WRONG[m.cls]).map((m) => m.spent);
  if (bad.length < 3 || good.length < 5) return null;   // too small a sample to claim anything
  return { bad: median(bad), good: median(good), n: bad.length };
}
function renderTimeNote() {
  if (!state.reviewed || !state.hasClocks) { el.timeNote.classList.add("hidden"); return; }
  const rows = [];
  for (const c of ["w", "b"]) {
    const v = timeVerdict(c);
    if (!v) continue;
    const who = (c === "w" ? state.headers.White : state.headers.Black) || (c === "w" ? "White" : "Black");
    const ratio = v.good > 0 ? v.bad / v.good : 1;
    const verdict = ratio <= 0.6 ? " — the errors were the rushed moves."
      : ratio >= 1.6 ? " — so the errors came from the long thinks, not from rushing."
      : " — thinking time wasn’t what separated them.";
    rows.push("<b>" + esc(who) + "</b> spent a median <b>" + fmtSecs(v.bad) + "</b> on the " +
      v.n + " moves that went wrong, versus <b>" + fmtSecs(v.good) + "</b> on the rest" + verdict);
  }
  el.timeNote.innerHTML = rows.join("<br>");
  el.timeNote.classList.toggle("hidden", !rows.length);
}

// A one-line-per-side pattern across the game's mistakes, e.g. "3 of 4 costly
// moves left a piece undefended." Silent unless one motif dominates a side.
function renderMotifNote() {
  if (!state.reviewed) { el.motifNote.classList.add("hidden"); return; }
  const rows = [];
  for (const c of ["w", "b"]) {
    const line = rollup(state.moves, c);
    if (!line) continue;
    const who = (c === "w" ? state.headers.White : state.headers.Black) || (c === "w" ? "White" : "Black");
    rows.push("<b>" + esc(who) + "</b> — " + line);
  }
  el.motifNote.innerHTML = rows.join("<br>");
  el.motifNote.classList.toggle("hidden", !rows.length);
}

// ---------- clocks ----------
// Chess.com and Lichess both stamp every move with the mover's remaining time,
// as {[%clk 0:09:58.5]}. chess.js drops comments, so read them from the text.
function parseClocks(pgn) {
  const out = [];
  const re = /\[%clk\s+(\d+):(\d{1,2}):(\d{1,2}(?:\.\d+)?)\]/g;
  let m;
  while ((m = re.exec(pgn))) out.push(+m[1] * 3600 + +m[2] * 60 + parseFloat(m[3]));
  return out;
}
// "600" / "600+5" / "180+2"; correspondence games ("1/259200") have no clock.
function parseTimeControl(tc) {
  if (!tc || tc.includes("/")) return { base: null, inc: 0 };
  const [b, i] = String(tc).split("+");
  const base = parseInt(b, 10);
  return { base: isNaN(base) ? null : base, inc: parseInt(i, 10) || 0 };
}
// Seconds a player burned on each move: what their clock lost since their last
// turn, plus whatever increment they were given back for making the move.
function attachClocks(moves, pgn, headers) {
  const clocks = parseClocks(pgn);
  if (clocks.length !== moves.length || !moves.length) return;
  const { base, inc } = parseTimeControl(headers.TimeControl);
  moves.forEach((mv, i) => {
    mv.clock = clocks[i];
    const before = i >= 2 ? clocks[i - 2] : base;
    mv.spent = before == null ? null
      : Math.max(0, Math.round((before - clocks[i] + inc) * 10) / 10);
  });
}
function fmtSecs(s) {
  if (s == null) return "";
  if (s < 10) return s.toFixed(1) + "s";
  if (s < 60) return Math.round(s) + "s";
  const m = Math.floor(s / 60);
  return m + "m " + String(Math.round(s % 60)).padStart(2, "0") + "s";
}
const median = (a) => {
  if (!a.length) return null;
  const s = [...a].sort((x, y) => x - y);
  const h = s.length >> 1;
  return s.length % 2 ? s[h] : (s[h - 1] + s[h]) / 2;
};

// ---------- parsing ----------
function parseGame(pgn) {
  const headers = {};
  for (const m of pgn.matchAll(/\[(\w+)\s+"([^"]*)"\]/g)) headers[m[1]] = m[2];
  const c = new Chess();
  try { c.loadPgn(pgn); }
  catch (e) { c.loadPgn(pgn.replace(/\{[^}]*\}/g, "").replace(/\$\d+/g, "")); }
  const startFen = headers.FEN ? headers.FEN : DEFAULT_FEN;
  const rc = new Chess(startFen);
  const verbose = c.history({ verbose: true });
  const moves = verbose.map((h, idx) => {
    const fenBefore = rc.fen();
    const m = rc.move(h.san);
    return {
      san: m.san, from: m.from, to: m.to,
      uci: m.from + m.to + (m.promotion || ""),
      color: m.color, fenBefore, fenAfter: rc.fen(),
      moveNo: rc.moveNumber() - (m.color === "w" ? 0 : 1),
      clock: null, spent: null,
    };
  });
  attachClocks(moves, pgn, headers);
  return { headers, startFen, moves };
}

function loadGame(parsed, opts = {}) {
  // Loading an actual new game/position retires the previous game's AI Coach
  // report and training queue - they described a different game. The
  // training flow itself loads a bare position through this same function
  // (see startTraining/stopTraining) and passes keepDomainState so the
  // report and item list it's driving survive the reload.
  if (!opts.keepDomainState) {
    state.report = null;
    state.coachReport = null;
    state.trainingItems = [];
    state.training = null;
    state.pausedGame = null;
    state.overlay = null;
    document.body.classList.remove("training-mode");
    if (el.trainBar) el.trainBar.classList.add("hidden");
    if (el.rightTabs) el.rightTabs.classList.add("hidden");
    if (el.rightCol) setRightTab("coach");
    if (el.coachV2Card) el.coachV2Card.classList.add("hidden");
    if (el.trainingCard) el.trainingCard.classList.add("hidden");
    if (el.trainBanner) el.trainBanner.classList.add("hidden");
  }
  state.headers = parsed.headers;
  state.moves = parsed.moves;
  state.startFen = parsed.startFen;
  state.ply = 0;
  state.reviewed = false;
  state.review = null;
  state.explore = null;
  state.selected = null;
  el.cardBtn.classList.add("hidden");   // nothing to report until this game is reviewed
  el.cardCopyBtn.classList.add("hidden");
  window.__card = null;
  state.opening = detectOpening(parsed.moves);
  state.hasClocks = parsed.moves.some((m) => m.spent != null);
  // A pasted game has no site to point at; the importers set this again after.
  state.source = null;
  // Any other import path (paste / FEN / sample / share link) deselects the
  // account game list; openAccountGame re-selects the row it just opened.
  state.acct.activeId = null;
  renderGameList();
  renderShareBar();
  renderImportBar();
  renderHeader();
  renderOpening();
  renderMoveList();
  el.summary.classList.add("hidden");
  el.accStrip.classList.add("hidden");
  el.phases.classList.add("hidden");
  el.coachCard.classList.add("hidden");
  el.reviewBtn.disabled = !state.moves.length || !state.booted;
  renderModeUi();          // mode-owned visibility (import card, play bar, review lock)
  goto(0);
}

// ---------- rendering ----------
function renderHeader() {
  const h = state.headers;
  const hasGame = !!(h.White || h.Black || state.moves.length);
  el.hdrTitle.textContent = hasGame ? (h.White || "White") + "  vs  " + (h.Black || "Black")
                                    : "Load a game to analyze";
  el.pWName.textContent = h.White || "White";
  el.pBName.textContent = h.Black || "Black";
  el.pWElo.textContent = h.WhiteElo ? "(" + h.WhiteElo + ")" : "";
  el.pBElo.textContent = h.BlackElo ? "(" + h.BlackElo + ")" : "";
  const bits = [];
  if (h.Date) bits.push(h.Date.replace(/\./g, "-"));
  if (h.ECO) bits.push("ECO " + h.ECO);
  if (h.Result) bits.push(h.Result);
  if (h.Termination) bits.push(h.Termination);
  el.hdrMeta.textContent = hasGame && bits.length ? bits.join("  ·  ")
    : "Paste a PGN or FEN above, upload a .pgn file, or click Load sample.";
}

function renderOpening() {
  const op = state.opening; // [eco, name]
  if (!op) { el.openingName.classList.add("hidden"); return; }
  el.openingName.textContent = op[1] + "  ·  " + op[0];
  el.openingName.classList.remove("hidden");
}

function renderMoveList() {
  const M = state.moves;
  el.movelist.innerHTML = "";
  if (!M.length) {
    el.movelist.innerHTML = '<div class="mvempty-msg">No moves — load a PGN, or a FEN for single-position analysis.</div>';
    return;
  }
  const rows = Math.ceil(M.length / 2);
  for (let r = 0; r < rows; r++) {
    const row = document.createElement("div");
    row.className = "mvrow";
    const no = document.createElement("div");
    no.className = "no"; no.textContent = r + 1 + ".";
    row.appendChild(no);
    for (const idx of [2 * r, 2 * r + 1]) {
      const cell = document.createElement("div");
      if (idx < M.length) {
        const mv = M[idx];
        cell.className = "mv"; cell.dataset.ply = idx + 1;
        let inner = '<span class="san">' + mv.san + "</span>";
        let label = (Math.floor(idx / 2) + 1) + (idx % 2 ? "..." : ".") + " " + mv.san;
        if (state.reviewed) {
          // three channels for one fact: the symbol (text), its colour, and the drawn mark (icon)
          const cl = CLASSES[mv.cls];
          const ann = ANNOTATION[mv.cls];
          if (ann) inner += '<span class="ann" style="--c:var(' + cl.v + ')">' + ann + "</span>";
          inner += '<span class="cg" style="--c:var(' + cl.v + ')" title="' + cl.label + '">' + glyphSvg(mv.cls) + '<span class="vh">' + esc(cl.g) + "</span></span>";
          inner += '<span class="ev">' + fmtEval(mv.cpWhite, mv.mateWhite) + "</span>";
          label += ", " + cl.label + ", evaluation " + fmtEval(mv.cpWhite, mv.mateWhite);
        }
        cell.setAttribute("role", "listitem");
        cell.setAttribute("aria-label", label);
        cell.innerHTML = inner;
        cell.addEventListener("click", () => { state.explore = null; goto(idx + 1); });
      } else cell.className = "mv empty";
      row.appendChild(cell);
    }
    el.movelist.appendChild(row);
  }
}

// There used to be an "estimated rating" here, mapped from accuracy by
// 6.8 * exp(0.0575 * acc). Checked against 64 real games spanning 280-3414 Elo,
// it was wrong by 1072 Elo on average: two players 2500 points apart produced
// the SAME accuracy (88.4% -> real 322, 89.3% -> real 2826), and the curve
// mathematically topped out near 2100, so every strong player was under-rated by
// ~1700. Nor is it a matter of re-fitting: accuracy does correlate with strength
// (r = 0.63), but even the best possible fit still misses by ~850 Elo, because a
// quiet game inflates accuracy and a sharp one deflates it whoever is playing.
// A number that wrong is worse than no number, so the estimate is gone.

// The classic annotation symbols, shown beside the move. Only the classes that carry one.
const ANNOTATION = { brilliant: "!!", great: "!", inaccuracy: "?!", mistake: "?", blunder: "??" };
const PHASE_LABEL = { opening: "Opening", middlegame: "Middlegame", endgame: "Endgame" };

// Accuracy by phase. One accuracy number says how well you played; three say WHERE you
// played badly, which is the only one of them you can act on.
function renderPhases() {
  const P = state.review.phases;
  if (!P) { el.phases.classList.add("hidden"); return; }
  const rows = [];
  for (const ph of ["opening", "middlegame", "endgame"]) {
    const w = P[ph].w, b = P[ph].b;
    if (!w && !b) continue;                       // neither side had a move to judge here
    const cell = (x) => (x
      ? '<span class="pn">' + x.acc + '%</span><span class="pc">' + x.n + "</span>"
      : '<span class="pn dim">–</span><span class="pc"></span>');
    rows.push('<div class="phaserow"><span class="pl">' + PHASE_LABEL[ph] + "</span>" +
      '<span class="pv">' + cell(w) + "</span>" +
      '<span class="pv">' + cell(b) + "</span></div>");
  }
  if (!rows.length) { el.phases.classList.add("hidden"); return; }
  el.phaseRows.innerHTML = rows.join("");
  el.phases.classList.remove("hidden");
}

// The plain-English "what to work on" card (js/summary.js). One paragraph per human
// side; the bot never gets coached. Hidden until a game is reviewed.
function renderCoach(botGame) {
  if (!state.reviewed) { el.coachCard.classList.add("hidden"); return; }
  const ctx = { moves: state.moves, review: state.review, opening: state.opening, headers: state.headers };
  const blocks = [];
  for (const c of ["w", "b"]) {
    const nm = c === "w" ? state.headers.White : state.headers.Black;
    if (botGame && /Stockfish \(≈/.test(nm || "")) continue;   // don't lecture the engine
    const text = gameSummary(c, ctx);
    if (text) blocks.push('<p class="advp">' + esc(text) + "</p>");
  }
  el.coachBody.innerHTML = blocks.join("");
  el.coachCard.classList.toggle("hidden", !blocks.length);
}

function renderSummary() {
  const R = state.review;
  el.summary.classList.remove("hidden");
  // Headline accuracies stay up beside the board; the breakdown lives below.
  // Each side also gets its rough game-rating estimate (see estimateElo for the
  // long list of caveats — the ratingnote below the breakdown repeats the short one).
  // A band, not a lone number — one game can't pin a rating (see estimateElo / NOTES),
  // so the range and the "provisional" tag own that instead of hiding it in a footnote.
  // Suppressed entirely for a game against the bot: the opponent's strength is one we
  // SET (≈400), and beating a bot that hangs pieces makes anyone's play read strong, so
  // the number would be pure noise. Detected from the bot's header name.
  const botGame = /Stockfish \(≈/.test(state.headers.White || "") ||
                  /Stockfish \(≈/.test(state.headers.Black || "");
  const est = (v) => (v == null || botGame ? "" :
    '<span class="est">game rating ≈ ' + v.lo + "–" + v.hi +
    ' <span class="prov">provisional</span></span>');
  el.accStrip.innerHTML =
    '<div class="a"><b>' + R.accWhite + "%</b><span>" + esc(state.headers.White || "White") + "</span>" +
      est(R.est && R.est.w) + "</div>" +
    '<div class="a"><b>' + R.accBlack + "%</b><span>" + esc(state.headers.Black || "Black") + "</span>" +
      est(R.est && R.est.b) + "</div>";
  el.accStrip.classList.remove("hidden");
  renderPhases();
  renderTimeNote();
  renderMotifNote();
  renderCoach(botGame);
  el.counts.innerHTML = "";
  for (const k of CLASS_ORDER) {
    const w = R.counts.w[k] || 0, b = R.counts.b[k] || 0;
    const row = document.createElement("div");
    row.className = "countrow";
    row.innerHTML =
      '<span class="g" style="background:var(' + CLASSES[k].v + ')">' + glyphSvg(k) + "</span>" +
      '<span class="cl">' + CLASSES[k].label + "</span>" +
      '<span class="cw">' + w + "</span><span class=\"cb\">" + b + "</span>";
    el.counts.appendChild(row);
  }
}

// A single comparable number from the mover's point of view, so "is the engine's
// move actually better than mine?" is one comparison. Mate scores dominate cp.
function moverEval(cpWhite, mateWhite, color) {
  const white = mateWhite != null ? (mateWhite > 0 ? 1e6 - mateWhite : -1e6 - mateWhite) : (cpWhite || 0);
  return color === "w" ? white : -white;
}
function fmtEvalBar(cp, mate) {
  if (mate != null) return "M" + Math.abs(mate);
  if (Math.abs(cp || 0) >= MATE_CP) return "#";
  return (Math.abs(cp || 0) / 100).toFixed(1);
}
function updateEvalBar(cp, mate) {
  const wp = wpFromNode(cp, mate);
  el.evalFill.style.transform = "scaleY(" + wp / 100 + ")";
  el.evalNum.textContent = fmtEvalBar(cp, mate);
  el.evalNum.className = "evalnum " + (wp >= 50 ? "bot" : "top");
}

function setGlyph(bg, inner) {
  el.readGlyph.style.background = bg;
  el.readGlyph.innerHTML = inner;
}
function renderReadout() {
  if (state.explain) {
    setGlyph("var(--best)", icon("hint"));
    el.readMove.textContent = state.explain.title || "The best line";
    el.readSub.innerHTML = "Step through it with <b>‹ ›</b>. Press <b>Got it</b> to return.";
    renderTacticBox();
    return;
  }
  if (state.explore) {
    setGlyph("var(--accent)", icon("analysis"));
    el.readMove.textContent = "Analysis line";
    el.readSub.innerHTML = "Exploring a variation. <b>Return to game</b> to resume review.";
    renderTacticBox();
    return;
  }
  // A live bot game: the move card is the "whose move is it" line, and nothing
  // more — the engine's opinions stay out of a competitive game.
  if (state.bot && !state.bot.over) {
    setGlyph("var(--accent)", icon("swords"));
    el.readMove.textContent = "You vs " + botName(state.bot);
    el.readSub.innerHTML = state.bot.thinking ? "Stockfish is thinking…"
      : "<b>Your move</b> — drag a piece or click it.";
    renderTacticBox();
    return;
  }
  const mv = state.ply > 0 ? state.moves[state.ply - 1] : null;
  if (!mv) {
    setGlyph("var(--muted)", icon("info"));
    el.readMove.textContent = "Starting position";
    el.readSub.innerHTML = "Use ← → keys or click a move. <b>Drag a piece</b> (or click it) to explore lines.";
    renderTacticBox();
    return;
  }
  const moveTxt = mv.moveNo + (mv.color === "w" ? ". " : "... ") + mv.san;
  if (state.reviewed) {
    const cl = CLASSES[mv.cls];
    setGlyph("var(" + cl.v + ")", glyphSvg(mv.cls));   // drawn mark, centred by geometry
    // icon (the mark) + colour + text (the label): the verdict never depends on colour alone
    el.readMove.innerHTML = "<span>" + esc(moveTxt) + '</span><span class="bdg" style="--c:var(' + cl.v + ')">' + esc(cl.label) + "</span>";
    let sub = "Eval " + fmtEval(mv.cpWhite, mv.mateWhite);
    if (mv.spent != null) sub += " · took " + fmtSecs(mv.spent);
    if (mv.loss >= 5) sub += " · lost " + mv.loss + "% win chance";
    el.readSub.innerHTML = sub;   // the "stronger move" suggestion lives in the assessment card
  } else {
    setGlyph("var(--muted)", icon("list"));
    el.readMove.textContent = moveTxt;
    el.readSub.innerHTML = (mv.spent != null ? "Took " + fmtSecs(mv.spent) + " · r" : "R") +
      'un <b>Analyze game</b> for move classifications.';
  }
  renderTacticBox();
}

// The named tactic the current move creates — worded from the real position, and drawn on
// the board (arrows to the actual targets, ringed target squares) while it is switched on.
const TACTIC_ICON = { fork: "fork", "double-attack": "double", "double-check": "double", pin: "pin", skewer: "skewer", "discovered-attack": "discovered" };
function renderTacticBox() {
  const box = el.tacticBox;
  const mv = state.ply > 0 ? state.moves[state.ply - 1] : null;
  const t = mv && !state.explain && !state.explore && !botActive() && !state.training ? tacticFor(mv) : null;
  if (!t) { box.classList.add("hidden"); box.innerHTML = ""; return; }
  const p = t.primary;
  const on = state.showTactics;
  box.classList.remove("hidden");
  box.innerHTML =
    '<div class="tacttop"><span class="bdg tactic">' + icon(TACTIC_ICON[p.kind] || "target") + esc(p.label) + "</span>" +
    '<span class="grow1"></span>' +
    '<button class="tactshow" id="tactShow" aria-pressed="' + on + '" aria-label="' + (on ? "Hide" : "Show") + ' the tactic on the board">' +
    icon(on ? "eye" : "eyeoff") + (on ? "On board" : "Show") + "</button></div>" +
    '<div class="tacttxt">' + esc(p.text) + "</div>" +
    '<div class="tactidea">' + esc(p.idea) + "</div>";
  box.querySelector("#tactShow").onclick = () => { state.showTactics = !state.showTactics; drawBoard(); renderTacticBox(); };
}

// ---------- move animation ----------
let playToken = 0; // cancels an in-flight line playback when the user does anything else
function dispCR(square) {
  const file = square.charCodeAt(0) - 97, rank = +square[1];
  return { c: state.flip ? 7 - file : file, r: state.flip ? rank - 1 : 8 - rank };
}
// Slide the piece now sitting on `to` from where it started (FLIP technique).
function animateMove(from, to) {
  const pc = el.board.querySelector('[data-sq="' + to + '"] .pc');
  if (!pc) return;
  const size = el.board.getBoundingClientRect().width / 8;
  const f = dispCR(from), t = dispCR(to);
  const dx = (f.c - t.c) * size, dy = (f.r - t.r) * size;
  pc.style.transition = "none";
  pc.style.transform = "translate(" + dx + "px," + dy + "px)";
  pc.getBoundingClientRect(); // force reflow so the next frame animates
  requestAnimationFrame(() => { pc.style.transition = "transform .2s ease"; pc.style.transform = "translate(0,0)"; });
}

// The Chess.com-style celebration for a rare move. Fired once, when you step
// FORWARD onto a brilliant or great move (like the move sound and animation).
// The element is appended to the destination square, which the next drawBoard
// rebuilds away — so navigating on naturally cancels an in-flight flourish and
// at most one can ever exist.
const FLOURISH = { brilliant: "Brilliant!", great: "Great!" };
function flourish(mv) {
  if (!FLOURISH[mv.cls] || !CLASSES[mv.cls]) return;
  if (window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  const sq = el.board.querySelector('[data-sq="' + mv.to + '"]');
  if (!sq) return;
  // Where the square sits on screen decides which way the label points, so it
  // never spills off the board edge.
  const file = mv.to.charCodeAt(0) - 97, rank = +mv.to[1];
  const col = state.flip ? 7 - file : file;
  const row = state.flip ? rank - 1 : 8 - rank;

  const wrap = document.createElement("div");
  wrap.className = "flourish";
  wrap.style.setProperty("--fl-col", "var(" + CLASSES[mv.cls].v + ")");
  const fill = document.createElement("div"); fill.className = "fl-fill";
  const glyph = document.createElement("div"); glyph.className = "fl-glyph";
  glyph.innerHTML = glyphSvg(mv.cls);
  glyph.dataset.g = CLASSES[mv.cls].g;
  const bubble = document.createElement("div"); bubble.className = "fl-bubble"; bubble.textContent = FLOURISH[mv.cls];
  if (row === 0) bubble.classList.add("below");
  if (col <= 1) bubble.classList.add("right");
  else if (col >= 6) bubble.classList.add("left");
  wrap.append(fill, glyph, bubble);
  sq.appendChild(wrap);
  setTimeout(() => wrap.remove(), 1450);
}

// ---------- board annotations ----------
// Everything the board draws besides pieces comes from here, so drawBoard() (which rebuilds
// the squares) and repaintArrows() (which only replaces the arrow layer, cheap enough to run
// on every engine update) always agree.
//   user arrows  - drawn by hand, always on top
//   tactic       - the fork / pin / skewer... the current move creates, from the real position
//   overlay      - a training explanation, tied to the position it was made for
//   engine       - the engine's top lines, only when nothing else is telling a story
const tacticCache = new Map();
function tacticFor(mv) {
  const k = mv.fenBefore + "|" + mv.uci;
  if (!tacticCache.has(k)) {
    let t = null;
    try { t = detectTactics({ fenBefore: mv.fenBefore, fenAfter: mv.fenAfter, from: mv.from, to: mv.to, san: mv.san }); }
    catch (e) { t = null; }
    tacticCache.set(k, t);
  }
  return tacticCache.get(k);
}
// While a training position is unsolved, or a bot game runs, the engine stays silent.
// (Training: the whole exercise is silent — the engine's lines and arrows would hand over the answer.)
const trainingQuiet = () => !!state.training;
const quiet = () => botActive() || trainingQuiet();

function kingAlert(fen) {
  try {
    const c = new Chess(fen);
    if (!c.isCheck()) return null;
    const stm = c.turn();
    for (const row of c.board()) for (const p of row) if (p && p.type === "k" && p.color === stm) return { sq: p.square, mate: c.isCheckmate() };
  } catch (e) { /* not a position chess.js accepts (e.g. an editor board) */ }
  return null;
}

function boardAnnotations(fen) {
  const arrows = [], squares = [];
  let tactic = null;
  if (state.explore) {
    if (state.explore.arrow) arrows.push({ from: state.explore.arrow.from, to: state.explore.arrow.to, role: "best" });
  } else if (state.ply > 0 && !state.explain && !state.training && !botActive() && state.showTactics) {
    const mv = state.moves[state.ply - 1];
    tactic = tacticFor(mv);
    if (tactic) {
      const ov = tacticOverlay(tactic, mv.to);
      ov.arrows.forEach((a) => arrows.push({ ...a, role: "motif" }));
      squares.push(...ov.squares);
    }
  }
  if (state.overlay && state.overlay.fen === fen) {
    arrows.push(...state.overlay.arrows);
    squares.push(...state.overlay.squares);
  }
  if (!arrows.length && state.engineArrowsOn && !quiet() && !state.explain && !state.explore &&
      state.engineArrows && state.engineArrows.fen === fen) arrows.push(...state.engineArrows.arrows);
  return { arrows, squares, tactic };
}
function allArrows(fen) {
  const ann = boardAnnotations(fen);
  const arrows = ann.arrows.slice();
  for (const a of state.userArrows) arrows.push(a);          // user annotations on top
  if (state.arrowPreview) arrows.push(state.arrowPreview);   // the one being dragged now
  return { ...ann, arrows };
}
function repaintArrows() {
  const fen = currentFen();
  setArrows(el.board, allArrows(fen).arrows, state.userMarks, state.flip);
}

function drawBoard() {
  const fen = currentFen();
  let lastMove = null, badge = null;
  if (state.explore) {
    const h = state.explore.chess.history({ verbose: true });
    const last = h[h.length - 1];
    if (last) lastMove = { from: last.from, to: last.to };
  } else if (state.ply > 0) {
    const mv = state.moves[state.ply - 1];
    lastMove = { from: mv.from, to: mv.to };
    if (state.reviewed) badge = { square: mv.to, cls: mv.cls };
  }
  const hlClass = badge ? badge.cls : null;
  const targets = state.selected ? legalTargets(fen, state.selected) : [];
  const ann = allArrows(fen);
  const ka = kingAlert(fen);
  renderBoard(el.board, fen, {
    flip: state.flip, lastMove, badge, hlClass, selected: state.selected, targets, arrows: ann.arrows,
    marks: state.userMarks, overlay: ann.squares,
    check: ka ? ka.sq : null, mate: ka ? ka.mate : false,
    onSquareClick: onSquareClick,
    onSquareDown: onSquareDown,
  });
  hoverSq = null;                    // the squares were just rebuilt
  renderMaterial(fen);
}

function legalTargets(fen, sq) {
  try {
    const c = new Chess(fen);
    return c.moves({ square: sq, verbose: true }).map((m) => m.to);
  } catch (e) { return []; }
}

// ---------- navigation ----------
function goto(ply) {
  const prev = state.ply;
  clearUserDrawings();          // annotations belong to the position you drew them on
  if (state.explain) { state.explain = null; el.explainBar.classList.add("hidden"); }
  playToken++;
  state.ply = Math.max(0, Math.min(state.moves.length, ply));
  state.selected = null;
  drawBoard();
  if (state.ply === prev + 1 && state.ply > 0) {
    const m = state.moves[state.ply - 1]; animateMove(m.from, m.to); playMoveSound(m);
    if (state.reviewed) { flourish(m); celebrateSound(m.cls); }
  } else if (state.ply === prev - 1 && prev > 0) {
    const m = state.moves[prev - 1]; animateMove(m.to, m.from); playMoveSound(m);
  }
  renderReadout();
  renderAssessment();
  // eval bar: prefer reviewed data, else let live analysis fill it in.
  if (state.reviewed && state.ply > 0) {
    const mv = state.moves[state.ply - 1];
    updateEvalBar(mv.cpWhite, mv.mateWhite);
  } else if (state.ply === 0) {
    updateEvalBar(20, null);
  }
  document.querySelectorAll(".mv").forEach((e) => {
    const on = +e.dataset.ply === state.ply;
    e.classList.toggle("active", on);
    if (on) e.setAttribute("aria-current", "true"); else e.removeAttribute("aria-current");
  });
  // Keep the current move visible INSIDE the move list. (scrollIntoView would also scroll every
  // ancestor - the whole analysis column - and push the review header out of sight.)
  const act = document.querySelector(".mv.active");
  if (act) {
    const box = el.movelist.getBoundingClientRect(), a = act.getBoundingClientRect();
    if (a.top < box.top) el.movelist.scrollTop -= box.top - a.top + 4;
    else if (a.bottom > box.bottom) el.movelist.scrollTop += a.bottom - box.bottom + 4;
  }
  drawEvalGraph();
  drawTimeGraph();
  restartLive();
}

// ---------- move exploration: click-to-move and drag-and-drop ----------

// Play from -> to on the exploration board. `animate` is off for drags, where
// the user's hand has already carried the piece across.
function tryPlayMove(from, to, animate) {
  // Outside plain analysis a board move is a move IN the game — unless a
  // walk-through or a clicked engine line is open, or a finished bot game is being
  // analysed, where the usual exploration branching applies.
  if (state.mode !== "analyze" && !state.explore && !state.explain && !(state.bot && state.bot.over)) {
    if (state.mode === "bot" && !state.bot) return false;         // no game yet: board is idle
    if (botActive() && state.bot.thinking) return false;          // wait for the reply
    return commitMove(from, to, null, animate);
  }
  const fen = currentFen();
  const c = new Chess(fen);
  let mv;
  try { mv = c.move({ from, to, promotion: "q" }); }
  catch (e) { return false; }        // not a legal move
  if (!mv) return false;

  if (!state.explore) state.explore = { base: fen, chess: new Chess(fen) };
  state.explore.chess.move({ from, to, promotion: "q" });
  state.explore.arrow = null;
  state.selected = null;
  el.exploreBar.classList.remove("hidden");
  renderExploreLine();
  drawBoard();
  if (animate) animateMove(from, to);
  playMoveSound(mv);
  renderReadout(); renderAssessment(); restartLive();
  return true;
}

function pieceCanMove(fen, square) {
  const c = new Chess(fen);
  const piece = c.get(square);
  if (!piece || piece.color !== (fen.split(" ")[1] || "w")) return false;
  if (state.training && state.training.resolved) return false;   // the exercise is over: Try again / Continue
  // In a live bot game only the player's pieces answer to the hand, and only
  // while the engine isn't thinking. Before a game starts, the board is idle.
  if (botActive() && (state.bot.thinking || piece.color !== state.bot.color)) return false;
  if (state.mode === "bot" && !state.bot) return false;
  return true;
}

let lastDropAt = 0;   // swallows the click a completed drag leaves behind

function onSquareClick(name) {
  if (state.reviewing) return;
  if (Date.now() - lastDropAt < 250) return;
  clearUserDrawings();               // any left click wipes the drawn annotations
  playToken++;
  const fen = currentFen();
  if (state.selected && state.selected !== name && tryPlayMove(state.selected, name, true)) return;
  state.selected = pieceCanMove(fen, name) ? name : null;
  drawBoard();
}

// ---------- dragging ----------
// The piece stays in its square and is carried by a transform, so the board
// keeps its layout; on drop we hand off to the same tryPlayMove as clicking.
let drag = null;
let hoverSq = null;

function squareAt(x, y) {
  const r = el.board.getBoundingClientRect();
  if (x < r.left || x >= r.right || y < r.top || y >= r.bottom) return null;
  const dc = Math.floor(((x - r.left) / r.width) * 8);
  const dr = Math.floor(((y - r.top) / r.height) * 8);
  const file = state.flip ? 7 - dc : dc;
  const rank = state.flip ? dr + 1 : 8 - dr;
  return "abcdefgh"[file] + rank;
}
function setHover(name) {
  if (hoverSq === name) return;
  const prev = hoverSq && el.board.querySelector('[data-sq="' + hoverSq + '"]');
  if (prev) prev.classList.remove("over");
  hoverSq = name;
  const next = name && el.board.querySelector('[data-sq="' + name + '"]');
  if (next) next.classList.add("over");
}
function carry(x, y) {
  const { pc, home } = drag;
  pc.style.transform = "translate(" + (x - home.x) + "px," + (y - home.y) + "px) scale(1.06)";
}

function onSquareDown(name, ev) {
  if (ev.button === 2) { startArrow(name, ev); return; }  // right button = draw an arrow / mark
  if (ev.button > 0 || state.reviewing || drag) return;   // left button / primary touch only
  if (!pieceCanMove(currentFen(), name)) return;          // not your piece: leave it to click
  clearUserDrawings();                                    // starting a move wipes annotations

  playToken++;
  state.selected = name;
  drawBoard();                       // paints the selection and the legal targets

  // drawBoard() rebuilt the squares, so grab the piece element that exists now.
  const sq = el.board.querySelector('[data-sq="' + name + '"]');
  const pc = sq && sq.querySelector(".pc");
  if (!pc) return;

  const r = sq.getBoundingClientRect();
  drag = { from: name, pc, moved: false, home: { x: r.left + r.width / 2, y: r.top + r.height / 2 } };
  pc.classList.add("dragging");
  carry(ev.clientX, ev.clientY);
  setHover(name);

  window.addEventListener("pointermove", onDragMove);
  window.addEventListener("pointerup", onDragEnd);
  window.addEventListener("pointercancel", onDragEnd);
  ev.preventDefault();               // no text selection / native image drag
}

function onDragMove(ev) {
  if (!drag) return;
  drag.moved = true;
  carry(ev.clientX, ev.clientY);
  setHover(squareAt(ev.clientX, ev.clientY));
}

function onDragEnd(ev) {
  if (!drag) return;
  window.removeEventListener("pointermove", onDragMove);
  window.removeEventListener("pointerup", onDragEnd);
  window.removeEventListener("pointercancel", onDragEnd);

  const { from, pc, moved } = drag;
  const to = ev.type === "pointercancel" ? null : squareAt(ev.clientX, ev.clientY);
  pc.classList.remove("dragging");
  pc.style.transform = "";
  setHover(null);
  drag = null;

  // A press with no travel is just a click-select — keep the piece selected so
  // the user can finish the move by clicking the destination.
  if (!moved || !to || to === from) return;

  lastDropAt = Date.now();
  if (!tryPlayMove(from, to, false)) {
    state.selected = null;           // dropped somewhere illegal: put it back
    drawBoard();
  }
}

// ---------- right-click annotations (arrows + square marks) ----------
// Right-drag draws an arrow; a right-click without travel marks a square.
// Drawing the same shape again toggles it off; a modifier key picks the colour
// (Chess.com / Lichess convention). Any left click or navigation clears them.
let arrowDraw = null;
const ARROW_COLORS = { none: "#15781b", shift: "#a02c2c", alt: "#1f6fb0", ctrl: "#e0a53f" };
function arrowColor(ev) {
  if (ev.shiftKey) return ARROW_COLORS.shift;
  if (ev.altKey) return ARROW_COLORS.alt;
  if (ev.ctrlKey || ev.metaKey) return ARROW_COLORS.ctrl;
  return ARROW_COLORS.none;
}
function clearUserDrawings() {
  if (!state.userArrows.length && !state.userMarks.length && !state.arrowPreview) return false;
  state.userArrows = []; state.userMarks = []; state.arrowPreview = null;
  return true;
}
function startArrow(name, ev) {
  ev.preventDefault();
  arrowDraw = { from: name, previewTo: null };
  window.addEventListener("pointermove", onArrowMove);
  window.addEventListener("pointerup", onArrowUp);
  window.addEventListener("pointercancel", onArrowCancel);
}
function onArrowMove(ev) {
  if (!arrowDraw) return;
  const to = squareAt(ev.clientX, ev.clientY);
  if (to === arrowDraw.previewTo) return;               // only redraw when the target square changes
  arrowDraw.previewTo = to;
  state.arrowPreview = to && to !== arrowDraw.from ? { from: arrowDraw.from, to, color: arrowColor(ev) } : null;
  drawBoard();
}
function onArrowUp(ev) {
  endArrowListeners();
  const from = arrowDraw && arrowDraw.from;
  arrowDraw = null;
  state.arrowPreview = null;
  if (from) {
    const to = squareAt(ev.clientX, ev.clientY);
    const color = arrowColor(ev);
    if (to === from) toggleMark(from, color);
    else if (to) toggleArrow(from, to, color);
  }
  drawBoard();
}
function onArrowCancel() { endArrowListeners(); arrowDraw = null; state.arrowPreview = null; drawBoard(); }
function endArrowListeners() {
  window.removeEventListener("pointermove", onArrowMove);
  window.removeEventListener("pointerup", onArrowUp);
  window.removeEventListener("pointercancel", onArrowCancel);
}
function toggleArrow(from, to, color) {
  const i = state.userArrows.findIndex((a) => a.from === from && a.to === to);
  if (i < 0) state.userArrows.push({ from, to, color });
  else if (state.userArrows[i].color === color) state.userArrows.splice(i, 1);   // same again -> remove
  else state.userArrows[i].color = color;                                        // different colour -> recolour
}
function toggleMark(square, color) {
  const i = state.userMarks.findIndex((m) => m.square === square);
  if (i < 0) state.userMarks.push({ square, color });
  else if (state.userMarks[i].color === color) state.userMarks.splice(i, 1);
  else state.userMarks[i].color = color;
}

function renderExploreLine() {
  if (!state.explore) { el.exploreBar.classList.add("hidden"); return; }
  const sans = state.explore.chess.history();
  el.exploreTxt.textContent = formatPvSan(state.explore.base, sans) || "—";
}

function returnToGame() {
  state.explore = null;
  state.selected = null;
  el.exploreBar.classList.add("hidden");
  goto(state.ply);
}

// ---------- modes: analyze / free board / play the engine ----------
// "analyze" is the app as it always was. "solo" records the moves you make (both
// sides) as THE game, so you can lay out a line by hand and press Analyze on it.
// "bot" is a game against a strength-limited Stockfish — with the engine's mouth
// taped shut until it ends: no eval bar, no live lines, no review button.

// The engine's UCI_Elo floor is 1320, so the club-strength settings use it directly
// and the lower ones fall back to Skill Level. But Skill Level 0 is not a beginner —
// it still plays ~1000-1350 (it adds move-noise, it does not hang pieces), which is
// why a "600" bot felt like a 1000. So below club strength the bot ALSO plays a
// random legal move some fraction of the time (`blunder`) — an actual blunder, the
// only way under Stockfish's floor. The rate is chosen, not calibrated (measuring a
// bot's Elo needs many games); what is certain is the direction — a random move at
// rate p strictly lowers move quality. The ≈ labels are estimates, as before.
// Weak settings also answer fast: nobody wants a 600 that thinks for seconds.
const BOT_LEVELS = [
  { label: "≈ 400 · learning the moves", elo: 400, skill: 0, mt: 100, blunder: 0.35 },
  { label: "≈ 600 · beginner", elo: 600, skill: 0, mt: 120, blunder: 0.22 },
  { label: "≈ 800 · casual", elo: 800, skill: 0, mt: 150, blunder: 0.12 },
  { label: "≈ 1000 · improving", elo: 1000, skill: 3, mt: 200, blunder: 0.05 },
  { label: "≈ 1200 · club beginner", elo: 1200, skill: 6, mt: 250 },
  { label: "≈ 1400 · club player", elo: 1400, uciElo: 1400, mt: 300 },
  { label: "≈ 1700 · strong club", elo: 1700, uciElo: 1700, mt: 350 },
  { label: "≈ 2000 · expert", elo: 2000, uciElo: 2000, mt: 400 },
  { label: "≈ 2300 · master", elo: 2300, uciElo: 2300, mt: 500 },
  { label: "≈ 2700 · grandmaster", elo: 2700, uciElo: 2700, mt: 700 },
];

const botActive = () => !!(state.bot && !state.bot.over);
const botName = (bot) => "Stockfish (≈" + bot.lvl.elo + ")";

function setMode(mode) {
  if (mode === state.mode) {
    // Re-clicking "Play the engine" after a finished game brings the setup back.
    if (mode === "bot" && state.bot && state.bot.over) { state.bot = null; renderModeUi(); renderReadout(); }
    return;
  }
  if (botActive()) state.bot = null;          // switching modes abandons a live bot game
  state.mode = mode;
  document.querySelectorAll(".modetab").forEach((b) => b.classList.toggle("on", b.dataset.mode === mode));
  state.explore = null;
  el.exploreBar.classList.add("hidden");
  if (state.explain) exitExplain();
  renderModeUi();
  renderReadout();
  restartLive();
}

function renderModeUi() {
  // Book Coach is a different kind of view entirely (no board/engine chrome),
  // so it's handled as an early return rather than threading "book" through
  // every toggle below that assumes analyze/solo/bot semantics.
  const workspaceEl = document.getElementById("workspace");
  const bookRoot = document.getElementById("bookCoachRoot");
  if (bookRoot) bookRoot.classList.toggle("hidden", state.mode !== "book");
  if (workspaceEl) workspaceEl.classList.toggle("hidden", state.mode === "book");
  if (state.mode === "book") {
    import("./integration/book-coach-entry.js").then(({ mountBookCoach, isBookCoachMounted }) => {
      if (!isBookCoachMounted()) mountBookCoach(bookRoot);
    });
    return;
  }
  const active = botActive();
  const silent = quiet();      // a bot game or an unsolved training position: no engine voice at all
  document.querySelector(".import").classList.toggle("hidden", state.mode !== "analyze");
  el.playSetup.classList.toggle("hidden", state.mode !== "bot" || !!state.bot);
  el.playBar.classList.toggle("hidden", state.mode === "analyze" || (state.mode === "bot" && !state.bot));
  el.soloReset.classList.toggle("hidden", state.mode !== "solo");
  el.botResign.classList.toggle("hidden", !active);
  el.botRematch.classList.toggle("hidden", !(state.mode === "bot" && state.bot && state.bot.over));
  // Competitive silence: while a bot game is on, every engine voice is off.
  el.live.classList.toggle("hidden", silent);
  document.querySelector(".evalbar").classList.toggle("hidden", silent);
  el.reviewBtn.disabled = !state.moves.length || !state.booted || active;
  if (state.mode === "solo") {
    el.playTxt.innerHTML = "<b>Free board</b> — you move both sides, and every move joins the game.";
  } else if (state.mode === "bot" && state.bot) {
    el.playTxt.innerHTML = state.bot.over
      ? "<b>" + esc(state.bot.note || "Game over") + "</b> — the review is unlocked."
      : "Playing <b>" + esc(botName(state.bot)) + "</b> as " + (state.bot.color === "w" ? "White" : "Black") + ".";
  }
  refreshExplorer();   // hide it during a live bot game, bring it back when one ends
  syncChrome();
}

function startBot() {
  if (!state.booted) return;
  const lvl = BOT_LEVELS[+el.botElo.value] || BOT_LEVELS[3];
  const color = state.botPick;
  state.bot = { color, lvl, thinking: false, over: false, note: null };
  loadGame({
    headers: {
      White: color === "w" ? "You" : botName(state.bot),
      Black: color === "b" ? "You" : botName(state.bot),
      Date: new Date().toISOString().slice(0, 10).replace(/-/g, "."),
      Result: "*",
    },
    moves: [], startFen: DEFAULT_FEN,
  });
  state.flip = color === "b";
  renderModeUi();
  drawBoard();
  renderReadout();
  if (color === "b") botMove();
}

// A uniformly random legal move (UCI), for the weak-bot blunder path. Reads the
// position only — never the engine — so it is instant, which also reads right: a
// beginner's blunder comes fast, not after a long think.
function randomLegalMove(fen) {
  const c = new Chess(fen);
  const ms = c.moves({ verbose: true });
  if (!ms.length) return null;
  const m = ms[Math.floor(Math.random() * ms.length)];
  return m.from + m.to + (m.promotion || "");
}

async function botMove() {
  const bot = state.bot;
  if (!bot || bot.over || bot.thinking) return;
  bot.thinking = true;
  renderReadout();
  const fen = state.moves.length ? state.moves[state.moves.length - 1].fenAfter : state.startFen;
  let uci = null;
  try {
    // Beginner tiers drop a real blunder some fraction of the time (a random legal
    // move), because Skill 0 alone floors around 1000 and never hangs a piece. The
    // randomness lives ONLY here, in bot play — analyse()/live() still assert full
    // strength before every search, so no evaluation is ever weakened.
    const bl = bot.lvl.blunder || 0;
    if (bl > 0 && Math.random() < bl) uci = randomLegalMove(fen);
    if (!uci) uci = await state.engine.play(fen, { uciElo: bot.lvl.uciElo, skill: bot.lvl.skill, movetime: bot.lvl.mt });
  } catch (e) { /* a dead engine just never answers; the game simply stalls visibly */ }
  bot.thinking = false;
  if (state.bot !== bot || bot.over) return;    // resigned / abandoned while it thought
  if (uci) commitMove(uci.slice(0, 2), uci.slice(2, 4), uci.slice(4, 5) || null, true);
  renderReadout();
}

// Play a move INTO the game (free board and bot games) rather than into an
// exploration branch: the move list grows, the review is invalidated, and — on the
// free board only — moving from an earlier position rewrites the game from there.
function commitMove(from, to, promo, animate) {
  if (state.ply < state.moves.length) {
    if (state.mode === "bot") { goto(state.moves.length); return false; }  // move at the end
    state.moves = state.moves.slice(0, state.ply);
  }
  const fen = state.moves.length ? state.moves[state.moves.length - 1].fenAfter : state.startFen;
  const c = new Chess(fen);
  let m;
  try { m = c.move({ from, to, promotion: promo || "q" }); }
  catch (e) { return false; }
  if (!m) return false;
  invalidateReview();
  state.moves.push({
    san: m.san, from: m.from, to: m.to, uci: m.from + m.to + (m.promotion || ""),
    color: m.color, fenBefore: fen, fenAfter: c.fen(),
    // the FEN's own fullmove counter, so a game grown from a FEN numbers correctly
    moveNo: parseInt(fen.split(" ")[5] || "1", 10),
  });
  if (state.training) evaluateTrainingMove(m);   // ?coach=v2 training attempt in progress
  el.pgnInput.value = gamePgn();   // sharing / re-importing works like a pasted game
  renderMoveList();
  renderShareBar();
  renderModeUi();                  // the first committed move unlocks Analyze (solo)
  goto(state.moves.length);
  if (botActive()) afterBotPly(c);
  return true;
}

// A committed move ended a review's validity: the game it reviewed no longer exists.
function invalidateReview() {
  if (!state.reviewed && !state.review) return;
  state.reviewed = false;
  state.review = null;
  el.summary.classList.add("hidden");
  el.accStrip.classList.add("hidden");
  el.phases.classList.add("hidden");
  el.graphCard.classList.add("hidden");
  el.timeCard.classList.add("hidden");
  el.cardBtn.classList.add("hidden");
  el.cardCopyBtn.classList.add("hidden");
  window.__card = null;
}

// After any committed ply of a bot game: is it over, and whose turn is it?
function afterBotPly(c) {
  if (!botActive()) return;
  const bot = state.bot;
  if (c.isGameOver()) {
    let result = "1/2-1/2", note = "Draw";
    if (c.isCheckmate()) {
      const winner = c.turn() === "w" ? "b" : "w";
      result = winner === "w" ? "1-0" : "0-1";
      note = (winner === bot.color ? "You won" : "Stockfish won") + " by checkmate";
    } else if (c.isStalemate()) note = "Draw by stalemate";
    else if (c.isThreefoldRepetition()) note = "Draw by repetition";
    else if (c.isInsufficientMaterial()) note = "Draw — insufficient material";
    endBotGame(result, note);
  } else if (c.turn() !== bot.color) {
    botMove();
  }
}

function endBotGame(result, note) {
  const bot = state.bot;
  if (!bot || bot.over) return;
  bot.over = true;
  bot.note = note;
  state.headers.Result = result;
  state.headers.Termination = note;
  el.pgnInput.value = gamePgn();
  renderHeader();
  renderModeUi();     // review button unlocks, eval bar and live panel come back
  renderReadout();
  renderShareBar();
  restartLive();
}

// A PGN of the game grown on the board, so share links and re-imports just work.
function gamePgn() {
  const h = state.headers || {};
  const tags = [];
  for (const k of ["White", "Black", "Date", "Result", "Termination"]) {
    if (h[k]) tags.push("[" + k + ' "' + String(h[k]).replace(/"/g, "") + '"]');
  }
  if (state.startFen !== DEFAULT_FEN) tags.push('[SetUp "1"]', '[FEN "' + state.startFen + '"]');
  let body = "";
  state.moves.forEach((m, i) => {
    if (m.color === "w") body += (body ? " " : "") + m.moveNo + ". " + m.san;
    else body += (i === 0 ? m.moveNo + "... " : " ") + m.san;
  });
  if (h.Result && h.Result !== "*") body += (body ? " " : "") + h.Result;
  return tags.join("\n") + "\n\n" + body + "\n";
}

// ---------- live engine ----------
// Debounced + generation-guarded so rapid navigation never overlaps engine
// searches (overlapping stop/position/go corrupts the WASM engine).
let liveGen = 0;
let liveTimer = null;
// ---------- opening explorer / endgame tablebase (js/explorer.js) ----------
// A bonus panel: what humans play here (Lichess DB), or perfect play once the board
// is down to seven pieces (tablebase). It steps aside without a fuss when offline.
let explorerTimer = null, explorerGen = 0;
const explorerCache = new Map();   // "fen|band" -> normalized result, for this session

function explorerVisible() {
  // Silent during a competitive bot game and in a hidden tab — the same courtesies the
  // live engine panel keeps — and on the bare opening board with nothing loaded. A game,
  // an exploration line, or a position pasted as a FEN all count as something to look up.
  if (!state.booted || document.hidden || botActive()) return false;
  return state.moves.length > 0 || !!state.explore || state.startFen !== DEFAULT_FEN;
}

function refreshExplorer() {
  clearTimeout(explorerTimer);
  const gen = ++explorerGen;
  if (!explorerVisible()) { el.explorerCard.classList.add("hidden"); return; }
  const fen = currentFen();
  const band = RATING_BANDS.find((b) => b.id === state.explorerBand) || RATING_BANDS[1];
  const key = fen + "|" + band.id;
  if (explorerCache.has(key)) { renderExplorer(explorerCache.get(key), fen); return; }
  // Debounce: arrowing quickly through a game must not fire a request per ply.
  explorerTimer = setTimeout(async () => {
    if (gen !== explorerGen) return;
    el.explorerCard.classList.remove("hidden");
    el.explorerBody.innerHTML = '<div class="exloading">Looking it up…</div>';
    el.explorerNote.textContent = "";
    try {
      const data = await lookupPosition(fen, { ratings: band.ratings });
      explorerCache.set(key, data);
      if (gen === explorerGen) renderExplorer(data, fen);
    } catch (e) {
      if (gen === explorerGen) el.explorerCard.classList.add("hidden");   // a bonus, so it just leaves
    }
  }, 260);
}

const pct = (x) => Math.round(x * 100);
const fmtCount = (n) => (n >= 10000 ? Math.round(n / 1000) + "k" : n >= 1000 ? (n / 1000).toFixed(1) + "k" : String(n));

function renderExplorer(data, fen) {
  el.explorerCard.classList.remove("hidden");
  if (data.kind === "tablebase") renderTablebase(data, fen);
  else renderOpeningExplorer(data, fen);
  el.explorerBody.querySelectorAll(".exrow").forEach((btn) =>
    (btn.onclick = () => playLine(fen, [btn.dataset.uci])));   // click a move = play it on the board
}

function renderOpeningExplorer(data, fen) {
  el.explorerTitle.textContent = "Opening explorer";
  el.explorerRating.style.visibility = "visible";
  if (!data.total || !data.moves.length) {
    el.explorerBody.innerHTML = "";
    el.explorerNote.textContent = "No games at this position in that rating band.";
    return;
  }
  el.explorerBody.innerHTML = data.moves.slice(0, 8).map((m) =>
    '<button class="exrow" data-uci="' + m.uci + '">' +
      '<span class="exsan">' + esc(m.san) + "</span>" +
      '<span class="exshare">' + pct(m.share) + "%</span>" +
      '<span class="wdl"><i class="w" style="width:' + pct(m.white) + '%"></i>' +
        '<i class="d" style="width:' + pct(m.draws) + '%"></i>' +
        '<i class="b" style="width:' + pct(m.black) + '%"></i></span>' +
      '<span class="excount">' + fmtCount(m.total) + "</span></button>").join("");
  const op = data.opening ? esc(data.opening.name) + " · " : "";
  el.explorerNote.textContent = op + "bars are white / draw / black results; % is how often the move is played here.";
}

const TB_LABEL = { win: "Winning", loss: "Losing", draw: "Drawn",
  "cursed-win": "Winning (50-move)", "blessed-loss": "Losing (50-move)",
  "maybe-win": "Winning", "maybe-loss": "Losing", unknown: "Unknown" };

function renderTablebase(data, fen) {
  el.explorerTitle.textContent = "Endgame tablebase";
  el.explorerRating.style.visibility = "hidden";   // rating is irrelevant to perfect play
  const verdict = data.checkmate ? "Checkmate" : data.stalemate ? "Stalemate"
    : (TB_LABEL[data.category] || "Unknown");
  const dtz = (data.dtz != null && !data.checkmate && !data.stalemate)
    ? ' <span class="dim">· ' + Math.abs(data.dtz) + " to zeroing</span>" : "";
  const rows = data.moves.map((m) =>
    '<button class="exrow tb" data-uci="' + m.uci + '">' +
      '<span class="exsan">' + esc(m.san) + "</span>" +
      '<span class="tbres ' + (m.result || "") + '">' + (TB_LABEL[m.result] || m.result || "") + "</span>" +
      (m.dtz != null ? '<span class="excount">' + Math.abs(m.dtz) + "</span>" : "") +
    "</button>").join("");
  el.explorerBody.innerHTML =
    '<div class="tbverdict ' + (data.category || "") + '">' + verdict + dtz + "</div>" + rows;
  el.explorerNote.textContent = "Perfect play, from Lichess's 7-piece tablebase. Distance is to the next pawn move or capture, not to mate.";
}

function initExplorerUi() {
  el.explorerRating.innerHTML = RATING_BANDS.map((b) =>
    '<option value="' + b.id + '">' + b.label + "</option>").join("");
  el.explorerRating.value = state.explorerBand;
  el.explorerRating.onchange = () => {
    state.explorerBand = el.explorerRating.value;
    try { localStorage.setItem("ca_explorer_band", state.explorerBand); } catch (e) { /* private mode */ }
    refreshExplorer();
  };
}

// ---------- visual position editor / confirm-board (fed by js/boardscan.js) ----------
// The always-correct half of screenshot import: whatever the scan guesses, you land
// here to fix any square before analysing. Useful on its own too — set up any position
// by hand, which pasting a FEN string never made pleasant.
const EDIT_PIECES = ["K", "Q", "R", "B", "N", "P", "k", "q", "r", "b", "n", "p"];
function fenToGrid(fen) {
  return fen.split(" ")[0].split("/").map((fr) => {
    const a = [];
    for (const ch of fr) { if (/\d/.test(ch)) for (let i = 0; i < +ch; i++) a.push(null); else a.push(ch); }
    return a;
  });
}
const emptyGrid = () => Array.from({ length: 8 }, () => Array(8).fill(null));

function openEditor(grid, note) {
  state.editor = { grid: grid.map((r) => r.slice()), stm: "w", flip: false, brush: "P" };
  el.editNote.textContent = note ||
    "Pick a piece, then click squares to place it. Choose ⌫ to erase. Set who is to move, then analyze.";
  el.edErr.classList.add("hidden");
  el.editorCard.classList.remove("hidden");
  renderPalette();
  renderEditor();
  el.editorCard.scrollIntoView({ block: "nearest", behavior: "smooth" });
}
function closeEditor() { state.editor = null; el.editorCard.classList.add("hidden"); }

function renderPalette() {
  const ed = state.editor;
  const mk = (code) => {
    const b = document.createElement("button");
    b.className = "palp" + (ed.brush === code ? " on" : "");
    b.dataset.code = code;
    if (code === "") { b.classList.add("eraser"); b.textContent = "⌫"; b.title = "Erase"; }
    else {
      const pc = document.createElement("div");
      pc.className = "pc";
      pc.style.backgroundImage = "url('vendor/pieces/cburnett/" +
        (code === code.toUpperCase() ? "w" : "b") + code.toUpperCase() + ".svg')";
      b.appendChild(pc);
    }
    b.onclick = () => { state.editor.brush = code; renderPalette(); };
    return b;
  };
  el.palette.innerHTML = "";
  for (const c of EDIT_PIECES) el.palette.appendChild(mk(c));
  el.palette.appendChild(mk(""));   // eraser
}
function renderEditor() {
  const ed = state.editor;
  renderBoard(el.editorBoard, gridToFen(ed.grid, ed.stm), { flip: ed.flip, onSquareClick: stampSquare });
  el.edWhite.classList.toggle("on", ed.stm === "w");
  el.edBlack.classList.toggle("on", ed.stm === "b");
}
function stampSquare(name) {
  const ed = state.editor;
  const c = name.charCodeAt(0) - 97, r = 8 - +name[1];
  ed.grid[r][c] = ed.brush === "" ? null : ed.brush;
  el.edErr.classList.add("hidden");
  renderEditor();
}
function analyzeEditor() {
  const ed = state.editor;
  const fen = gridToFen(ed.grid, ed.stm);
  try { new Chess(fen); }
  catch (e) {
    const msg = /king/i.test(e.message || "") ? "each side needs exactly one king."
      : (e.message || "check the pieces.").replace(/^.*FEN:\s*/i, "");
    el.edErr.textContent = "That position isn't legal — " + msg;
    el.edErr.classList.remove("hidden");
    return;
  }
  const flip = ed.flip;
  el.fenInput.value = fen;
  closeEditor();
  loadGame({ headers: { White: "White", Black: "Black" }, moves: [], startFen: fen });
  state.flip = flip;
  drawBoard();
}

// Read a chosen / pasted image, run the recognizer, and open the confirm-board on its
// guess. Every failure still lands on the editor, so the feature never dead-ends.
async function handleScanFile(file) {
  if (!file) return;
  const url = URL.createObjectURL(file);
  try {
    const img = await new Promise((res, rej) => {
      const im = new Image(); im.onload = () => res(im); im.onerror = rej; im.src = url;
    });
    const scan = await scanBoard(img);
    if (!scan.plausible) {
      // A garbage read (uncropped screenshot, a piece set we don't have): don't prefill
      // 64 wrong squares — start empty and say plainly what a readable image looks like.
      openEditor(emptyGrid(),
        "Couldn't read that image. It needs to be cropped to JUST the 8×8 board — no app window, coordinates ring, or borders. Try a tighter crop, or build the position by hand below.");
      return;
    }
    openEditor(scan.grid,
      "Read " + scan.occupied + " pieces. Fix any square it got wrong, set who's to move, then analyze.");
  } catch (e) {
    openEditor(emptyGrid(), "Couldn't read that image. Set the position up by hand, then analyze.");
  } finally {
    URL.revokeObjectURL(url);
  }
}

function restartLive() {
  clearTimeout(liveTimer);
  // The human-move panel follows the same board position, but not the engine on/off
  // toggle — someone who muted the engine may still want the opening stats — so it
  // refreshes here, before the live-engine guard below.
  refreshExplorer();
  // botActive: no engine commentary during a competitive game.
  if (!state.booted || !state.live || state.reviewing || document.hidden || quiet()) return;
  const gen = ++liveGen;
  liveTimer = setTimeout(async () => {
    if (gen !== liveGen || state.reviewing || !state.live || document.hidden) return;
    const fen = currentFen();
    setLiveBadge("analyzing");
    await state.engine.stopLive();          // fully settle the previous search
    if (gen !== liveGen || state.reviewing) return; // superseded / review started while stopping
    await state.engine.live(fen, {
      multipv: state.liveLines,
      depth: LIVE_DEPTH,
      onUpdate: (lines) => { if (gen === liveGen) renderLive(fen, lines); },
    });
  }, 90);
}

// A tab you are not looking at must not analyse. Even a depth-capped search restarts
// on every navigation, and a background tab left open on a game was the other half of
// the "laptop is hot" complaint. Picks straight back up when you return.
document.addEventListener("visibilitychange", () => {
  if (document.hidden) {
    clearTimeout(liveTimer); liveGen++;     // cancel anything pending
    if (state.engine) state.engine.stopLive();
  } else {
    restartLive();
  }
});
let lastEngineArrowKey = "";
function setLiveBadge(kind) {
  const b = el.liveBadge;
  if (!b) return;
  const map = { ready: ["READY", "neutral"], analyzing: ["ANALYZING", "warn live"], off: ["ENGINE OFF", "neutral"], on: ["ENGINE ON", "ok"] };
  const [txt, cls] = map[kind] || map.ready;
  b.textContent = txt;
  b.className = "bdg " + cls;
}
function renderLive(fen, lines) {
  if (!lines.length) return;
  const top = lines[0];
  el.liveDepth.textContent = "depth " + top.depth + (top.seldepth ? "/" + top.seldepth : "");
  el.liveEval.textContent = fmtEval(top.cp, top.mate);
  el.liveEval.className = "mono " + (wpFromNode(top.cp, top.mate) >= 50 ? "pos" : "neg");
  setLiveBadge(top.depth >= LIVE_DEPTH ? "ready" : "analyzing");
  // fill eval bar live only when not showing reviewed eval
  if (!(state.reviewed && state.ply > 0 && !state.explore)) updateEvalBar(top.cp, top.mate);
  el.liveLinesBox.innerHTML = "";
  for (const ln of lines) {
    const sans = pvToSan(fen, ln.pv);
    const div = document.createElement("div");
    div.className = "liveline";
    div.title = "Play the next move of this line";
    div.innerHTML =
      '<span class="lev">' + fmtEval(ln.cp, ln.mate) + "</span>" +
      '<span class="lpv">' + formatPvSan(fen, sans) + "</span>";
    const pv = ln.pv.slice();
    div.addEventListener("click", () => playLine(fen, pv));
    el.liveLinesBox.appendChild(div);
  }
  // Engine arrows: the top line firm, the others faint. Only the arrow layer is repainted, and only
  // when the moves actually changed, so a search that keeps refining the same idea doesn't flicker.
  const arrows = lines.filter((l) => l.pv && l.pv[0]).slice(0, 3)
    .map((l, i) => ({ from: l.pv[0].slice(0, 2), to: l.pv[0].slice(2, 4), role: i === 0 ? "best" : "pv" }));
  const key = fen + "|" + arrows.map((a) => a.from + a.to + a.role).join(",");
  if (key !== lastEngineArrowKey) {
    lastEngineArrowKey = key;
    state.engineArrows = { fen, arrows };
    if (state.engineArrowsOn && !quiet() && !state.explain && !state.explore) repaintArrows();
  }
}

// ---------- review ----------
async function runReview() {
  if (!state.moves.length || !state.booted || state.reviewing || botActive()) return;

  // A review is a pure function of (game, depth, engine), so the same game at the same
  // depth never has to be analysed twice. Re-opening a game used to re-run ~100 engine
  // searches; now it comes back instantly.
  const key = reviewKey({
    startFen: state.startFen, moves: state.moves,
    depth: state.reviewDepth,
    engine: state.engine.name + (USE_GAME_ANALYZER ? "|game-analyzer-v2" : ""),
  });
  const cached = await getCached(key);
  if (cached) {
    applyReview(cached, true);
    // A cached review skips the engine entirely, but the domain report is a
    // cheap pure reshape of it (see buildReportFromLegacyReview) - rebuild it
    // so the AI Coach / Training panels stay in sync with whichever game is
    // actually on screen, cached or freshly analyzed.
    if (USE_GAME_ANALYZER) {
      const report = createGameAnalyzer({}).buildReportFromLegacyReview({ game: state.headers, legacyReview: cached });
      applyDomainReport(report, key);
    }
    return;
  }

  state.reviewing = true;
  clearTimeout(liveTimer); liveGen++;   // cancel any pending live search
  state.cancel = { cancelled: false };
  el.reviewLabel.textContent = "Cancel";
  el.reviewBtn.classList.add("cancel");
  el.progress.classList.remove("hidden");
  await state.engine.stopLive();

  // Spin the pool up for this review only. The live engine is the first member, so we
  // only pay to boot the extras — and the wasm is already compiled and cached by now,
  // so that costs ~20ms each.
  const extras = [];
  for (let i = 1; i < poolSize(); i++) extras.push(new Engine(ENGINE_URL()));
  await Promise.all(extras.map((e) => e.boot().catch(() => null)));
  const pool = [state.engine, ...extras.filter((e) => e.booted)];

  const total = state.moves.length + 1;
  let res = null;
  let domainReport = null;   // populated only when USE_GAME_ANALYZER succeeds
  try {
    const reviewOptions = {
      depth: state.reviewDepth,
      onProgress: (d) => {
        const pct = Math.round((d / total) * 100);
        el.progressBar.style.transform = "scaleX(" + pct / 100 + ")";
        el.progressTxt.textContent = "Analyzing " + d + " / " + total + " positions (depth " +
          state.reviewDepth + (pool.length > 1 ? ", " + pool.length + " engines" : "") + ")";
      },
      signal: state.cancel,
    };

    if (USE_GAME_ANALYZER) {
      try {
        // GameAnalyzer accepts the existing review engine pool and delegates to
        // the same reviewGame() implementation used by the legacy path.
        const analyzer = createGameAnalyzer({ engine: pool });
        const report = await analyzer.analyzeGame({
          game: state.headers,
          moves: state.moves,
          startFen: state.startFen,
          depth: reviewOptions.depth,
          onProgress: reviewOptions.onProgress,
          signal: reviewOptions.signal,
        });
        res = report ? report.legacyReview : null;
        domainReport = report;
      } catch (err) {
        console.warn("GameAnalyzer integration failed; falling back to legacy review.", err);
        res = await reviewGame(pool, state.moves, state.startFen, reviewOptions);
      }
    } else {
      res = await reviewGame(pool, state.moves, state.startFen, reviewOptions);
    }
  } finally {
    // Always tear the extras down — cancelled, crashed or finished. Leaking six engines
    // would hand the user back a machine holding hundreds of idle MB.
    for (const e of extras) e.quit();
  }

  state.reviewing = false;
  el.reviewLabel.textContent = "Analyze game";
  el.reviewBtn.classList.remove("cancel");
  el.progress.classList.add("hidden");
  el.progressBar.style.transform = "scaleX(0)";
  if (!res) { restartLive(); return; }
  // Only a COMPLETE review is worth remembering — a cancelled one returns null above.
  // The pool size is deliberately NOT in the cache key: a review is now bit-identical
  // on one engine or eight, so a cached result stays valid on any machine.
  putCached(key, res);
  applyReview(res, false);
  if (USE_GAME_ANALYZER && domainReport) applyDomainReport(domainReport, key);
}

// Fold a freshly-built or reconstructed GameAnalyzer report (game-analyzer.js)
// into the session PlayerModel, derive the structured Coach report and the
// training queue from it, and render both panels. `key` is the review cache
// key; it double as the PlayerModel de-duplication key, so re-opening the
// same cached review (goto-ing back to a game already analyzed this
// session) doesn't count it into the player's history twice.
function applyDomainReport(report, key) {
  state.report = report;
  if (!report) {
    state.coachReport = null;
    state.trainingItems = [];
    renderCoachV2();
    renderTraining();
    return;
  }
  if (state.playerModel && key && !state.ingestedReviewKeys.has(key)) {
    state.ingestedReviewKeys.add(key);
    state.playerModel.ingestReport(report, { gameId: key });
  }
  state.coachReport = buildCoachReport(report, state.playerModel);
  state.trainingItems = generateTrainingItems(report, { maxItems: 8 });
  renderCoachV2();
  renderTraining();
}

// Jump the board to the ply a GameAnalyzer move record came from. The move
// objects inside report.criticalPositions (and therefore coachReport's
// criticalMistakes) are the SAME object instances as state.moves' elements -
// buildReportFromLegacyReview() reshapes legacyReview.moves without cloning
// them - so locating one by reference is exact, not a fuzzy FEN/SAN match.
function jumpToReportMove(move) {
  if (!move) return;
  const idx = state.moves.indexOf(move);
  if (idx >= 0) goto(idx + 1);
}

// ---------- AI Coach panel (?coach=v2) ----------
function setRightTab(tab) {
  el.rightCol.dataset.tab = tab;
  document.querySelectorAll(".rtab").forEach((b) => {
    const on = b.dataset.rtab === tab;
    b.classList.toggle("on", on);
    b.setAttribute("aria-selected", String(on));
  });
}

function syncRightTabs() {
  const has = !!(state.trainingItems && state.trainingItems.length);
  el.rightTabs.classList.toggle("hidden", !has);
  el.trainCount.textContent = has ? String(state.trainingItems.length) : "";
  if (!has) setRightTab("coach");
}

// A collapsible coach section: icon + colour + label + count, so a section is recognisable
// by any one of the three. Progressive disclosure — the summary and the mistakes worth
// fixing are open, the rest is one click away.
function cv2Section(key, iconName, title, count, body, open) {
  return '<details class="cv2-sec" data-sec="' + key + '"' + (open ? " open" : "") + ">" +
    '<summary><span class="secic">' + icon(iconName) + '</span><span class="sech">' + esc(title) + "</span>" +
    (count != null ? '<span class="seccount">' + count + "</span>" : "") +
    '<span class="chev">' + icon("down") + "</span></summary>" +
    '<div class="secbody">' + body + "</div></details>";
}
const bullets = (arr) => '<ul class="cv2-list">' + arr.map((x) => "<li>" + x + "</li>").join("") + "</ul>";
const critLabel = (m) => m.moveNo + (m.color === "w" ? "." : "...") + m.san;

// Drives the Magnus coach bubble (js/integration/magnus-coach-bubble.js) from
// the same coach report renderCoachV2() already has — no separate evidence
// fetch, no new state. Picks the single most useful thing to say: the worst
// classification among this game's critical mistakes, or a good-game line
// when there aren't any.
function updateMagnusBubble(cr) {
  const mount = document.getElementById("magnusBubbleMount");
  if (!mount) return;
  const severity = { blunder: 3, mistake: 2, inaccuracy: 1 };
  let worst = null;
  for (const m of cr.criticalMistakes || []) {
    if (severity[m.cls] && (!worst || severity[m.cls] > severity[worst])) worst = m.cls;
  }
  const bubbleState = worst || (cr.strengths && cr.strengths.length ? "good_move" : "main");
  renderMagnusBubble({ state: bubbleState }, mount);
}

function renderCoachV2() {
  if (!USE_COACH_V2 || !el.coachV2Card) return;
  const cr = state.coachReport;
  if (!cr) {
    el.coachV2Card.classList.add("hidden");
    const mount = document.getElementById("magnusBubbleMount");
    if (mount) renderMagnusBubble({ visible: false }, mount);
    syncRightTabs();
    return;
  }
  el.coachV2Card.classList.remove("hidden");

  const parts = [];
  // SUMMARY: the numbers first, the opening beneath.
  parts.push(cv2Section("summary", "list", "Game summary", null,
    '<div class="cv2-stats">' +
      '<div class="cv2-stat"><b>' + cr.summary.totalMoves + "</b><span>Moves analyzed</span></div>" +
      '<div class="cv2-stat"><b>' + cr.summary.averageLoss + "%</b><span>Average loss</span></div>" +
    "</div>" +
    (cr.summary.opening ? '<p class="cv2-p"><b>Opening:</b> ' + esc(String(cr.summary.opening).replace(/^([A-E]\d\d),\s*/, "$1 · ")) + "</p>" : ""), true));

  // CRITICAL MISTAKES: the most actionable thing on the screen — each one a button that jumps to the position.
  if (cr.criticalMistakes.length) {
    const rows = cr.criticalMistakes.map((m, i) => {
      const cls = CLASSES[m.cls] ? m.cls : "blunder";
      const cl = CLASSES[cls];
      return '<button type="button" class="cv2-critbtn" data-idx="' + i + '" style="--c:var(' + cl.v + ')" ' +
        'aria-label="' + esc(cl.label + ", " + critLabel(m) + ", lost " + Math.round(m.loss || 0) + " percent. Click to inspect.") + '">' +
        '<span class="cg">' + glyphSvg(cls) + "</span>" +
        '<span class="crit-main"><b>' + esc(critLabel(m)) + "</b><small>" + (m.color === "w" ? "White" : "Black") + " · click to inspect</small></span>" +
        '<span class="bdg" style="--c:var(' + cl.v + ')">' + esc(cl.label) + "</span>" +
        '<span class="cv2-loss">−' + Math.round(m.loss || 0) + "%</span></button>";
    }).join("");
    parts.push(cv2Section("critical", "warning", "Critical mistakes", cr.criticalMistakes.length, '<div class="cv2-crit">' + rows + "</div>", true));
  }
  if (cr.weaknesses.length) parts.push(cv2Section("weaknesses", "warning", "Weaknesses", cr.weaknesses.length, bullets(cr.weaknesses.map((w) => esc(w.detail))), true));
  if (cr.strengths.length) parts.push(cv2Section("strengths", "check", "Strengths", cr.strengths.length, bullets(cr.strengths.map((x) => esc(x.detail))), false));
  if (cr.recurringPatterns.length) parts.push(cv2Section("concepts", "chart", "Recurring patterns", cr.recurringPatterns.length, bullets(cr.recurringPatterns.map((p) => esc(p.detail))), false));
  if (cr.concepts.length) parts.push(cv2Section("concepts", "book", "Concepts", cr.concepts.length,
    bullets(cr.concepts.map((c) => "<b>" + esc(String(c.concept).replace(/-/g, " ")) + ":</b> " + esc(c.explanation))), false));
  if (cr.recommendations.length) parts.push(cv2Section("recs", "target", "Recommendations", cr.recommendations.length, bullets(cr.recommendations.map((r) => esc(r.detail))), true));
  if (cr.questions.length) parts.push(cv2Section("questions", "info", "Questions to think about", cr.questions.length,
    '<ul class="cv2-list cv2-questions">' + cr.questions.map((q, i) => '<li class="cv2-q" data-idx="' + i + '" tabindex="0" role="button">' + esc(q.question) + "</li>").join("") + "</ul>", false));

  el.coachV2Body.innerHTML = parts.join("");
  updateMagnusBubble(cr);
  el.coachV2Body.querySelectorAll(".cv2-critbtn").forEach((btn) => {
    btn.addEventListener("click", () => jumpToReportMove(cr.criticalMistakes[+btn.dataset.idx]));
  });
  // Questions are built from report.criticalPositions in the same order as
  // criticalMistakes (see src/chess/coach.js buildQuestions), so index i of
  // one pairs with index i of the other - no separate lookup needed.
  el.coachV2Body.querySelectorAll(".cv2-q").forEach((li) => {
    const go = () => jumpToReportMove(cr.criticalMistakes[+li.dataset.idx]);
    li.addEventListener("click", go);
    li.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { go(); e.preventDefault(); } });
  });
  syncRightTabs();
}

// ---------- Training ----------
// The queue lives in the right-hand column; an exercise opens in TRAINING MODE: the analysis
// panels step aside (body.training-mode), the board stays put, and the whole right-hand side
// becomes the exercise: task -> attempt -> verdict -> why -> idea -> pattern -> takeaway -> next.
const CONCEPT_ICON = { fork: "fork", pin: "pin", skewer: "skewer", "discovered-attack": "discovered", "double-attack": "double",
  "hung-piece": "warning", "allowed-mate": "mate", "missed-mate": "mate", "losing-exchange": "double", "missed-material": "target" };
const conceptIcon = (c) => CONCEPT_ICON[c] || "target";
const conceptLabel = (c) => String(c || "").replace(/-/g, " ");
const sideName = (c) => (c === "w" ? "White" : "Black");
const stripSan = (san) => String(san || "").replace(/[+#]/g, "");
const taskText = (item) => (item.task === "find-better-move" ? "Find the best move for " + sideName(item.color) + "." : "Spot the tactic for " + sideName(item.color) + ".");

function renderTraining() {
  if (!USE_COACH_V2 || !el.trainingCard) return;
  const items = state.trainingItems;
  if (!items || !items.length) { el.trainingCard.classList.add("hidden"); syncRightTabs(); return; }
  el.trainingCard.classList.remove("hidden");
  el.trainingBody.innerHTML =
    '<p class="train-lead">Practise the positions from this game. Each one is a position you actually reached.</p>' +
    items.map((item, i) =>
      '<div class="train-item">' +
        '<span class="train-ico">' + icon(conceptIcon(item.concept)) + "</span>" +
        '<div class="train-concept">' + esc(conceptLabel(item.concept)) +
          '<span class="bdg train-diff ' + (item.difficulty === "hard" ? "bad" : item.difficulty === "medium" ? "mistake" : "ok") + '">' + esc(item.difficulty) + "</span></div>" +
        '<div class="train-task">' + esc(taskText(item)) + "</div>" +
        '<button type="button" class="mini primary train-try" data-idx="' + i + '" aria-label="Try training position ' + (i + 1) + '">' + icon("play") + "Try it</button>" +
      "</div>").join("");
  el.trainingBody.querySelectorAll(".train-try").forEach((btn) => btn.addEventListener("click", () => startTraining(+btn.dataset.idx)));
  syncRightTabs();
}

function expectedMoveOf(item) {
  if (item.expectedFrom && item.expectedTo) return { from: item.expectedFrom, to: item.expectedTo, promo: item.expectedPromo || null };
  if (!item.expectedMove) return null;
  try { const m = new Chess(item.fen).move(item.expectedMove); return m ? { from: m.from, to: m.to, promo: m.promotion || null } : null; }
  catch (e) { return null; }
}

// Enter (or advance within) training mode: load the position, turn the board to the side
// that has to move, and hand the whole right-hand side to the exercise.
function startTraining(idx, opts = {}) {
  const item = state.trainingItems[idx];
  if (!item || !item.fen) return;
  const prev = state.training;
  if (!prev) {
    // Remember the game on screen so "Back to analysis" can bring it back exactly as it was.
    state.pausedGame = { headers: state.headers, moves: state.moves, startFen: state.startFen, mode: state.mode,
      ply: state.ply, flip: state.flip, reviewed: state.reviewed, tab: el.rightCol.dataset.tab };
  }
  state.overlay = null;
  clearUserDrawings();
  state.training = { idx, item, resolved: false, correct: null, phase: "task", attempt: null, hint: 0,
    checking: false, analysis: null, results: prev ? prev.results : {}, token: 0 };
  loadGame({ headers: { White: "Training", Black: "Training" }, moves: [], startFen: item.fen }, { keepDomainState: true });
  setMode("solo");
  state.flip = item.color === "b";
  document.body.classList.add("training-mode");
  renderModeUi();
  drawBoard();
  renderReadout();
  renderTrainingBanner();
  if (opts.focus !== false) el.trainBanner.scrollTop = 0;
}

function stopTraining() {
  const wasReviewed = state.pausedGame && state.pausedGame.reviewed;
  state.training = null;
  state.overlay = null;
  document.body.classList.remove("training-mode");
  el.trainBar.classList.add("hidden");
  el.trainBanner.classList.add("hidden");
  if (state.pausedGame) {
    const g = state.pausedGame;
    state.pausedGame = null;
    loadGame({ headers: g.headers, moves: g.moves, startFen: g.startFen }, { keepDomainState: true });
    setMode(g.mode || "analyze");
    state.flip = !!g.flip;
    goto(g.ply || 0);
    if (g.tab) setRightTab(g.tab);
    // loadGame drops the review overlay; re-running Analyze on it is instant (reviews are cached).
    if (wasReviewed) runReview();
  }
  renderModeUi();
  restartLive();
}

// ----- judging the attempt -----
const PIECE_VAL = { p: 1, n: 3, b: 3, r: 5, q: 9, k: 100 };

// WHY a move failed, from the position alone. Every sentence here is read off the board
// (an attacker, a defender, a move the review already named) — never guessed.
function whyAttemptFailed(item, at) {
  const reasons = [];
  if (item.playedMove && stripSan(item.playedMove) === stripSan(at.san) && item.explanation && item.explanation.motifText) {
    reasons.push(item.explanation.motifText);
  }
  try {
    const c = new Chess(at.fenAfter);
    const enemy = at.color === "w" ? "b" : "w";
    const piece = c.get(at.to);
    const atk = c.attackers(at.to, enemy).map((s) => ({ s, p: c.get(s) })).filter((x) => x.p)
      .sort((a, b) => PIECE_VAL[a.p.type] - PIECE_VAL[b.p.type]);
    if (piece && atk.length) {
      const defended = c.attackers(at.to, at.color).length > 0;
      const low = atk[0];
      const cheaper = PIECE_VAL[low.p.type] < PIECE_VAL[piece.type];
      if (!defended || cheaper) {
        reasons.push(at.san + " leaves the " + PIECE_NAME[piece.type] + " on " + at.to + " where the " + PIECE_NAME[low.p.type] + " on " + low.s +
          " can take it" + (!defended ? ", and nothing defends it." : ", and it is worth more than the piece that takes it."));
      }
    }
  } catch (e) { /* fall through to the generic line */ }
  if (/#$/.test(item.expectedMove || "")) reasons.push("There was a forced checkmate: " + item.expectedMove + ".");
  if (!reasons.length && item.expectedMove) {
    reasons.push(item.expectedMove + " was the engine's top choice here, and " + at.san + " doesn't do the same job.");
  }
  return reasons;
}

// The engine's verdict on the attempt: what the opponent can do now, and what it does to the
// evaluation (from the mover's side). Runs in the background; the panel says "checking" until it lands.
async function analyzeAttempt(t, at) {
  const tok = ++t.token;
  const item = t.item;
  let after = null, base = null;
  try {
    if (state.engine && state.booted) {
      after = await state.engine.analyse(at.fenAfter, { depth: 12, multipv: 1 });
      if (item.bestCpWhite == null && item.bestMateWhite == null) base = await state.engine.analyse(item.fen, { depth: 12, multipv: 1 });
    }
  } catch (e) { after = null; }
  if (state.training !== t || t.token !== tok) return;   // moved on while the engine thought
  const res = { ok: false };
  if (after && after.best) {
    res.ok = true;
    const sgn = at.color === "w" ? 1 : -1;
    const asMover = (cp, mate) => ({ cp: cp == null ? null : sgn * cp, mate: mate == null ? null : sgn * mate });
    res.attempt = asMover(after.best.cp, after.best.mate);
    const b = base && base.best ? base.best : null;
    const baseCp = b ? b.cp : item.bestCpWhite, baseMate = b ? b.mate : item.bestMateWhite;
    res.best = baseCp != null || baseMate != null ? asMover(baseCp, baseMate) : null;
    if (after.bestmove) {
      try {
        const c = new Chess(at.fenAfter);
        const r = c.move({ from: after.bestmove.slice(0, 2), to: after.bestmove.slice(2, 4), promotion: after.bestmove.slice(4, 5) || undefined });
        if (r) {
          res.reply = { san: r.san, from: r.from, to: r.to, captured: r.captured || null };
          const tac = detectTactics({ fenBefore: at.fenAfter, fenAfter: c.fen(), from: r.from, to: r.to, san: r.san });
          res.replyTactic = tac ? tac.primary : null;
        }
      } catch (e) { /* no reply to describe */ }
    }
  }
  t.checking = false;
  t.analysis = res;
  renderTrainingBanner();
}

// Called by commitMove() when a move is made while a training item is active.
function evaluateTrainingMove(m) {
  const t = state.training;
  if (!t || t.resolved || t.busyReplay) return;
  const item = t.item;
  const fenAfter = state.moves[state.moves.length - 1].fenAfter;
  const at = { san: m.san, from: m.from, to: m.to, color: m.color, fenBefore: item.fen, fenAfter };
  const exp = expectedMoveOf(item);
  const correct = exp ? (m.from === exp.from && m.to === exp.to) || stripSan(m.san) === stripSan(item.expectedMove) : null;
  t.resolved = true; t.correct = correct; t.attempt = at;
  t.results[t.idx] = correct;
  if (state.playerModel) state.playerModel.recordTrainingAttempt(item, { correct });

  if (correct === true) {
    t.phase = "correct";
    t.tactic = tacticOf(item.fen, m);
    const ov = t.tactic ? tacticOverlay(t.tactic, m.to) : { arrows: [], squares: [] };
    state.overlay = { fen: fenAfter, arrows: [...ov.arrows.map((a) => ({ ...a, role: "motif" })), { from: m.from, to: m.to, role: "correct" }],
      squares: [...ov.squares, { sq: m.to, role: "correct" }] };
  } else if (correct === false) {
    t.phase = "incorrect";
    t.checking = true;
    state.overlay = { fen: fenAfter, arrows: [{ from: m.from, to: m.to, role: "wrong" }], squares: [{ sq: m.to, role: "wrong" }] };
    analyzeAttempt(t, at);
  } else {
    t.phase = "played";    // identify-motif items have no single right move to mark
    t.tactic = tacticOf(item.fen, m);
    const ov = t.tactic ? tacticOverlay(t.tactic, m.to) : { arrows: [], squares: [] };
    state.overlay = { fen: fenAfter, arrows: ov.arrows.map((a) => ({ ...a, role: "motif" })), squares: ov.squares };
  }
  renderTrainingBanner();
}

// The named tactic a move creates, read from the real position it was played in.
function tacticOf(fenBefore, m) {
  try {
    const c = new Chess(fenBefore);
    const r = c.move({ from: m.from, to: m.to, promotion: m.promotion || m.promo || "q" });
    if (!r) return null;
    const t = detectTactics({ fenBefore, fenAfter: c.fen(), from: r.from, to: r.to, san: r.san });
    return t;
  } catch (e) { return null; }
}

// ----- the three things the panel can do besides wait for a move -----
function trainTryAgain() {
  const t = state.training; if (!t) return;
  startTraining(t.idx, { focus: false });
}
function trainNext() {
  const t = state.training; if (!t) return;
  const n = t.idx + 1;
  if (n < state.trainingItems.length) startTraining(n);
  else { t.phase = "done"; state.overlay = null; drawBoard(); renderTrainingBanner(); }
}
// Play the engine's answer on the board, and explain it with arrows to the real targets.
function trainShowExplanation() {
  const t = state.training; if (!t) return;
  const item = t.item, exp = expectedMoveOf(item);
  if (!exp) return;
  const keep = { idx: t.idx, results: t.results, attempt: t.attempt, analysis: t.analysis, correct: t.correct };
  loadGame({ headers: { White: "Training", Black: "Training" }, moves: [], startFen: item.fen }, { keepDomainState: true });
  setMode("solo");
  state.flip = item.color === "b";
  state.training = { ...t, phase: "explain", resolved: true, busyReplay: true, hint: t.hint, ...keep, checking: false };
  const nt = state.training;
  commitMove(exp.from, exp.to, exp.promo, true);
  nt.busyReplay = false;
  const played = state.moves[state.moves.length - 1];
  nt.tactic = tacticOf(item.fen, { from: exp.from, to: exp.to, promo: exp.promo });
  const ov = nt.tactic ? tacticOverlay(nt.tactic, exp.to) : { arrows: [], squares: [] };
  state.overlay = { fen: played.fenAfter, arrows: [...ov.arrows.map((a) => ({ ...a, role: "motif" })), { from: exp.from, to: exp.to, role: "correct" }],
    squares: [...ov.squares, { sq: exp.to, role: "correct" }] };
  drawBoard();
  renderTrainingBanner();
}
function trainHint() {
  const t = state.training; if (!t || t.resolved) return;
  t.hint = Math.min(2, t.hint + 1);
  const exp = expectedMoveOf(t.item);
  if (t.hint === 1 && exp) state.overlay = { fen: currentFen(), arrows: [], squares: [{ sq: exp.from, role: "hint" }] };
  drawBoard();
  renderTrainingBanner();
}

// ----- rendering the exercise -----
const fmtMoverEval = (e) => (e ? fmtEval(e.cp, e.mate) : "–");
function moverEvalValue(e) {   // a comparable number for "how much worse", mates counted as very large
  if (!e) return null;
  if (e.mate != null) return (e.mate > 0 ? 1 : -1) * (10000 - Math.abs(e.mate));
  return e.cp;
}

// A general lesson per pattern — pedagogy, not a claim about this position (those come from the board).
const TACTIC_TAKEAWAY = {
  fork: "Before you move a knight, count what it would attack from the new square. Two targets it can win is a fork.",
  "double-attack": "Look for a move that threatens two things at once: the opponent can only answer one.",
  "double-check": "Two checks at once can't be blocked or captured away, so the king must move. Look for them when a piece can uncover a line with check.",
  pin: "When a piece stands on a line with something more valuable behind it, pressure the piece in front — it can't leave.",
  skewer: "Line a bishop, rook or queen up against a valuable piece that has something worth taking behind it.",
  "discovered-attack": "When one of your pieces blocks your own bishop, rook or queen, moving it can create a second threat.",
};
function trainingPattern(t) {
  // The named pattern: a detected tactic wins; otherwise the review's own concept for the position.
  if (t.tactic) return { label: t.tactic.primary.label, icon: TACTIC_ICON[t.tactic.primary.kind] || "target", idea: t.tactic.primary.idea };
  const c = t.item.concept;
  if (MOTIF_CONCEPTS[c]) return { label: conceptLabel(c).toUpperCase(), icon: conceptIcon(c), idea: MOTIF_CONCEPTS[c] };
  return null;
}
function sansOfLine(fen, uci, max = 6) {
  try { return formatPvSan(fen, pvToSan(fen, uci, max)); } catch (e) { return ""; }
}

function renderTrainingBanner() {
  const t = state.training;
  const ban = el.trainBanner;
  if (!t) { ban.classList.add("hidden"); el.trainBar.classList.add("hidden"); return; }
  ban.classList.remove("hidden"); el.trainBar.classList.remove("hidden");
  const item = t.item, total = state.trainingItems.length;
  el.trainProg.textContent = (t.phase === "done" ? total : t.idx + 1) + " / " + total;
  ban.className = "card trainbanner st-" + (t.phase === "correct" ? "correct" : t.phase === "incorrect" ? "incorrect" : "task");

  const bar = '<div class="tr-progress" aria-hidden="true">' +
    state.trainingItems.map((_, i) => '<i class="' + (t.results[i] === true ? "done" : i === t.idx && t.phase !== "done" ? "now" : "") + '"></i>').join("") + "</div>";
  const meta = '<div class="tr-meta"><span class="bdg tactic">' + icon(conceptIcon(item.concept)) + esc(conceptLabel(item.concept)) + "</span>" +
    '<span class="bdg ' + (item.difficulty === "hard" ? "bad" : item.difficulty === "medium" ? "mistake" : "ok") + '">' + esc(item.difficulty) + "</span></div>";
  const pat = trainingPattern(t);
  const patternHtml = pat ? '<div class="tr-sec"><div class="tr-lab">Pattern</div><div class="tr-pattern"><span class="bdg tactic">' + icon(pat.icon) + esc(pat.label) + "</span></div></div>" : "";
  let html = "";

  if (t.phase === "done") {
    const done = Object.values(t.results), right = done.filter((r) => r === true).length, judged = done.filter((r) => r !== null).length;
    ban.className = "card trainbanner st-correct";
    html = '<div class="tr-verdict"><span class="tr-vico">' + icon("check") + '</span><div><div class="tr-vlabel">SESSION COMPLETE</div>' +
      '<div class="tr-vmove">' + right + " / " + Math.max(judged, 1) + " solved</div></div></div>" +
      '<div class="tr-sec"><p>You worked through every position from this game. Each one is a place you actually reached — the ones you missed are the ones worth another look.</p></div>' +
      bar + '<div class="tr-actions"><button class="primary" id="trBack">' + icon("prev") + 'Back to analysis</button></div>';
  } else if (t.phase === "task") {
    const ctx = [];
    if (item.task === "find-better-move") {
      ctx.push("From your game — move " + item.moveNumber + (item.explanation && item.explanation.phase ? ", " + item.explanation.phase : "") + ".");
      if (item.playedMove) ctx.push("You played " + item.playedMove + " here" + (item.explanation && item.explanation.classification ? " (" + item.explanation.classification + ")" : "") + ". What was better?");
    } else ctx.push("A tactical moment from your game (move " + item.moveNumber + "). Play the move you think matters.");
    const hintTxt = t.hint >= 2 ? (MOTIF_CONCEPTS[item.concept] || "Look for a forcing move: a check, a capture or a threat.") :
      t.hint === 1 ? "The highlighted piece is the one that moves." : "";
    html = meta + '<div class="tr-lab">Task</div><h2 class="tr-task">' + esc(taskText(item)) + "</h2>" +
      '<p class="tr-context">' + esc(ctx.join(" ")) + "</p>" +
      (hintTxt ? '<div class="tr-sec"><div class="tr-lab">Hint</div><p>' + esc(hintTxt) + "</p></div>" : "") + bar +
      '<div class="tr-actions"><button id="trHint" ' + (t.hint >= 2 ? "disabled" : "") + ">" + icon("hint") + (t.hint ? "More hint" : "Hint") + "</button>" +
      '<span class="grow2"></span><button id="trSkip">Skip' + icon("next") + "</button></div>";
  } else if (t.phase === "incorrect") {
    const at = t.attempt, an = t.analysis;
    const why = whyAttemptFailed(item, at);
    let consequence = "";
    if (t.checking) consequence = '<div class="tr-checking">Checking your move with the engine…</div>';
    else if (an && an.ok) {
      const bits = [];
      if (an.reply) {
        bits.push("The opponent's best reply is " + an.reply.san + (an.reply.captured ? ", capturing your " + PIECE_NAME[an.reply.captured] : "") + ".");
        if (an.replyTactic) bits.push(an.replyTactic.text);
      }
      consequence = bits.map((b) => "<p>" + esc(b) + "</p>").join("") || "<p>The engine found no single decisive reply.</p>";
    } else consequence = "<p>The engine wasn't available to check the consequence.</p>";
    let evalHtml = "";
    if (!t.checking && an && an.ok && an.attempt) {
      const a = moverEvalValue(an.attempt), b = moverEvalValue(an.best);
      evalHtml = '<div class="tr-sec"><div class="tr-lab">Evaluation</div><div class="tr-eval">' +
        (an.best ? "<span>" + esc(fmtMoverEval(an.best)) + '</span><span class="arrow">→</span>' : "") +
        "<span>" + esc(fmtMoverEval(an.attempt)) + "</span>" +
        (a != null && b != null && Math.abs(b - a) >= 10 ? '<span class="delta">' + (b - a > 0 ? "−" : "+") + (Math.abs(b - a) >= 5000 ? "mate" : (Math.abs(b - a) / 100).toFixed(1)) + "</span>" : "") +
        '</div><p class="sub">' + (an.best ? "Best move, then your move — " : "Your move — ") + "from " + sideName(item.color) + "'s side.</p></div>";
    }
    html = '<div class="tr-verdict"><span class="tr-vico">' + icon("cross") + '</span><div><div class="tr-vlabel">INCORRECT MOVE</div>' +
      '<div class="tr-vmove">' + esc(at.san) + "?</div></div></div>" +
      '<div class="tr-sec"><div class="tr-lab">Why?</div>' + why.map((w) => "<p>" + esc(w) + "</p>").join("") + "</div>" +
      '<div class="tr-sec"><div class="tr-lab">Consequence</div>' + consequence + "</div>" + evalHtml + bar +
      '<div class="tr-actions"><button class="primary" id="trAgain">' + icon("reset") + "Try again</button>" +
      (expectedMoveOf(item) ? '<button id="trExplain">' + icon("hint") + "Show explanation</button>" : "") +
      '<span class="grow2"></span><button id="trSkip">Continue' + icon("next") + "</button></div>";
  } else if (t.phase === "correct" || t.phase === "explain") {
    const san = t.phase === "correct" ? t.attempt.san : item.expectedMove;
    const tp = t.tactic && t.tactic.primary;
    const idea = tp ? tp.text : (item.expectedLine && item.expectedLine.length
      ? "The engine's main line from here: " + sansOfLine(item.fen, item.expectedLine, 6) + "." : "");
    const why = tp ? tp.idea : (MOTIF_CONCEPTS[item.concept] || "");
    const take = tp ? (TACTIC_TAKEAWAY[tp.kind] || "Look for the same shape again.")
      : item.playedMove ? "Compare " + san + " with your move " + item.playedMove + ": what does " + san + " do that " + item.playedMove + " doesn't?"
      : "Before you move, ask what changes for both sides.";
    const head = t.phase === "correct"
      ? '<div class="tr-verdict"><span class="tr-vico">' + icon("check") + '</span><div><div class="tr-vlabel">CORRECT</div><div class="tr-vmove">' + esc(san) + "!</div></div></div>"
      : '<div class="tr-verdict"><span class="tr-vico" style="background:var(--accent);color:var(--on-accent)">' + icon("hint") + '</span><div><div class="tr-vlabel" style="color:var(--accent-ink)">THE ANSWER</div><div class="tr-vmove">' + esc(san) + "</div></div></div>";
    html = head +
      (idea ? '<div class="tr-sec"><div class="tr-lab">The idea</div><p>' + esc(idea) + "</p></div>" : "") +
      (why ? '<div class="tr-sec"><div class="tr-lab">Why it works</div><p>' + esc(why) + "</p></div>" : "") +
      patternHtml +
      '<div class="tr-sec"><div class="tr-lab">Training takeaway</div><p>' + esc(take) + "</p></div>" + bar +
      '<div class="tr-actions">' + (t.phase === "explain" ? '<button id="trAgain">' + icon("reset") + "Try again</button>" : "") +
      '<span class="grow2"></span><button class="' + (t.phase === "correct" ? "success" : "primary") + '" id="trSkip">Continue' + icon("next") + "</button></div>";
  } else {   // "played": identify-motif items
    const hint = MOTIF_CONCEPTS[item.concept] || (item.explanation && item.explanation.motifText) || "";
    const tp = t.tactic && t.tactic.primary;
    html = '<div class="tr-verdict"><span class="tr-vico" style="background:var(--tactic);color:#fff">' + icon("info") + '</span><div><div class="tr-vlabel" style="color:var(--tactic)">MOVE PLAYED</div><div class="tr-vmove">' +
      esc(t.attempt.san) + "</div></div></div>" +
      (tp ? '<div class="tr-sec"><div class="tr-lab">What it does</div><p>' + esc(tp.text) + "</p></div>" : "") +
      (hint ? '<div class="tr-sec"><div class="tr-lab">The idea in this position</div><p>' + esc(item.explanation && item.explanation.motifText ? item.explanation.motifText : hint) + "</p></div>" : "") +
      patternHtml + bar +
      '<div class="tr-actions"><button id="trAgain">' + icon("reset") + 'Try again</button><span class="grow2"></span><button class="primary" id="trSkip">Continue' + icon("next") + "</button></div>";
  }
  ban.innerHTML = html;
  const on = (id, fn) => { const b = ban.querySelector("#" + id); if (b) b.onclick = fn; };
  on("trHint", trainHint); on("trSkip", trainNext); on("trAgain", trainTryAgain); on("trExplain", trainShowExplanation); on("trBack", stopTraining);
  hydrateIcons(ban);
  // Land keyboard focus on the natural next action once there is a verdict to act on.
  if (t.phase !== "task") { const primary = ban.querySelector(".primary, .success"); if (primary) primary.focus({ preventScroll: true }); }
}

function applyReview(res, fromCache) {
  state.review = res;
  state.moves = res.moves;
  state.reviewed = true;
  window.__moves = res.moves;        // test hook: lets the suite read classifications + motifs
  window.__fromCache = fromCache;    // test hook: did this review come back without the engine?
  el.cardBtn.classList.remove("hidden");   // there is a report to share now
  if (canCopyImages()) el.cardCopyBtn.classList.remove("hidden");
  renderSummary();
  renderMoveList();
  goto(state.ply);
}

// ---------- shareable report card ----------
// A PNG of how the game went, for posting. Drawn rather than screenshotted: see js/card.js.
async function buildCard() {
  const canvas = document.createElement("canvas");
  drawCard(canvas, { headers: state.headers, moves: state.moves, review: state.review });
  window.__card = { w: canvas.width, h: canvas.height, url: canvas.toDataURL("image/png") };  // test hook
  return new Promise((res) => canvas.toBlob(res, "image/png"));
}

async function saveCard() {
  const blob = await buildCard();
  if (!blob) return;
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = cardName(state.headers);
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 5000);
  chip(el.cardBtn, "Saved", "Save image", "download", "check");
}

// Straight to the clipboard, so the card can be pasted into a chat without ever
// becoming a file. The write MUST happen in the click's own task: browsers only honour
// a clipboard write while the user gesture is still live, so awaiting the blob first and
// writing after would be rejected on Safari. Hence the Promise is handed to
// ClipboardItem, which is allowed to resolve later.
async function copyCard() {
  if (!canCopyImages()) return;
  try {
    await navigator.clipboard.write([new ClipboardItem({ "image/png": buildCard() })]);
    chip(el.cardCopyBtn, "Copied", "Copy image", "copy", "check");
  } catch (e) {
    // Some browsers reject a Promise payload; retry with a resolved blob.
    try {
      const blob = await buildCard();
      await navigator.clipboard.write([new ClipboardItem({ "image/png": blob })]);
      chip(el.cardCopyBtn, "Copied", "Copy image", "copy", "check");
    } catch (e2) {
      chip(el.cardCopyBtn, "Blocked", "Copy image", "copy", "warning");
    }
  }
}

// Firefox only grew ClipboardItem recently, and it needs a secure context. Rather than
// offer a button that silently fails, don't offer it.
const canCopyImages = () =>
  typeof ClipboardItem !== "undefined" && !!(navigator.clipboard && navigator.clipboard.write);

// Briefly confirm on a button, then put its label back.
let chipTimer2 = null;
function chip(btn, on, off, iconOff, iconOn) {
  const set = (txt, ic) => { btn.innerHTML = icon(ic) + esc(txt); };
  set(on, iconOn || iconOff);
  clearTimeout(chipTimer2);
  chipTimer2 = setTimeout(() => set(off, iconOff), 1800);
}

// ---------- engine boot ----------
const ENGINE_URL = () => new URL("../vendor/stockfish/stockfish-18-lite-single.js", import.meta.url);

// How many engines to review with. A review is ~100 INDEPENDENT positions, so it scales
// across separate single-threaded engines (measured 3.5x on six; see docs/NOTES.md — and
// note this is the OPPOSITE of Threads>1 inside one engine, which measured 5-6x SLOWER).
//
// The pool is built for a review and torn down after it. Each engine is its own WASM
// instance holding its own hash, so keeping six alive would cost hundreds of MB to sit
// idle — for a machine that is not reviewing anything. One engine stays, for the live
// panel; the rest exist only while the progress bar is on screen.
function poolSize() {
  const cores = navigator.hardwareConcurrency || 2;
  const lowMem = navigator.deviceMemory && navigator.deviceMemory <= 4;
  return Math.max(1, Math.min(lowMem ? 2 : 6, cores - 1));
}

async function boot() {
  state.engine = new Engine(ENGINE_URL());
  el.engineStatus.textContent = "loading engine (~7 MB)…";
  await state.engine.boot();
  state.booted = true;
  el.engineName.textContent = state.engine.name || "Stockfish 18";
  el.engineStatus.textContent = "ready";
  el.engineStatus.classList.add("ok");
  el.reviewBtn.disabled = !state.moves.length;
  renderModeUi();
  restartLive();
}

// ---------- wire up UI ----------
function bind() {
  $("bStart").onclick = () => { state.explore = null; el.exploreBar.classList.add("hidden"); goto(0); };
  $("bPrev").onclick = () => { state.explore = null; el.exploreBar.classList.add("hidden"); goto(state.ply - 1); };
  $("bNext").onclick = () => { state.explore = null; el.exploreBar.classList.add("hidden"); goto(state.ply + 1); };
  $("bEnd").onclick = () => { state.explore = null; el.exploreBar.classList.add("hidden"); goto(state.moves.length); };
  $("bFlip").onclick = () => { state.flip = !state.flip; drawBoard(); };
  // Right-clicking the board draws arrows instead of opening the context menu.
  el.board.addEventListener("contextmenu", (e) => e.preventDefault());
  $("returnGame").onclick = returnToGame;
  el.explainPrev.onclick = () => explainStep(-1);
  el.explainNext.onclick = () => explainStep(1);
  el.explainDone.onclick = exitExplain;

  el.reviewBtn.onclick = () => { state.reviewing ? (state.cancel.cancelled = true) : runReview(); };
  el.cardBtn.onclick = saveCard;
  el.cardCopyBtn.onclick = copyCard;

  // ---- modes ----
  document.querySelectorAll(".modetab").forEach((b) => (b.onclick = () => setMode(b.dataset.mode)));
  const pickSide = (c) => {
    state.botPick = c;
    el.pickWhite.classList.toggle("on", c === "w");
    el.pickBlack.classList.toggle("on", c === "b");
  };
  el.pickWhite.onclick = () => pickSide("w");
  el.pickBlack.onclick = () => pickSide("b");
  BOT_LEVELS.forEach((l, i) => {
    const o = document.createElement("option");
    o.value = i;
    o.textContent = l.label;
    el.botElo.appendChild(o);
  });
  el.botElo.value = "4";   // ≈1200 — a humble default beats an insulting one
  el.botStart.onclick = startBot;
  el.botRematch.onclick = () => { if (state.mode === "bot") startBot(); };
  el.botResign.onclick = () => {
    if (!botActive()) return;
    endBotGame(state.bot.color === "w" ? "0-1" : "1-0", "You resigned");
  };
  el.soloReset.onclick = () => loadGame({ headers: {}, moves: [], startFen: DEFAULT_FEN });
  initExplorerUi();

  // ----- screenshot scan + position editor -----
  el.scanFile.onchange = (e) => { handleScanFile(e.target.files[0]); e.target.value = ""; };
  el.scanBtn.onclick = () => openEditor(emptyGrid(),
    "Build a position: pick a piece and click squares. Choose ⌫ to erase. Set who's to move, then analyze.");
  el.edWhite.onclick = () => { if (state.editor) { state.editor.stm = "w"; renderEditor(); } };
  el.edBlack.onclick = () => { if (state.editor) { state.editor.stm = "b"; renderEditor(); } };
  el.edFlip.onclick = () => { if (state.editor) { state.editor.flip = !state.editor.flip; renderEditor(); } };
  el.edClear.onclick = () => { if (state.editor) { state.editor.grid = emptyGrid(); renderEditor(); } };
  el.edStart.onclick = () => { if (state.editor) { state.editor.grid = fenToGrid(DEFAULT_FEN); renderEditor(); } };
  el.edAnalyze.onclick = analyzeEditor;
  el.edCancel.onclick = closeEditor;
  // Paste an image straight onto the page (⌘V a screenshot) to scan it. Only image
  // items are intercepted, so pasting a PGN into its box still works normally.
  window.addEventListener("paste", (e) => {
    const items = (e.clipboardData && e.clipboardData.items) || [];
    for (const it of items) {
      if (it.type && it.type.startsWith("image/")) { handleScanFile(it.getAsFile()); e.preventDefault(); break; }
    }
  });

  $("loadPgn").onclick = () => {
    const txt = el.pgnInput.value.trim();
    if (!txt) return;
    // A link dropped in the PGN box should work too, rather than fail to parse.
    if (looksLikeUrl(txt)) { el.userInput.value = txt; openGameFromLink(txt); return; }
    try { loadGame(parseGame(txt)); }
    catch (e) { alert("Could not parse PGN:\n" + e.message); }
  };
  $("loadFen").onclick = () => {
    const fen = el.fenInput.value.trim();
    if (!fen) return;
    try {
      new Chess(fen); // validates
      loadGame({ headers: { White: "Position", Black: "analysis" }, moves: [], startFen: fen });
    } catch (e) { alert("Invalid FEN:\n" + e.message); }
  };
  $("loadSample").onclick = () => { el.pgnInput.value = SAMPLE_PGN; loadGame(parseGame(SAMPLE_PGN)); };

  el.impToggle.onclick = () => {
    setImportOpen(true);
    el.userInput.focus({ preventScroll: true });
    document.querySelector(".import").scrollIntoView({ block: "nearest", behavior: "smooth" });
  };

  el.siteSel.value = state.acct.site;
  el.userInput.value = state.acct.user;
  el.loadUser.onclick = loadFromInput;
  el.userInput.addEventListener("keydown", (e) => { if (e.key === "Enter") loadFromInput(); });
  el.siteSel.onchange = () => {
    // The listed games belong to the previous site — drop them.
    state.acct.site = el.siteSel.value;
    state.acct.games = [];
    state.acct.activeId = null;
    renderGameList();
    setAcctMsg("", false);
  };
  $("pgnFile").onchange = (e) => {
    const f = e.target.files[0];
    if (!f) return;
    const r = new FileReader();
    r.onload = () => { el.pgnInput.value = r.result; try { loadGame(parseGame(r.result)); } catch (err) { alert(err.message); } };
    r.readAsText(f);
  };

  el.depthSel.onchange = () => { state.reviewDepth = +el.depthSel.value; };
  el.linesSel.onchange = () => { state.liveLines = +el.linesSel.value; restartLive(); };
  el.liveToggle.onclick = () => {
    state.live = !state.live;
    el.liveToggle.classList.toggle("on", state.live);
    el.liveToggleTxt.textContent = state.live ? "Engine on" : "Engine off";
    el.live.classList.toggle("off", !state.live);
    el.liveToggle.setAttribute("aria-pressed", String(state.live));
    setLiveBadge(state.live ? "analyzing" : "off");
    if (state.live) restartLive(); else { state.engine && state.engine.stopLive(); state.engineArrows = null; repaintArrows(); }
  };
  // fold the engine down to its best line (the rest is one click away)
  const setLinesFold = (folded) => {
    el.live.classList.toggle("folded", folded);
    el.linesFold.setAttribute("aria-expanded", String(!folded));
    el.linesFold.setAttribute("aria-label", folded ? "Show more engine lines" : "Collapse engine lines");
    el.linesFold.title = el.linesFold.getAttribute("aria-label");
    el.linesFold.querySelector("[data-icon]").innerHTML = icon(folded ? "down" : "up");
    try { localStorage.setItem("ca_lines_folded", folded ? "1" : "0"); } catch (e) { /* private mode */ }
  };
  el.trainBack.onclick = stopTraining;
  el.linesFold.onclick = () => setLinesFold(!el.live.classList.contains("folded"));
  try { if (localStorage.getItem("ca_lines_folded") === "1") setLinesFold(true); } catch (e) { /* private mode */ }
  // the eye under the board: engine arrows on / off
  const syncArrowBtn = () => {
    el.bArrows.classList.toggle("on", state.engineArrowsOn);
    el.bArrows.setAttribute("aria-pressed", String(state.engineArrowsOn));
    const label = state.engineArrowsOn ? "Hide engine arrows" : "Show engine arrows";
    el.bArrows.setAttribute("aria-label", label); el.bArrows.title = label;
    el.bArrows.querySelector("[data-icon]").innerHTML = icon(state.engineArrowsOn ? "eye" : "eyeoff");
  };
  el.bArrows.onclick = () => {
    state.engineArrowsOn = !state.engineArrowsOn;
    try { localStorage.setItem("ca_engine_arrows", state.engineArrowsOn ? "1" : "0"); } catch (e) { /* private mode */ }
    syncArrowBtn(); repaintArrows();
  };
  syncArrowBtn();
  // coach / training tabs in the right column
  document.querySelectorAll(".rtab").forEach((b) => {
    b.onclick = () => setRightTab(b.dataset.rtab);
  });
  const seekFromGraph = (canvas) => (e) => {
    const r = canvas.getBoundingClientRect();
    state.explore = null; el.exploreBar.classList.add("hidden");
    goto(Math.round(((e.clientX - r.left) / r.width) * state.moves.length));
  };
  el.evalGraph.addEventListener("click", seekFromGraph(el.evalGraph));
  el.timeGraph.addEventListener("click", seekFromGraph(el.timeGraph));
  window.addEventListener("resize", () => { drawEvalGraph(); drawTimeGraph(); });

  const syncSoundIcon = () => {
    el.soundToggle.querySelector("[data-icon]").innerHTML = icon(state.sound ? "sound" : "mute");
    el.soundToggle.setAttribute("aria-pressed", String(state.sound));
  };
  el.soundToggle.classList.toggle("on", state.sound);
  syncSoundIcon();
  el.soundToggle.onclick = () => {
    state.sound = !state.sound;
    syncSoundIcon();
    el.soundToggle.classList.toggle("on", state.sound);
    try { localStorage.setItem("ca_sound", state.sound ? "1" : "0"); } catch (e) { /* ignore */ }
    if (state.sound) playMoveSound({ san: "e4" }); // preview the sound when enabling
  };
  el.shareBtn.onclick = copyShareLink;
  el.shareBtn2.onclick = copyShareLink;
  // Pasting a share link into an already-open tab should load that game.
  window.addEventListener("hashchange", () => { loadFromHash(); });

  $("themeToggle").onclick = () => {
    const cur = document.documentElement.getAttribute("data-theme");
    const next = cur === "dark" ? "light" : cur === "light" ? "dark"
      : (matchMedia("(prefers-color-scheme: dark)").matches ? "light" : "dark");
    document.documentElement.setAttribute("data-theme", next);
  };

  document.addEventListener("keydown", (e) => {
    if (e.target.tagName === "TEXTAREA" || e.target.tagName === "INPUT") return;
    // While explaining, the arrows drive the walk-through, not the game.
    if (state.explain) {
      if (e.key === "ArrowLeft") { explainStep(-1); e.preventDefault(); }
      else if (e.key === "ArrowRight") { explainStep(1); e.preventDefault(); }
      else if (e.key === "Escape" || e.key === "Enter") { exitExplain(); e.preventDefault(); }
      return;
    }
    if (e.key === "ArrowLeft") { $("bPrev").click(); e.preventDefault(); }
    else if (e.key === "ArrowRight") { $("bNext").click(); e.preventDefault(); }
    else if (e.key === "Home") { $("bStart").click(); e.preventDefault(); }
    else if (e.key === "End") { $("bEnd").click(); e.preventDefault(); }
    else if (e.key === "f") $("bFlip").click();
  });
}

// build legend once
function buildLegend() {
  const box = $("legend");
  for (const k of CLASS_ORDER) {
    const it = document.createElement("div");
    it.className = "legitem";
    it.innerHTML = '<span class="g" style="background:var(' + CLASSES[k].v + ')">' + glyphSvg(k) +
      "</span>" + CLASSES[k].label;
    box.appendChild(it);
  }
}

// ---------- init ----------
hydrateIcons();
bind();
buildLegend();
el.depthSel.value = String(state.reviewDepth);
el.linesSel.value = String(state.liveLines);
// A shared #g= / #z= / #pgn= / #fen= link loads that game; otherwise start empty.
loadFromHash().then((loaded) => {
  if (!loaded) loadGame({ headers: {}, moves: [], startFen: DEFAULT_FEN });
});
boot();
