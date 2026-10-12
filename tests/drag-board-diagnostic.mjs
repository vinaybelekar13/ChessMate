import { chromium } from "playwright";

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1280, height: 1400 } });
page.on("pageerror", e => console.log("PAGE ERROR:", e.message));

await page.goto("http://localhost:8787", { waitUntil: "networkidle" });
await page.waitForFunction(
  () => document.getElementById("engineStatus")?.textContent === "ready",
  null,
  { timeout: 60000 }
);

async function centre(sq) {
  const el = page.locator('[data-sq="' + sq + '"]');
  await el.waitFor({ state: "attached", timeout: 5000 });
  const r = await el.boundingBox();
  if (!r) throw new Error("No bounding box for " + sq);
  return { x: r.x + r.width / 2, y: r.y + r.height / 2 };
}

async function drag(from, to) {
  const a = await centre(from);
  const b = await centre(to);
  await page.mouse.move(a.x, a.y);
  await page.mouse.down();
  await page.mouse.move(b.x, b.y, { steps: 8 });
  await page.mouse.up();
  await page.waitForTimeout(150);
}

console.log("BEFORE:", await page.evaluate(() => ({
  squares: document.querySelectorAll("[data-sq]").length,
  e5: (() => {
    const s = document.querySelector('[data-sq="e5"]');
    const r = s?.getBoundingClientRect();
    return { exists: !!s, rect: r ? [r.x, r.y, r.width, r.height] : null };
  })()
})));

await drag("e2", "e4");

console.log("AFTER WHITE e2-e4:", await page.evaluate(() => {
  const b = document.getElementById("board");
  const s = document.querySelector('[data-sq="e5"]');
  const r = s?.getBoundingClientRect();
  const br = b?.getBoundingClientRect();
  return {
    squares: document.querySelectorAll("[data-sq]").length,
    e5Exists: !!s,
    e5Rect: r ? [r.x, r.y, r.width, r.height] : null,
    e5Display: s ? getComputedStyle(s).display : null,
    e5Visibility: s ? getComputedStyle(s).visibility : null,
    boardRect: br ? [br.x, br.y, br.width, br.height] : null,
    viewport: [innerWidth, innerHeight],
    scroll: [scrollX, scrollY],
    moves: document.getElementById("movelist")?.textContent
  };
}));

await browser.close();
