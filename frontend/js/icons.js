// ChessMate's icon set — one coherent family, drawn here, on one 24×24 grid.
//
// Why this file exists: the controls used to be text characters (⏮ ◀ ▶ ⏭ ⇅ ♪ ◐ 💡 📋 🏳).
// Each of those comes from whatever fallback font the platform picks, so stroke weight,
// size and vertical position all differed from icon to icon — and emoji don't follow
// `color` at all, so they ignore hover, disabled and theme states. These are original
// SVGs (no third-party assets): every one is a 2px round-capped stroke on currentColor,
// so they inherit the button's colour, dim when disabled, and scale with `1em`-based
// sizing wherever they sit.
//
// Markup convention: <span data-icon="prev"></span>. hydrateIcons() fills it in.
// Icon-only buttons must carry an aria-label (hydrateIcons copies it to `title` so
// there is always a tooltip, and warns in the console if a label is missing).

const P = {
  // navigation
  first: '<path d="M6 5v14"/><path d="M18 6l-8 6 8 6"/>',
  prev: '<path d="M15 5l-7 7 7 7"/>',
  next: '<path d="M9 5l7 7-7 7"/>',
  last: '<path d="M18 5v14"/><path d="M6 6l8 6-8 6"/>',
  flip: '<path d="M8 4v16"/><path d="M4.5 7.5L8 4l3.5 3.5"/><path d="M16 20V4"/><path d="M12.5 16.5L16 20l3.5-3.5"/>',
  reset: '<path d="M3.5 12a8.5 8.5 0 1 0 2.7-6.2"/><path d="M3.5 4.5v4.6h4.6"/>',
  // chevrons for collapsible sections
  down: '<path d="M6 9l6 6 6-6"/>',
  up: '<path d="M6 15l6-6 6 6"/>',
  right: '<path d="M9 6l6 6-6 6"/>',
  // status
  check: '<path d="M4.5 12.8l4.7 4.7L19.5 7"/>',
  cross: '<path d="M6 6l12 12"/><path d="M18 6L6 18"/>',
  warning: '<path d="M12 3.6L2.9 19.4h18.2z"/><path d="M12 10v4.4"/><path d="M12 17.2v.1"/>',
  info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v5.4"/><path d="M12 7.8v.1"/>',
  // tools
  settings: '<path d="M4 7h9"/><path d="M17 7h3"/><path d="M4 17h3"/><path d="M11 17h9"/><circle cx="15" cy="7" r="2.2"/><circle cx="9" cy="17" r="2.2"/>',
  hint: '<path d="M9.2 18h5.6"/><path d="M10 21h4"/><path d="M12 3a6 6 0 0 0-3.6 10.8c.7.6 1.1 1.3 1.1 2.2h5c0-.9.4-1.6 1.1-2.2A6 6 0 0 0 12 3z"/>',
  analysis: '<circle cx="10.5" cy="10.5" r="6.3"/><path d="M15.2 15.2L20.5 20.5"/>',
  book: '<path d="M5 4.5h11a3 3 0 0 1 3 3V20H8a3 3 0 0 1-3-3z"/><path d="M5 17a3 3 0 0 1 3-3h11"/>',
  target: '<circle cx="12" cy="12" r="8.5"/><circle cx="12" cy="12" r="4.5"/><path d="M12 12v.1"/>',
  coach: '<path d="M2.5 9.5L12 4.7l9.5 4.8L12 14.3z"/><path d="M6.4 11.6v4.6c1.4 1.6 3.4 2.4 5.6 2.4s4.2-.8 5.6-2.4v-4.6"/><path d="M21.5 9.5v5.5"/>',
  engine: '<path d="M13 2.8L5 13.6h6.2L10.6 21 19 10.2h-6.3z"/>',
  list: '<path d="M9 6.5h11"/><path d="M9 12h11"/><path d="M9 17.5h11"/><path d="M4 6.5v.1"/><path d="M4 12v.1"/><path d="M4 17.5v.1"/>',
  chart: '<path d="M4 4.5V20h16"/><path d="M8 15.5l3.6-4.6 3 2.8 4.4-6"/>',
  share: '<path d="M12 15V3.5"/><path d="M7.5 8L12 3.5 16.5 8"/><path d="M5 13v5.5A1.5 1.5 0 0 0 6.5 20h11a1.5 1.5 0 0 0 1.5-1.5V13"/>',
  link: '<path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1"/><path d="M14 10a4 4 0 0 0-5.7 0l-3 3A4 4 0 0 0 11 18.7l1-1"/>',
  copy: '<rect x="8.5" y="8.5" width="11" height="11" rx="2"/><path d="M15.5 8.5V6.5a2 2 0 0 0-2-2h-7a2 2 0 0 0-2 2v7a2 2 0 0 0 2 2h2"/>',
  download: '<path d="M12 4v11"/><path d="M7.5 11L12 15.5 16.5 11"/><path d="M5 19.5h14"/>',
  camera: '<path d="M4 8.5A1.5 1.5 0 0 1 5.5 7h2.2l1.2-2h6.2l1.2 2h2.2A1.5 1.5 0 0 1 20 8.5v9a1.5 1.5 0 0 1-1.5 1.5h-13A1.5 1.5 0 0 1 4 17.5z"/><circle cx="12" cy="13" r="3.4"/>',
  flag: '<path d="M6 21V4"/><path d="M6 5h11l-2.4 3.8L17 12.5H6"/>',
  swords: '<path d="M5 19L17.5 6.5"/><path d="M14 4h6v6"/><path d="M19 19L6.5 6.5"/><path d="M10 4H4v6"/>',
  play: '<path d="M8 5.5l11 6.5-11 6.5z"/>',
  plus: '<path d="M12 5v14"/><path d="M5 12h14"/>',
  sound: '<path d="M4 9.5h3.2L12 5.5v13l-4.8-4H4z"/><path d="M15.5 9a4.2 4.2 0 0 1 0 6"/><path d="M18 6.6a7.6 7.6 0 0 1 0 10.8"/>',
  mute: '<path d="M4 9.5h3.2L12 5.5v13l-4.8-4H4z"/><path d="M16 9.5l5 5"/><path d="M21 9.5l-5 5"/>',
  theme: '<circle cx="12" cy="12" r="8.5"/><path d="M12 3.5a8.5 8.5 0 0 1 0 17z" fill="currentColor"/>',
  eye: '<path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12z"/><circle cx="12" cy="12" r="2.8"/>',
  eyeoff: '<path d="M3 3l18 18"/><path d="M10.2 5.7A9.7 9.7 0 0 1 12 5.5c6 0 9.5 6.5 9.5 6.5a17 17 0 0 1-3 3.7"/><path d="M6.4 7.6A16.4 16.4 0 0 0 2.5 12S6 18.5 12 18.5c1.4 0 2.7-.3 3.8-.9"/>',
  // tactical patterns (used on tactic chips and the training panel)
  fork: '<path d="M12 21V10.5"/><path d="M5.5 4v3.5a6.5 6.5 0 0 0 13 0V4"/><path d="M12 4v6.5"/>',
  pin: '<path d="M12 21v-5.5"/><path d="M8.5 3.5h7L14.3 9.4 17.5 13H6.5l3.2-3.6z"/>',
  skewer: '<path d="M3.5 20.5L20.5 3.5"/><circle cx="9" cy="15" r="2.4"/><circle cx="15" cy="9" r="2.4"/>',
  discovered: '<path d="M3.5 12h5"/><path d="M15.5 12h5"/><rect x="8.5" y="8" width="7" height="8" rx="1.5" stroke-dasharray="2.6 2.4"/><path d="M12 4v2.2"/><path d="M12 17.8V20"/>',
  double: '<path d="M4 7h11"/><path d="M11.5 3.5L15 7l-3.5 3.5"/><path d="M4 17h11"/><path d="M11.5 13.5L15 17l-3.5 3.5"/><path d="M20 4v16" stroke-dasharray="1.5 3"/>',
  mate: '<path d="M12 3.5v4"/><path d="M9.8 5.5h4.4"/><path d="M7 20.5l1.4-8.2a3.6 3.6 0 0 1 7.2 0L17 20.5z"/>',
};

