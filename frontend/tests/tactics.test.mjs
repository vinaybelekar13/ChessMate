// Guards src/chess/tactics.js: the detector names a tactic only when the position really contains it,
// points at the ACTUAL pieces, and stays quiet otherwise. Pure logic — no browser needed.
import { Chess } from "../vendor/chess.js";
import { detectTactics, tacticOverlay } from "../src/chess/tactics.js";
import { suite } from "./lib/harness.mjs";

const t = suite("tactics");
const T = (fenBefore, fenAfter, from, to, san) => detectTactics({ fenBefore, fenAfter, from, to, san });
const kind = (r) => (r ? r.primary.kind : null);
const sqs = (p) => p.targets.map((x) => x.sq).sort().join(",");

// --- each named tactic, from a position built to contain exactly it ---
let r = T("r3k3/8/8/3N4/8/8/8/4K3 w - - 0 1", "r3k3/2N5/8/8/8/8/8/4K3 b - - 1 1", "d5", "c7", "Nc7+");
t.ok("fork: Nc7+ hits the king and the rook", kind(r) === "fork" && sqs(r.primary) === "a8,e8" && r.primary.check,
  r && r.primary.text);
t.ok("fork arrows leave the knight's square and land on the real targets",
  r && r.primary.arrows.every((a) => a.from === "c7") && r.primary.arrows.map((a) => a.to).sort().join() === "a8,e8");

r = T("r1r3k1/8/8/3N4/8/8/8/4K3 w - - 0 1", "r1r3k1/8/1N6/8/8/8/8/4K3 b - - 1 1", "d5", "b6", "Nb6");
t.ok("fork: Nb6 attacks both rooks", kind(r) === "fork" && sqs(r.primary) === "a8,c8", r && r.primary.text);

r = T("r1r3k1/p7/8/3N4/8/8/8/4K3 w - - 0 1", "r1r3k1/p7/1N6/8/8/8/8/4K3 b - - 1 1", "d5", "b6", "Nb6");
t.ok("no fork when the enemy pawn simply takes the knight", r === null, String(kind(r)));

r = T("r1bqkbnr/ppp2ppp/2np4/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R w KQkq - 0 4",
  "r1bqkbnr/ppp2ppp/2np4/1B2p3/4P3/5N2/PPPP1PPP/RNBQK2R b KQkq - 1 4", "f1", "b5", "Bb5");
t.ok("pin: Bb5 pins the knight on c6 to the king on e8",
  kind(r) === "pin" && r.primary.absolute && r.primary.targets[0].sq === "c6" && r.primary.targets[1].sq === "e8", r && r.primary.text);
t.ok("pin arrows run attacker -> pinned piece -> king",
  r && r.primary.arrows[0].from === "b5" && r.primary.arrows[0].to === "c6" && r.primary.arrows[1].from === "c6" && r.primary.arrows[1].to === "e8");

r = T("r1bqkbnr/pppp1ppp/2n5/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R w KQkq - 2 3",
  "r1bqkbnr/pppp1ppp/2n5/1B2p3/4P3/5N2/PPPP1PPP/RNBQK2R b KQkq - 3 3", "f1", "b5", "Bb5");
t.ok("no pin while a pawn on d7 stands between the knight and the king", r === null, String(kind(r)));

r = T("r1bqkbnr/ppp2ppp/2np4/1B2p3/4P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 0 5",
  "r1bqkbnr/ppp2ppp/2np4/4p3/B3P3/5N2/PPPP1PPP/RNBQK2R b KQkq - 1 5", "b5", "a4", "Ba4");
t.ok("no pin credit for a move that merely keeps an existing pin", r === null, String(kind(r)));

r = T("4k2r/8/8/8/8/8/8/R3K3 w - - 0 1", "R3k2r/8/8/8/8/8/8/4K3 b - - 1 1", "a1", "a8", "Ra8+");
t.ok("skewer: Ra8+ attacks the king with the rook behind it",
  kind(r) === "skewer" && r.primary.targets[0].sq === "e8" && r.primary.targets[1].sq === "h8", r && r.primary.text);

r = T("6k1/8/5q2/8/3N4/8/1B6/4K3 w - - 0 1", "6k1/8/4Nq2/8/8/8/1B6/4K3 b - - 1 1", "d4", "e6", "Ne6");
t.ok("discovered attack: moving the knight opens the bishop's line to the queen",
  kind(r) === "discovered-attack" && r.primary.attacker.sq === "b2" && r.primary.targets[0].sq === "f6" &&
  r.primary.arrows[0].from === "b2" && r.primary.arrows[0].to === "f6", r && r.primary.text);

