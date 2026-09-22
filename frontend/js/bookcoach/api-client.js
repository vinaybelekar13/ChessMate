/**
 * Thin fetch wrapper for the Book Coach backend (see ../../ARCHITECTURE.md).
 * The rest of ChessMate is server-less by design; only these Book Coach
 * screens talk to a network backend, so the base URL is configurable and
 * defaults to localhost for local development against the scaffold in
 * ../../backend/.
 */
const BASE = window.BOOK_COACH_API_BASE || "http://localhost:8080";

async function request(path, opts = {}) {
  const res = await fetch(BASE + path, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new Error(`Book Coach API ${res.status} on ${path}: ${body}`);
  }
  const ct = res.headers.get("content-type") || "";
  return ct.includes("application/json") ? res.json() : res.text();
}

export const BookCoachAPI = {
  listBooks: () => request("/books"),
  getBook: (bookId) => request(`/books/${bookId}`),
  getStructure: (bookId) => request(`/books/${bookId}/structure`),
  getCoverage: (bookId) => request(`/books/${bookId}/coverage`),

  uploadBook: async (file) => {
    const form = new FormData();
    form.append("file", file);
    const res = await fetch(BASE + "/books/upload", { method: "POST", body: form });
    if (!res.ok) throw new Error(`Upload failed: ${res.status}`);
    return res.json();
  },
  getIngestionStatus: (bookId) => request(`/books/${bookId}/ingestion-status`),

  startBook: (bookId, userId) =>
    request(`/books/${bookId}/start?user_id=${encodeURIComponent(userId)}`, { method: "POST" }),
  resume: (bookId, userId) =>
    request(`/books/${bookId}/resume?user_id=${encodeURIComponent(userId)}`),
  continueLesson: (bookId, userId) =>
    request(`/books/${bookId}/continue?user_id=${encodeURIComponent(userId)}`, { method: "POST" }),
  skipSection: (bookId, sectionId, userId) =>
    request(`/books/${bookId}/sections/${sectionId}/skip?user_id=${encodeURIComponent(userId)}`,
      { method: "POST" }),
  teachSection: (bookId, sectionId, userId, depth = "normal") =>
    request(`/books/${bookId}/sections/${sectionId}/teach?user_id=${encodeURIComponent(userId)}&depth=${depth}`),

  getPuzzle: (puzzleId, userId, bookId) =>
    request(`/puzzles/${puzzleId}?user_id=${encodeURIComponent(userId)}&book_id=${bookId}`),
  submitMove: (puzzleId, moveSan, userId, bookId) =>
    request(`/puzzles/${puzzleId}/attempt?user_id=${encodeURIComponent(userId)}&book_id=${bookId}`, {
      method: "POST",
      body: JSON.stringify({ move_san: moveSan }),
    }),
  getHint: (puzzleId, userId, bookId) =>
    request(`/puzzles/${puzzleId}/hint?user_id=${encodeURIComponent(userId)}&book_id=${bookId}`),
  showSolution: (puzzleId, userId, bookId) =>
    request(`/puzzles/${puzzleId}/solution?user_id=${encodeURIComponent(userId)}&book_id=${bookId}`,
      { method: "POST" }),

  searchBook: (bookId, query) =>
    request(`/books/${bookId}/search?q=${encodeURIComponent(query)}`),
};
