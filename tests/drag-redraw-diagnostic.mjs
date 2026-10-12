import { chromium } from "playwright";
import fs from "node:fs";

const base = "http://localhost:8787";
const sourcePath = "./js/app.js";
const source = fs.readFileSync(sourcePath, "utf8");

const needle = "function drawBoard() {";
if (!source.includes(needle)) {
  throw new Error("Could not find drawBoard() in js/app.js; no files changed.");
}

const instrumented = source.replace(
  needle,
  `${needle}
  window.__drawBoardTrace ??= [];
  window.__drawBoardTrace.push({
    time: performance.now(),
    stack: new Error("drawBoard trace").stack,
    dragging: document.querySelectorAll(".pc.dragging").length,
    buttons: window.__lastPointerButtons ?? null
  });`
);

const browser = await chromium.launch({ headless: true });
try {
  const page = await browser.newPage({
    viewport: { width: 1280, height: 1400 }
  });

  page.on("pageerror", error =>
    console.log("PAGE_ERROR", error.message)
  );

  await page.route("**/js/app.js?v=36", async route => {
    const response = await route.fetch();
    await route.fulfill({
      response,
      body: instrumented
    });
  });

  await page.route(
    /(?:explorer|tablebase)\.lichess\.ovh/,
    route => route.abort()
  );

  await page.goto(base, { waitUntil: "networkidle" });
  await page.waitForFunction(
    () => document.getElementById("engineStatus")?.textContent === "ready",
    null,
    { timeout: 60000 }
  );

  const centre = async square => {
    const handle = await page.waitForFunction(name => {
      const el = [...document.querySelectorAll("[data-sq]")]
        .find(node => node.dataset.sq === name && node.isConnected);
      if (!el) return false;
      const r = el.getBoundingClientRect();
      if (!r.width || !r.height) return false;
      return { x: r.x + r.width / 2, y: r.y + r.height / 2 };
    }, square);
    return handle.jsonValue();
  };

  const from = await centre("d2");
  const to = await centre("d4");

  await page.evaluate(() => {
    window.__drawBoardTrace = [];
    window.__lastPointerButtons = null;
    window.addEventListener("pointermove", e => {
      window.__lastPointerButtons = e.buttons;
    }, true);
  });

  await page.mouse.move(from.x, from.y);
  await page.mouse.down();

  await page.waitForTimeout(50);
  await page.mouse.move(to.x, to.y, { steps: 6 });
  await page.waitForTimeout(50);

  const trace = await page.evaluate(() => ({
    dragging: [...document.querySelectorAll(".pc.dragging")].map(el => ({
      square: el.closest("[data-sq]")?.dataset.sq,
      transform: el.style.transform,
      connected: el.isConnected
    })),
    redraws: window.__drawBoardTrace || []
  }));

  console.log(JSON.stringify(trace, null, 2));
  await page.mouse.up();
} finally {
  await browser.close();
}
