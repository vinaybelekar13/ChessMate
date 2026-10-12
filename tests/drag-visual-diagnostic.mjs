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

for (const name of ["d2", "d4"]) {
  const sq = page.locator('[data-sq="' + name + '"]');
  await sq.waitFor({ state: "visible", timeout: 10000 }).catch(() => {});
  console.log(name, await page.evaluate((n) => {
    const s = document.querySelector('[data-sq="' + n + '"]');
    const r = s?.getBoundingClientRect();
    const b = document.getElementById("board")?.getBoundingClientRect();
    return {
      count: document.querySelectorAll('[data-sq="' + n + '"]').length,
      rect: r ? [r.x, r.y, r.width, r.height] : null,
      boardRect: b ? [b.x, b.y, b.width, b.height] : null,
      visibility: s ? getComputedStyle(s).visibility : null,
      display: s ? getComputedStyle(s).display : null,
      squares: document.querySelectorAll("[data-sq]").length
    };
  }, name));
}

const a = await page.locator('[data-sq="d2"]').boundingBox();
if (!a) throw new Error("d2 has no bounding box");
await page.mouse.move(a.x + a.width / 2, a.y + a.height / 2);
await page.mouse.down();
await page.waitForTimeout(100);

console.log("AFTER PRESS:", await page.evaluate(() => {
  const p = document.querySelector(".pc.dragging");
  return {
    found: !!p,
    transform: p?.style.transform ?? null,
    over: document.querySelectorAll(".sq.over").length
  };
}));

await page.mouse.move(a.x + a.width / 2, a.y + a.height / 2 - 60, { steps: 3 });
console.log("AFTER MOVE:", await page.evaluate(() => {
  const p = document.querySelector(".pc.dragging");
  return {
    found: !!p,
    transform: p?.style.transform ?? null,
    over: document.querySelectorAll(".sq.over").length
  };
}));

await page.mouse.up();
await browser.close();
