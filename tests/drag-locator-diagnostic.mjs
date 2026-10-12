import { chromium } from "playwright";

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1280, height: 1400 } });
await page.goto("http://localhost:8787", { waitUntil: "networkidle" });
await page.waitForFunction(
  () => document.getElementById("engineStatus")?.textContent === "ready",
  null,
  { timeout: 60000 }
);

async function check(label, sq) {
  const loc = page.locator('[data-sq="' + sq + '"]');
  console.log(label, sq, {
    count: await loc.count(),
    visible: await loc.isVisible(),
    box: await loc.boundingBox(),
    evaluate: await loc.evaluate(el => {
      const r = el.getBoundingClientRect();
      return {
        connected: el.isConnected,
        rect: [r.x, r.y, r.width, r.height],
        display: getComputedStyle(el).display,
        visibility: getComputedStyle(el).visibility
      };
    })
  });
}

await check("initial", "e2");
await check("initial", "e4");

const a = await page.locator('[data-sq="e2"]').boundingBox();
if (!a) throw new Error("e2 box missing at start");
const b = await page.locator('[data-sq="e4"]').boundingBox();
if (!b) throw new Error("e4 box missing at start");

await page.mouse.move(a.x + a.width / 2, a.y + a.height / 2);
await page.mouse.down();
await page.mouse.move(b.x + b.width / 2, b.y + b.height / 2, { steps: 8 });
await page.mouse.up();
await page.waitForTimeout(150);

await check("after e2-e4", "e4");
await check("after e2-e4", "e7");

await browser.close();