// The ChessMate mark: a 2×2 board with the analysis arrow running across it. Original —
// it is the product's own subject (a position and an arrow), not a piece silhouette.
const LOGO =
  '<svg class="brandmark" viewBox="0 0 32 32" aria-hidden="true" focusable="false">' +
  '<rect width="32" height="32" rx="7" fill="var(--sq-d)"/>' +
  '<rect x="16" y="0" width="16" height="16" fill="var(--sq-l)"/>' +
  '<rect x="0" y="16" width="16" height="16" fill="var(--sq-l)"/>' +
  '<path d="M9 23.5L22.5 10" stroke="var(--logo-arrow,#e58e26)" stroke-width="3.6" stroke-linecap="round" fill="none"/>' +
  '<path d="M15.6 9.6h7.6v7.6z" fill="var(--logo-arrow,#e58e26)"/>' +
  "</svg>";

export const ICON_NAMES = Object.keys(P);

// Inline SVG markup for an icon. `cls` adds classes to the <svg>.
export function icon(name, cls = "") {
  const body = P[name];
  if (!body) return "";
  return '<svg class="ico' + (cls ? " " + cls : "") + '" viewBox="0 0 24 24" fill="none" ' +
    'stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" ' +
    'aria-hidden="true" focusable="false">' + body + "</svg>";
}

export const logoSvg = () => LOGO;

// Fill every <span data-icon="name"> under `root`. Idempotent (safe to call on markup
// that was built later), and it never overwrites an element that already holds an <svg>.
export function hydrateIcons(root = document) {
  root.querySelectorAll("[data-icon]").forEach((node) => {
    if (node.querySelector("svg")) return;
    const name = node.dataset.icon;
    if (name === "logo") { node.innerHTML = LOGO; return; }
    if (!P[name]) { console.warn("icons: unknown icon '" + name + "'"); return; }
    node.innerHTML = icon(name);
    // An icon-only control must be nameable by assistive tech, and should show a
    // tooltip. Borrow the label from the nearest button if the span doesn't have one.
    const btn = node.closest("button, a, [role=button]");
    if (btn && !btn.textContent.trim()) {
      const label = btn.getAttribute("aria-label") || btn.getAttribute("title");
      if (!label) console.warn("icons: icon-only control has no aria-label:", btn.id || btn.className);
      else {
        if (!btn.getAttribute("aria-label")) btn.setAttribute("aria-label", label);
        if (!btn.getAttribute("title")) btn.setAttribute("title", label);
      }
    }
  });
}