r = T("8/6k1/8/8/3N4/8/1B6/4K3 w - - 0 1", "8/6k1/8/5N2/8/8/1B6/4K3 b - - 1 1", "d4", "f5", "Nf5+");
t.ok("double check: the knight and the uncovered bishop both give check", kind(r) === "double-check", r && r.primary.text);

r = T("1k1b4/8/8/8/8/1n6/8/4K2Q w - - 0 1", "1k1b4/8/8/3Q4/8/1n6/8/4K3 b - - 1 1", "h1", "d5", "Qd5");
t.ok("double attack: a queen hitting two loose pieces is named as one, not as a fork",
  kind(r) === "double-attack" && sqs(r.primary) === "b3,d8", r && r.primary.text);

r = T("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1", "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1", "e2", "e4", "e4");
t.ok("a quiet opening move is not called a tactic", r === null);

// --- the overlay a UI would draw ---
const ov = tacticOverlay(T("r3k3/8/8/3N4/8/8/8/4K3 w - - 0 1", "r3k3/2N5/8/8/8/8/8/4K3 b - - 1 1", "d5", "c7", "Nc7+"), "c7");
t.ok("overlay marks the forking piece and every target square",
  ov.squares.some((s) => s.sq === "c7" && s.role === "attacker") &&
  ov.squares.filter((s) => s.role === "target").map((s) => s.sq).sort().join() === "a8,e8" && ov.arrows.length === 2);

// --- a whole real game: precision check. Every claim is one a human can verify on the board. ---
const pgn = `1. e4 e5 2. Nc3 Nc6 3. Nf3 Nf6 4. d4 exd4 5. Nxd4 Bb4 6. Nxc6 bxc6 7. Bd3 d5
8. exd5 O-O 9. O-O cxd5 10. Bg5 c6 11. Qf3 Bd6 12. Rae1 Rb8 13. b3 Bb4 14. Qg3 Be6
15. Qh4 h6 16. Bxh6 gxh6 17. Qxh6 Bxc3 18. Rxe6 Ne4 19. Rxe4 dxe4 20. Bxe4 f5
21. Bxf5 Rf7 22. Be6 Qf6 23. Bxf7+ Kxf7 24. Qh5+ Kg8 25. Qg4+ Kf8 26. Rd1 c5
27. Rd5 Re8 28. g3 Re5 29. Rd3 Ke7 30. Qd7+ Kf8 31. Qg4 Ke7 32. Qa4 Re1+
33. Kg2 Bd4 34. Qxa7+ Kf8 35. Qa8+ Kg7 36. Rf3 Qe6 37. Qf8+ Kg6 38. h4 c4
39. bxc4 Qxc4 40. h5+ Kh7 41. Rf7+ Qxf7 42. Qxf7+ Bg7 43. a4 Rd1 44. Qg6+ Kh8
45. Qe8+ Kh7 46. a5 Ra1 47. Qg6+ Kh8 48. a6 Be5 49. Qe8+ Kh7 50. Qxe5 Rxa6
51. Qc7+ Kh6 52. Qf7 1-0`;
const g = new Chess(); g.loadPgn(pgn);
const flagged = g.history({ verbose: true })
  .map((m) => ({ san: m.san, r: detectTactics({ fenBefore: m.before, fenAfter: m.after, from: m.from, to: m.to, san: m.san }) }))
  .filter((x) => x.r);
t.ok("on a 103-ply game it is selective (a handful of moves, not most of them)",
  flagged.length >= 3 && flagged.length <= 15, flagged.length + " flagged: " + flagged.map((x) => x.san).join(" "));
const last = flagged.find((x) => x.san === "Qe8+");
t.ok("49.Qe8+ is the check that also hits the loose bishop on e5 (the game continued 50.Qxe5)",
  !!last && last.r.primary.kind === "fork" && last.r.primary.targets.some((x) => x.sq === "e5"), last && last.r.primary.text);
const g2 = flagged.find((x) => x.san === "Bb4" && /king on e1/.test(x.r.primary.text));
t.ok("5...Bb4 is called an absolute pin of Nc3 against the king on e1", !!g2 && g2.r.primary.absolute, g2 && g2.r.primary.text);
t.ok("no target or arrow ever refers to an empty or out-of-range square",
  flagged.every((x) => x.r.patterns.every((p) => p.targets.every((y) => /^[a-h][1-8]$/.test(y.sq)) && p.arrows.every((a) => /^[a-h][1-8]$/.test(a.from + "") && /^[a-h][1-8]$/.test(a.to + "")))));

t.finish();
