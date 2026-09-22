/**
 * Wires the pre-existing Book Coach screens (js/bookcoach/*.js — untouched)
 * into ChessMate's "mode" tab bar as one additional tab, per the integration
 * spec's "small additive component, no redesign" rule (§18-19).
 *
 * Nothing here changes Analyze/Free board/Play engine. This module is only
 * imported and only runs its DOM work when the person clicks the new "Book"
 * tab (see js/app.js's tiny hook — search for "book-coach-entry").
 */
import { renderLibrary } from "../bookcoach/book-library.js";
import { renderDashboard } from "../bookcoach/book-dashboard.js";
import { renderStory } from "../bookcoach/book-story.js";
import { renderPuzzle } from "../bookcoach/book-puzzle.js";
import { renderUpload } from "../bookcoach/book-upload.js";

const USER_ID = "local-user"; // single-user local app, per ARCHITECTURE.md §0/§8

let mounted = false;

export function mountBookCoach(container) {
  if (!container) return;
  showLibrary(container);
  mounted = true;
}

export function isBookCoachMounted() {
  return mounted;
}

function showLibrary(container) {
  renderLibrary(container, {
    onOpenBook: (bookId) => showDashboard(container, bookId),
    onUpload: () => showUpload(container),
  }).catch((err) => showError(container, err));
}

function showUpload(container) {
  renderUpload(container, {
    onReady: (bookId) => showDashboard(container, bookId),
  });
}

function showDashboard(container, bookId) {
  renderDashboard(container, bookId, {
    onStart: () => showStory(container, bookId),
    onSearch: () => showStory(container, bookId), // dashboard's search entry reuses story view's search box
  }).catch((err) => showError(container, err));
}

function showStory(container, bookId) {
  renderStory(container, bookId, USER_ID).catch((err) => showError(container, err));
}

// Exposed for book-story.js / book-dashboard.js to jump into a puzzle by id
// without each of those modules needing to import book-puzzle.js themselves.
window.__chessmateOpenPuzzle = (container, puzzleId, bookId) => {
  renderPuzzle(container, puzzleId, bookId, USER_ID).catch((err) => showError(container, err));
};

function showError(container, err) {
  container.innerHTML = `<div class="bc-dashboard"><p class="bc-muted">Book Coach backend unavailable: ${escapeHtml(
    String(err && err.message ? err.message : err)
  )}</p></div>`;
}

function escapeHtml(s) {
  return s.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
