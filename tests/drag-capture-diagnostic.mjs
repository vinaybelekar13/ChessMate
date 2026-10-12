import { chromium } from "playwright";

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1280, height: 1400 } });
page.on("pageerror", e => console.log("PAGE ERROR:", e.message));

try {
  await page.goto("http://localhost:8787", { waitUntil: "networkidle" });
  await page.waitForFunction(
    () => document.getElementById("engineStatus")?.textContent === "ready",
    null,
    { timeout: 60000 }
  );

  const inspect = async label => {
    console.log(label, await page.evaluate(() => ({
      url: location.href,
      fen: document.querySelector("#fenInput")?.value ?? null,
      boardExists: !!document.querySelector("#board"),
      squareCount: document.querySelectorAll("[data-sq]").length,
      d7Count: document.querySelectorAll('[data-sq="d7"]').length,
      d7: [...document.querySelectorAll('[data-sq="d7"]')].map(el => ({
        connected: el.isConnected,
        rect: (() => {
          const r = el.getBoundingClientRect();
          return { x: r.x, y: r.y, width: r.width, height: r.height };
        })()
      })),
      moveList: document.getElementById("movelist")?.textContent ?? null
    })));
  };

  await inspect("INITIAL");

  for (const [from, to] of [["e2", "e4"], ["d7", "d5"]]) {
    const start = await page.locator(`[data-sq="${from}"]`).evaluate(el => {
      const r = el.getBoundingClientRect();
      return { x: r.x + r.width / 2, y: r.y + r.height / 2 };
    });
    const end = await page.locator(`[data-sq="${to}"]`).evaluate(el => {
      const r = el.getBoundingClientRect();
      return { x: r.x + r.width / 2, y: r.y + r.height / 2 };
    });

    await page.mouse.move(start.x, start.y);
    await page.mouse.down();
    await page.mouse.move(end.x, end.y, { steps: 8 });
    await page.mouse.up();
    await page.waitForTimeout(200);
    await inspect(`${from}-${to}`);
  }
} finally {
  await browser.close();
}
