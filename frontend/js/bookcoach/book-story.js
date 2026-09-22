/**
 * Book Story / Lesson screen (spec §26 CENTER, §55). Renders the current
 * section's narrative, then any position/puzzle it contains, reusing
 * ChessMate's existing board + arrows renderer rather than building a new one
 * (spec §54). Drop this file into ChessMate/js/bookcoach/ — the relative
 * imports below assume that location.
 */
import { renderBoard, setArrows } from "../board.js";
import { BookCoachAPI } from "./api-client.js";
import { openSourceViewer } from "./source-viewer.js";

export async function renderStory(container, bookId, userId) {
  container.innerHTML = `<div class="bc-story">Loading…</div>`;

  let step;
  try {
    step = await BookCoachAPI.continueLesson(bookId, userId);
  } catch (err) {
    container.innerHTML = `<p class="bc-error">Couldn't load the lesson: ${err.message}</p>`;
    return;
  }

  if (step.type === "review_detour") {
    renderReviewDetour(container, bookId, userId, step);
    return;
  }

  const section = step.section;
  if (!section) {
    container.innerHTML = `<p class="bc-muted">You've reached the end of the book. 🎉</p>`;
    return;
  }

  const { narrative } = await BookCoachAPI.teachSection(bookId, section.id, userId);

  container.innerHTML = `
    <div class="bc-story">
      <div class="bc-story-crumbs">${escapeHtml(section.title)} · pages ${section.start_page}–${section.end_page}</div>
      <div class="bc-story-narrative">${renderNarrative(narrative)}</div>
      <div class="bc-story-board" id="bc-story-board"></div>
      <div class="bc-story-actions">
        <button class="bc-btn" id="bc-source-btn">View source</button>
        <button class="bc-btn bc-btn-accent" id="bc-next-btn">Continue</button>
      </div>
    </div>`;

  container.querySelector("#bc-source-btn").addEventListener("click", () =>
    openSourceViewer(bookId, section.id));
  container.querySelector("#bc-next-btn").addEventListener("click", () =>
    renderStory(container, bookId, userId));

  // If the section carries a position, ChessMate's own board component
  // renders it — actual position wiring depends on the API returning a FEN
  // for this section, left as a follow-up once /sections/{id}/teach also
  // returns associated position ids.
}

function renderReviewDetour(container, bookId, userId, step) {
  container.innerHTML = `
    <div class="bc-story bc-review-detour">
      <p>You seem to be missing the idea behind <strong>${escapeHtml(step.concept)}</strong>.
      Let's quickly revisit that.</p>
      <button class="bc-btn bc-btn-accent" id="bc-review-btn">Review it</button>
    </div>`;
  container.querySelector("#bc-review-btn").addEventListener("click", async () => {
    // Real flow: render step.review_section_id here, then on completion
    // call continueLesson() again, which resumes at step.resume_section_id
    // since the review detour never moved the Progress pointer (see
    // backend/app/coach/book_coach.py continue_lesson()).
    renderStory(container, bookId, userId);
  });
}

function renderNarrative(text) {
  // Narrative comes from the coach's LLM call (source-grounded, see
  // backend/app/coach/prompts.py) — render as paragraphs, no HTML trust.
  return String(text || "")
    .split(/\n{2,}/)
    .map((p) => `<p>${escapeHtml(p)}</p>`)
    .join("");
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}
