/**
 * Book dashboard (spec §51): chapter/section/puzzle/game counts, coverage,
 * and the entry points into Story mode, Puzzles, and Search.
 */
import { BookCoachAPI } from "./api-client.js";

export async function renderDashboard(container, bookId, { onStart, onSearch }) {
  container.innerHTML = `<div class="bc-dashboard">Loading…</div>`;
  const [book, coverage] = await Promise.all([
    BookCoachAPI.getBook(bookId),
    BookCoachAPI.getCoverage(bookId),
  ]);

  container.innerHTML = `
    <div class="bc-dashboard">
      <h2>${escapeHtml(book.title)}</h2>
      <p class="bc-muted">${escapeHtml(book.author || "")}</p>
      <div class="bc-coverage">
        ${coverageRow("Chapters", coverage.chapters)}
        ${coverageRow("Sections", coverage.sections)}
        ${coverageRow("Puzzles", coverage.puzzles)}
        ${coverageRow("Positions", coverage.positions)}
      </div>
      <div class="bc-dashboard-actions">
        <button class="bc-btn bc-btn-accent" id="bc-start-btn">Start / Continue</button>
        <button class="bc-btn" id="bc-search-btn">Ask the book</button>
      </div>
    </div>`;

  container.querySelector("#bc-start-btn").addEventListener("click", () => onStart(bookId));
  container.querySelector("#bc-search-btn").addEventListener("click", () => onSearch(bookId));
}

function coverageRow(label, stat) {
  const total = stat && stat.total != null ? stat.total : "—";
  return `<div class="bc-coverage-row"><span>${label}</span><span>${total}</span></div>`;
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}
