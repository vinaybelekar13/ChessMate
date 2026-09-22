/**
 * MagnusCoachBubble (integration spec §15-18): a small, reusable coach
 * avatar + speech bubble. Deliberately NOT an animation framework — one
 * component, one deterministic message-per-state table, done.
 *
 * These are ChessMate coach lines, never quotations from Magnus Carlsen
 * (spec §16) — the wording below says "the model" / "the engine" / "Magnus
 * played" rather than "Magnus would/says", exactly per the spec's example
 * phrasing.
 */

const MESSAGES = {
  main: "Look carefully at this position.",
  mistake: "Wait — there is a concrete problem here.",
  blunder: "This changes the position immediately. Let's see why.",
  good_move: "Nice. You found the important idea.",
  training: "Take your time. What is your opponent threatening?",
  wrong_training: "Not quite. Let's look at what your move allows.",
  correct_training: "Exactly. That's the idea.",
  tactical: "Before calculating, look for checks, captures and threats.",
  engine_disagreement: "Interesting. The engine sees something different. Let's investigate.",
  historical_match: "Magnus reached a similar position in a real game.",
  book_concept: "This connects directly to the idea from your book.",
  book_puzzle: "Take your time and find the author's idea.",
};

const VALID_STATES = new Set(Object.keys(MESSAGES));

/**
 * Renders (or updates in place) the coach bubble inside `container`.
 * @param {{message?: string, state?: string, visible?: boolean}} props
 * @param {HTMLElement} container - an existing element in the current
 *   layout (e.g. the Coach card). This never resizes or repositions its
 *   parent — it only fills whatever box it's given (spec §18/§19).
 */
export function renderMagnusBubble(props, container) {
  if (!container) return;
  const state = VALID_STATES.has(props.state) ? props.state : "main";
  const message = props.message || MESSAGES[state];
  const visible = props.visible !== false;

  if (!container.querySelector(".magnus-bubble")) {
    container.insertAdjacentHTML(
      "beforeend",
      `<div class="magnus-bubble" role="status" aria-live="polite">
         <span class="magnus-avatar" aria-hidden="true">&#9820;</span>
         <span class="magnus-speech"></span>
       </div>`
    );
  }
  const root = container.querySelector(".magnus-bubble");
  root.hidden = !visible;
  root.dataset.state = state;
  root.querySelector(".magnus-speech").textContent = message;
}

/** Look up the deterministic default line for a state without rendering — used
 * by callers that build their own evidence-driven message but want the
 * spec's baseline copy as a fallback. */
export function defaultMessageFor(state) {
  return MESSAGES[state] || MESSAGES.main;
}
