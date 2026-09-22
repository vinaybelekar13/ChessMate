/**
 * Upload + processing screen (spec §50). Polls ingestion-status so the
 * "Reading pages / Finding chapters / …" stages reflect the backend's real
 * progress, not a fake timer.
 */
import { BookCoachAPI } from "./api-client.js";

export function renderUpload(container, { onReady }) {
  container.innerHTML = `
    <div class="bc-upload">
      <input type="file" id="bc-file-input" accept="application/pdf" />
      <div id="bc-upload-status" class="bc-muted"></div>
    </div>`;

  const input = container.querySelector("#bc-file-input");
  const statusEl = container.querySelector("#bc-upload-status");

  input.addEventListener("change", async () => {
    const file = input.files[0];
    if (!file) return;
    statusEl.textContent = "Uploading…";
    try {
      const { book_id } = await BookCoachAPI.uploadBook(file);
      pollStatus(book_id);
    } catch (err) {
      statusEl.textContent = `Upload failed: ${err.message}`;
    }
  });

  function pollStatus(bookId) {
    const tick = async () => {
      try {
        const { step, counts } = await BookCoachAPI.getIngestionStatus(bookId);
        statusEl.textContent = counts && Object.keys(counts).length
          ? `${step} (${Object.entries(counts).map(([k, v]) => `${v} ${k}`).join(", ")})`
          : step;
        if (step === "Book ready") {
          onReady(bookId);
          return;
        }
        if (step === "Failed") return;
        setTimeout(tick, 1500);
      } catch (err) {
        statusEl.textContent = `Error checking progress: ${err.message}`;
      }
    };
    tick();
  }
}
