/**
 * Book Puzzle screen (spec §14-§18, §58): shows the position, takes the
 * user's move, and drives the acknowledge -> explain -> hint -> retry flow
 * on a wrong answer rather than just saying "wrong". Reuses ChessMate's
 * board renderer (spec §54).
 */
import { renderBoard } from "../board.js";
import { BookCoachAPI } from "./api-client.js";

export async function renderPuzzle(container, puzzleId, bookId, userId) {
  const puzzle = await BookCoachAPI.getPuzzle(puzzleId, userId, bookId);

  container.innerHTML = `
    <div class="bc-puzzle">
      <div class="bc-puzzle-header">
        ${puzzle.source === "generated"
          ? `<span class="bc-badge bc-badge-generated">ChessMate application exercise</span>`
          : `<span class="bc-badge bc-badge-book">Book puzzle</span>`}
        <span class="bc-muted">${escapeHtml(puzzle.original_text || "")}</span>
      </div>
      <div class="bc-puzzle-board" id="bc-puzzle-board"></div>
      <form id="bc-move-form">
        <input type="text" id="bc-move-input" placeholder="Your move (e.g. Nf5)" autocomplete="off" />
        <button type="submit" class="bc-btn bc-btn-accent">Play move</button>
      </form>
      <div class="bc-puzzle-actions">
        <button class="bc-btn" id="bc-hint-btn">Hint</button>
        <button class="bc-btn" id="bc-solution-btn">Show solution</button>
      </div>
      <div class="bc-puzzle-feedback" id="bc-puzzle-feedback"></div>
    </div>`;

  // NOTE: the puzzle's FEN comes from Position.fen; if it's null (unverified
  // diagram reconstruction, spec §46), render the original page image
  // (Position.raw_image_ref) instead of a board and disable move input —
  // that branch isn't wired here since the API doesn't return the FEN yet.

  const feedbackEl = container.querySelector("#bc-puzzle-feedback");

  container.querySelector("#bc-move-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const move = container.querySelector("#bc-move-input").value.trim();
    if (!move) return;
    const result = await BookCoachAPI.submitMove(puzzleId, move, userId, bookId);
    renderFeedback(feedbackEl, result);
  });

  container.querySelector("#bc-hint-btn").addEventListener("click", async () => {
    const { hint } = await BookCoachAPI.getHint(puzzleId, userId, bookId);
    feedbackEl.innerHTML = `<p class="bc-hint">${escapeHtml(hint)}</p>`;
  });

  container.querySelector("#bc-solution-btn").addEventListener("click", async () => {
    const solution = await BookCoachAPI.showSolution(puzzleId, userId, bookId);
    feedbackEl.innerHTML = `
      <p class="bc-solution"><strong>Solution:</strong> ${solution.solution_line_san.join(" ")}</p>
      <p>${escapeHtml(solution.author_explanation || "")}</p>`;
  });
}

function renderFeedback(el, result) {
  if (result.correct) {
    el.innerHTML = `
      <p class="bc-correct">Yes — that's the move the author is demonstrating.</p>
      <p>${escapeHtml(result.explanation || "")}</p>`;
  } else {
    // Full acknowledge -> problem -> hint text is produced server-side by
    // explain_mistake() (backend/app/coach/book_coach.py) once its LLM call
    // is wired up; this renders whatever structured fields come back.
    el.innerHTML = `
      <p class="bc-incorrect">Not quite — ${escapeHtml(result.attempted_idea || "let's look closer")}.</p>
      <p class="bc-muted">Try again, or use a hint.</p>`;
  }
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}
