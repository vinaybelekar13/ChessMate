import { renderBoard as renderSharedBoard } from "./board.js?v=35";
import { Chess } from "../vendor/chess.js";
const API = "http://127.0.0.1:8788/api";
const $ = id => document.getElementById(id);
const PIECES = {
  K:"â™”", Q:"â™•", R:"â™–", B:"â™—", N:"â™˜", P:"â™™",
  k:"â™š", q:"â™›", r:"â™œ", b:"â™", n:"â™ž", p:"â™Ÿ"
};

let dragFrom = null;
let dragStartX = 0;
let dragStartY = 0;
let dragMoved = false;
let suppressNextBoardClick = false;
let activePointerId = null;

const state = {
  puzzle:null, startFen:"", boardFen:"", expected:[], moveIndex:0,
  orientation:"white", selected:null, legal:[], line:[], hintLevel:0,
  solved:false, revealed:false, streak:0, solvedCount:0, attempts:0,
  correctFirst:0, lastMove:null, busy:false
};

let positionHistory = [];
let historyIndex = 0;

function resetPositionHistory(fen) {
  positionHistory = [{ fen, lastMove: null }];
  historyIndex = 0;
updateNavigation();
}

function recordPosition(fen, lastMove) {
  positionHistory.push({ fen, lastMove: lastMove || null });
  historyIndex = positionHistory.length - 1;
updateNavigation();
}

function updateNavigation() {
  const count = positionHistory.length;
  const index = Math.max(0, Math.min(historyIndex, count - 1));
  const reviewing = index < count - 1;
  const first = $("move-first");
  const previous = $("move-previous");
  const next = $("move-next");
  const last = $("move-last");
  const label = $("move-position");

  if (!first || !previous || !next || !last || !label) return;
  first.disabled = count < 2 || index === 0;
  previous.disabled = count < 2 || index === 0;
  next.disabled = count < 2 || index === count - 1;
  last.disabled = count < 2 || index === count - 1;
  label.textContent = `Position ${index + 1} / ${count}`;
  label.title = reviewing
    ? "Reviewing history. Use Next or Last to return to the current position."
    : "Current puzzle position";
}

