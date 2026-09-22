/**
 * Book Library screen (spec §26 LEFT nav source, §51 dashboard entry point).
 * Renders the list of uploaded books; clicking one opens book-dashboard.js.
 */
import { BookCoachAPI } from "./api-client.js";

export async function renderLibrary(container, { onOpenBook, onUpload }) {
  container.innerHTML = `
    <div class="bc-library">
      <div class="bc-library-header">
        <h2>Your books</h2>
        <button class="bc-btn bc-btn-accent" id="bc-upload-btn">Upload PDF</button>
      </div>
      <div class="bc-library-list" id="bc-library-list">Loading…</div>
    </div>`;

  container.querySelector("#bc-upload-btn").addEventListener("click", () => onUpload());

  const listEl = container.querySelector("#bc-library-list");
  try {
    const books = await BookCoachAPI.listBooks();
    if (!books.length) {
      listEl.innerHTML = `<p class="bc-muted">No books yet — upload a PDF to get started.</p>`;
      return;
    }
    listEl.innerHTML = "";
    for (const book of books) {
      const card = document.createElement("div");
      card.className = "bc-card bc-book-card";
      card.innerHTML = `
        <div class="bc-book-title">${escapeHtml(book.title)}</div>
        <div class="bc-book-author">${escapeHtml(book.author || "")}</div>
        <div class="bc-book-status bc-status-${book.status}">${book.status}</div>`;
      card.addEventListener("click", () => onOpenBook(book.id));
      listEl.appendChild(card);
    }
  } catch (err) {
    listEl.innerHTML = `<p class="bc-error">Couldn't load your books: ${escapeHtml(err.message)}</p>`;
  }
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}
