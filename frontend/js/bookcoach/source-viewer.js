/**
 * Source Panel / Viewer (spec §25): shows book/chapter/section/page and a
 * "View page" affordance back to the original scanned/rasterized page.
 */
export function openSourceViewer(bookId, sectionId) {
  const modal = document.createElement("div");
  modal.className = "bc-modal";
  modal.innerHTML = `
    <div class="bc-modal-content">
      <button class="bc-modal-close" aria-label="Close">&times;</button>
      <p class="bc-muted">Source for section ${sectionId} of book ${bookId}.</p>
      <p class="bc-muted">Full page image rendering needs the section's
      Page.image_ref wired through the API — see backend/app/api/routes/books.py.</p>
    </div>`;
  modal.querySelector(".bc-modal-close").addEventListener("click", () => modal.remove());
  document.body.appendChild(modal);
}