function parseFen(fen) {
  const rows = fen.split(" ")[0].split("/");
  const board = [];
  for (const row of rows) {
    const squares = [];
    for (const c of row) {
      if (/\d/.test(c)) for(let i=0;i<Number(c);i++) squares.push("");
      else squares.push(c);
    }
    board.push(...squares);
  }
  return board;
}
function squareName(index) {
  return "abcdefgh"[index % 8] + (8 - Math.floor(index / 8));
}
function indexFromName(name) {
  return (8 - Number(name[1])) * 8 + "abcdefgh".indexOf(name[0]);
}
function sideFromFen(fen) { return fen.split(" ")[1] === "w" ? "white" : "black"; }
function pieceSide(piece) {
  return !piece ? null : piece === piece.toUpperCase() ? "white" : "black";
}
function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, c => ({
    "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"
  }[c]));
}
async function api(path, body) {
  const response = await fetch(API + path, {
    method: body ? "POST" : "GET",
    headers: body ? {"Content-Type":"application/json"} : {},
    body: body ? JSON.stringify(body) : undefined
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || `API error ${response.status}`);
  return data;
}
function setStatus(title, message, kind="normal") {
  $("status-title").textContent = title;
  $("status-message").textContent = message;
  const card = $("status-card");
  card.style.borderColor = kind === "error" ? "#75423d" : kind === "success" ? "#4b693d" : "";
  card.style.background = kind === "error" ? "#332624" : kind === "success" ? "#263125" : "";
  $("status-title").style.color = kind === "error" ? "#f09489" : kind === "success" ? "#a3d160" : "";
}
function hideCheckmateOverlay() {
  const overlay = $("checkmate-overlay");
  if (!overlay) return;
  overlay.classList.remove("is-visible");
  overlay.setAttribute("aria-hidden", "true");
}

function updateCheckmateOverlay(fen = state.boardFen) {
  const overlay = $("checkmate-overlay");
  if (!overlay) return;

  try {
    const chess = new Chess(fen);
    if (!chess.isCheckmate()) {
      hideCheckmateOverlay();
      return;
    }

    const winner = chess.turn() === "w" ? "Black" : "White";
    $("checkmate-title").textContent = "CHECKMATE";
    $("checkmate-subtitle").textContent = `${winner} wins`;
    overlay.classList.add("is-visible");
    overlay.setAttribute("aria-hidden", "false");
  } catch (error) {
    console.error("Checkmate detection failed:", error);
    hideCheckmateOverlay();
  }
}
function renderBoard() {
  const board = $("board");
  const reviewing = historyIndex < positionHistory.length - 1;
  const viewed = reviewing ? positionHistory[historyIndex] : null;
  const shownFen = viewed ? viewed.fen : state.boardFen;
  const shownLastMove = viewed ? viewed.lastMove : state.lastMove;
  const destinations = reviewing ? [] : [
    ...new Set(
      state.legal
        .filter(m => m.from === state.selected)
        .map(m => m.to)
    )
  ];

  const lastMove = shownLastMove
    ? {
        from: shownLastMove.slice(0, 2),
        to: shownLastMove.slice(2, 4)
      }
    : null;

  renderSharedBoard(board, shownFen, {
    flip: state.orientation === "black",
    lastMove,
    selected: reviewing ? null : state.selected,
    targets: destinations,
    arrows: [
      ...((!reviewing && state.revealed && state.expected[1])
        ? [{
            from: state.expected[1].slice(0, 2),
            to: state.expected[1].slice(2, 4),
            color: "#a6e66e"
          }]
        : []),
      ...userArrows
    ],
    onSquareClick: handleBoardClick,
    onSquareDown: onSquareDown
  });

  board.setAttribute("aria-label", reviewing
    ? "Chessboard showing a previous position"
    : "Interactive chessboard");
  const shownSide = sideFromFen(shownFen);
  const sideName = shownSide === "white" ? "White" : "Black";

  $("side-label").textContent = reviewing
    ? `Reviewing · ${sideName} to move`
    : state.solved
      ? "Puzzle completed"
      : `${sideName} to move`;

  $("side-detail").textContent = reviewing
    ? "Previous position · use Next or Last to return"
    : state.solved
      ? "Great calculation."
      : "Select a piece, then a destination";

  $("turn-pill").textContent = reviewing
    ? `${shownSide.toUpperCase()} TO MOVE · REVIEW`
    : state.solved
      ? "PUZZLE COMPLETED"
      : `${shownSide.toUpperCase()} TO MOVE`;

  $("turn-pill").dataset.turn = state.solved && !reviewing
    ? "solved"
    : shownSide;
  updateCheckmateOverlay(shownFen);
  updateNavigation();
}
async function refreshLegalMoves() {
  const data = await api("/legal-moves", {fen:state.boardFen});
  state.legal = data.moves || [];
  renderBoard();
}
function updateMeta() {
  const p = state.puzzle;
  $("rating").textContent = `${p.rating ?? "â€”"} ELO`;
  $("opponent-name").textContent = `Puzzle ${p.puzzle_id}`;
  $("opponent-meta").textContent = `${p.source} database Â· ${p.nb_plays ?? 0} plays`;
  const side = sideFromFen(state.boardFen);
  $("side-label").textContent = state.solved ? "Puzzle completed" : `${side === "white" ? "White" : "Black"} to move`;
  $("side-detail").textContent = state.solved ? "Great calculation." : "Select a piece, then a destination";
  $("turn-pill").textContent = state.solved ? "SOLVED" : side.toUpperCase() + " TO MOVE";
  const themes = p.themes || [];
  $("theme-chips").innerHTML = themes.length
    ? themes.slice(0,8).map(t=>`<span class="chip">${escapeHtml(t.replace(/([A-Z])/g," $1").trim())}</span>`).join("")
    : '<span class="chip">General tactics</span>';
  $("objective-title").textContent = themes.some(t=>t.toLowerCase().includes("mate"))
    ? "Find the mating sequence" : "Find the strongest continuation";
  $("objective-copy").textContent = `Solve the position in ${Math.max(1,Math.ceil(state.expected.length/2))} calculated move${state.expected.length>2?"s":""}.`;
  $("move-list").innerHTML = state.line.length
    ? state.line.map((m,i)=>`<span class="move-token">${i+1}. ${escapeHtml(m)}</span>`).join("")
    : "Your moves will appear here.";
}
async function loadPuzzle() {
  state.busy = true;
  $("new-puzzle").disabled = true;
  $("next-puzzle").disabled = true;
  setStatus("Loading a new puzzle","Selecting a position from your local puzzle database.");
  try {
    const range = $("difficulty").value.split("-").map(Number);
    const params = new URLSearchParams({
      min_rating:String(range[0]), max_rating:String(range[1])
    });
    if ($("theme").value) params.set("theme",$("theme").value);
    const p = await api("/puzzle?" + params.toString());
    state.puzzle = p;
    state.startFen = p.fen;
    state.expected = p.moves_uci || [];
    if (state.expected.length < 2) {
      throw new Error("Puzzle solution is incomplete.");
    }

    // Lichess moves_uci[0] is the opponent's forced setup move.
    const setup = await api("/validate", {
      fen: state.startFen,
      uci: state.expected[0]
    });

    state.boardFen = setup.fen;
    state.moveIndex = 1;
    state.orientation = sideFromFen(p.fen);
    state.selected = null;
    state.line = [];
    state.hintLevel = 0;
    state.solved = false;
    state.revealed = false;
    state.lastMove = null;
    resetPositionHistory(state.boardFen);
    await refreshLegalMoves();
    updateMeta();
    setStatus("Find the best move","Look for checks, captures, and forcing threats.");
    $("hint-text").textContent = "Start by checking all forcing moves.";
  } catch (err) {
    setStatus("Couldn't load a puzzle",err.message,"error");
  } finally {
    state.busy = false;
    $("new-puzzle").disabled = false;
    $("next-puzzle").disabled = false;
  }
}

function handleBoardClick(square) {
  if (suppressNextBoardClick) {
    suppressNextBoardClick = false;
    return;
  }
  return onSquareClick(square);
}

let arrowStart = null;
let arrowPointerId = null;
let suppressNextArrowContextMenu = false;
const userArrows = [];

function onSquareDown(square, event) {
  if (event.button === 0 && userArrows.length > 0) {
    userArrows.length = 0;
    renderBoard();
  }

  if (event.button === 2) {
    event.preventDefault();
    if (historyIndex < positionHistory.length - 1) return;
    arrowStart = square;
    arrowPointerId = event.pointerId;
    return;
  }

  if (historyIndex < positionHistory.length - 1) return;
  if (event.button !== 0 || state.busy || state.solved ||
      state.revealed || !state.puzzle) return;

  const pieces = parseFen(state.boardFen);
  const piece = pieces[indexFromName(square)];

  if (!piece || pieceSide(piece) !== sideFromFen(state.boardFen)) return;

  dragFrom = square;
  activePointerId = event.pointerId;
  dragStartX = event.clientX;
  dragStartY = event.clientY;
  dragMoved = false;
}

if (!window.__chessMatePuzzleDragBound) {
  window.__chessMatePuzzleDragBound = true;

  const puzzleBoardElement = document.getElementById("board");
  if (puzzleBoardElement) {
    puzzleBoardElement.addEventListener("contextmenu", event => {
      event.preventDefault();

      // A drag can trigger contextmenu after pointerup; don't erase its arrow.
      if (suppressNextArrowContextMenu) {
        suppressNextArrowContextMenu = false;
        return;
      }

      // Right-click is reserved for drawing arrows.
      // Do not clear arrows from the context-menu event.

    });
  }

  document.addEventListener("pointerup", event => {
    if (arrowPointerId === null || event.pointerId !== arrowPointerId) return;

    const from = arrowStart;
    arrowStart = null;
    arrowPointerId = null;

    const target = document.elementFromPoint(event.clientX, event.clientY);
    const squareElement = target?.closest("#board [data-sq]");
    const to = squareElement?.dataset.sq;

    if (!from || !to || from === to) return;

    suppressNextArrowContextMenu = true;
    window.setTimeout(() => {
      suppressNextArrowContextMenu = false;
    }, 700);

    const existing = userArrows.findIndex(
      arrow => arrow.from === from && arrow.to === to
    );

    if (existing >= 0) {
      userArrows.splice(existing, 1);
    } else {
      userArrows.push({ from, to, color: "#e64b4b" });
    }

    renderBoard();
  });

  document.addEventListener("pointercancel", event => {
    if (event.pointerId !== arrowPointerId) return;
    arrowStart = null;
    arrowPointerId = null;
  });

  document.addEventListener("pointermove", event => {
    if (!dragFrom || event.pointerId !== activePointerId) return;

    const dx = event.clientX - dragStartX;
    const dy = event.clientY - dragStartY;

    if (Math.hypot(dx, dy) > 7) {
      dragMoved = true;
    }
  }, { passive: true });

  document.addEventListener("pointerup", async event => {
    if (!dragFrom || event.pointerId !== activePointerId) return;

    const from = dragFrom;
    const moved = dragMoved;

    dragFrom = null;
    dragMoved = false;
    activePointerId = null;

    if (!moved) return;

    // Suppress the synthetic click generated after a completed drag.
    suppressNextBoardClick = true;
    window.setTimeout(() => {
      suppressNextBoardClick = false;
    }, 350);

    const target = document.elementFromPoint(event.clientX, event.clientY);
    const squareElement = target?.closest("#board [data-sq]");
    if (!squareElement) return;

    const to = squareElement.dataset.sq;
    if (!to || to === from) return;

    if (historyIndex < positionHistory.length - 1 ||
        state.busy || state.solved || state.revealed || !state.puzzle) {
      return;
    }

    // Use the same legal-move and puzzle-validation path as click-to-move.
    state.selected = from;
    await onSquareClick(to);
  });

  document.addEventListener("pointercancel", event => {
    if (event.pointerId !== activePointerId) return;

    dragFrom = null;
    dragMoved = false;
    activePointerId = null;
  });
}

async function onSquareClick(square) {
  if (historyIndex < positionHistory.length - 1) {
    setStatus("Reviewing previous position", "Use Next or Last to return to the current puzzle position.");
    return;
  }
  if (state.busy || state.solved || state.revealed || !state.puzzle) return;
  const pieces = parseFen(state.boardFen);
  const piece = pieces[indexFromName(square)];
  const turn = sideFromFen(state.boardFen);

  if (state.selected && state.legal.some(m=>m.from===state.selected && m.to===square)) {
    const move = state.legal.find(m=>m.from===state.selected && m.to===square);
    await submitMove(move.uci);
    return;
  }
  if (piece && pieceSide(piece) === turn) {
    state.selected = square;
    renderBoard();
  } else {
    state.selected = null;
    renderBoard();
  }
}
async function submitMove(uci, forced=false) {
  if (!state.expected.length || state.moveIndex >= state.expected.length) return;
  state.busy = true;
  state.selected = null;
  try {
    const expected = state.expected[state.moveIndex];
    if (uci !== expected) {
      state.attempts++;
      state.streak = 0;
      updateStats();
      setStatus("Not quite","That move isn't the puzzle continuation. Try another candidate.","error");
      await refreshLegalMoves();
      return;
    }

    const result = await api("/validate",{fen:state.boardFen,uci});
    state.boardFen = result.fen;
    state.lastMove = uci;
    state.line.push(result.san || uci);
    state.moveIndex++;
    recordPosition(state.boardFen, uci);
    state.attempts++;
    if (state.moveIndex === 2) state.correctFirst++;
    await refreshLegalMoves();
    updateMeta();

    if (state.moveIndex >= state.expected.length) {
      state.solved = true;
      state.solvedCount++;
      state.streak++;
      updateStats();
      setStatus("Puzzle solved!","Excellent calculation. Load another puzzle when you're ready.","success");
      updateMeta();
      return;
    }

    setStatus("Correct move","Now calculate the opponent's best reply.","success");
    await new Promise(resolve=>setTimeout(resolve,350));
    const reply = state.expected[state.moveIndex];
    const replyResult = await api("/validate",{fen:state.boardFen,uci:reply});
    state.boardFen = replyResult.fen;
    state.lastMove = reply;
    state.line.push(replyResult.san || reply);
    state.moveIndex++;
    recordPosition(state.boardFen, reply);
    await refreshLegalMoves();
    updateMeta();

    if (state.moveIndex >= state.expected.length) {
      state.solved = true;
      state.solvedCount++;
      state.streak++;
      updateStats();
      setStatus("Puzzle solved!","You completed the full line. Nice work.","success");
      updateMeta();
    } else {
      setStatus("Your turn again","Continue the combination. Look for the next forcing move.");
    }
  } catch (err) {
    setStatus("Move error",err.message,"error");
  } finally {
    state.busy = false;
  }
}
function updateStats() {
  $("streak").textContent = state.streak;
  $("solved-count").textContent = state.solvedCount;
  $("attempt-count").textContent = state.attempts;
  $("accuracy").textContent = state.attempts ? Math.round(state.solvedCount / state.attempts * 100) + "%" : "â€”";
}
async function retryPuzzle() {
  if (!state.puzzle) return;
  state.boardFen = state.startFen;
  state.moveIndex = 0;
  if (state.expected.length) {
    const setup = await api("/validate", {
      fen: state.startFen,
      uci: state.expected[0]
    });
    state.boardFen = setup.fen;
    state.moveIndex = 1;
  }
  state.selected = null;
  state.line = [];
  state.solved = false;
  state.revealed = false;
  state.lastMove = null;
  state.hintLevel = 0;
  resetPositionHistory(state.boardFen);
  refreshLegalMoves().then(updateMeta);
  setStatus("Try again","Take a fresh look at the original position.");
}
function getHint() {
  if (!state.expected.length || state.solved) return;
  state.hintLevel++;
  const first = state.expected[Math.min(state.moveIndex,state.expected.length-1)];
  if (state.hintLevel === 1) {
    $("hint-text").textContent = "Look for a forcing move: check, capture, or direct threat.";
    setStatus("Hint 1","Scan for checks and forcing captures.");
  } else if (state.hintLevel === 2) {
    $("hint-text").textContent = `The solution starts from ${first.slice(0,2)}. Find the piece on that square.`;
    setStatus("Hint 2","We've narrowed down the piece to consider.");
  } else {
    $("hint-text").textContent = `The next move is ${first}.`;
    setStatus("Move hint","Try that move on the board.");
  }
}
async function revealSolution() {
  if (!state.puzzle || state.busy) return;

  state.revealed = true;

  try {
    // Recreate the setup position from the original puzzle every time.
    const setup = await api("/validate", {
      fen: state.startFen,
      uci: state.expected[0]
    });

    let fen = setup.fen;
    const formattedMoves = [];

    // The first UCI move is the forced setup move, not the solution.
    for (const uci of state.expected.slice(1)) {
      const result = await api("/validate", { fen, uci });
      const fields = fen.split(/\s+/);

      formattedMoves.push({
        number: Number(fields[5]) || 1,
        side: fields[1],
        san: result.san || uci
      });

      fen = result.fen;
    }

    $("move-list").innerHTML = formattedMoves.map((move, index) => {
      const previous = formattedMoves[index - 1];
      const prefix = move.side === "w"
        ? `${move.number}. `
        : (!previous || previous.number !== move.number
            ? `${move.number}... `
            : "");

      return `<span class="move-token">${prefix}${escapeHtml(move.san)}</span>`;
    }).join("");

    $("hint-text").textContent =
      "Solution revealed. Use Retry to solve it yourself.";
    setStatus(
      "Solution revealed",
      "Study the complete line, then retry the puzzle."
    );
    $("board").setAttribute("data-revealed", "true");
    renderBoard();
  } catch (error) {
    state.revealed = false;
    console.error("Could not reveal puzzle solution:", error);
    setStatus("Solution data error", error.message, "error");
    renderBoard();
  }
}
$("new-puzzle").addEventListener("click",loadPuzzle);
$("next-puzzle").addEventListener("click",loadPuzzle);
$("difficulty").addEventListener("change",loadPuzzle);
$("theme").addEventListener("change",loadPuzzle);
$("flip-board").addEventListener("click",()=>{state.orientation=state.orientation==="white"?"black":"white";renderBoard()});
$("reset-puzzle").addEventListener("click",retryPuzzle);
$("hint-button").addEventListener("click",getHint);
$("show-solution").addEventListener("click",revealSolution);

$("move-first").addEventListener("click", () => {
  if (positionHistory.length < 2) return;
  historyIndex = 0;
  state.selected = null;
  renderBoard();
});

$("move-previous").addEventListener("click", () => {
  if (historyIndex <= 0) return;
  historyIndex--;
  state.selected = null;
  renderBoard();
});

$("move-next").addEventListener("click", () => {
  if (historyIndex >= positionHistory.length - 1) return;
  historyIndex++;
  state.selected = null;
  renderBoard();
});

$("move-last").addEventListener("click", () => {
  if (!positionHistory.length) return;
  historyIndex = positionHistory.length - 1;
  state.selected = null;
  renderBoard();
});

document.addEventListener("keydown", event => {
  if (event.altKey || event.ctrlKey || event.metaKey) return;
  const el = event.target;
  if (el && (
    el.isContentEditable ||
    ["INPUT", "TEXTAREA", "SELECT"].includes(el.tagName)
  )) return;

  if (event.key === "ArrowLeft" && historyIndex > 0) {
    event.preventDefault();
    historyIndex--;
    state.selected = null;
    renderBoard();
  } else if (
    event.key === "ArrowRight" &&
    historyIndex < positionHistory.length - 1
  ) {
    event.preventDefault();
    historyIndex++;
    state.selected = null;
    renderBoard();
  } else if (event.key === "Home" && positionHistory.length > 1) {
    event.preventDefault();
    historyIndex = 0;
    state.selected = null;
    renderBoard();
  } else if (event.key === "End" && positionHistory.length > 1) {
    event.preventDefault();
    historyIndex = positionHistory.length - 1;
    state.selected = null;
    renderBoard();
  }
});

loadPuzzle();







