import { chromium } from "playwright";

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1280, height: 1400 } });

try {
  await page.goto("http://localhost:8787", { waitUntil: "networkidle" });
  await page.waitForFunction(
    () => document.getElementById("engineStatus")?.textContent === "ready",
    null,
    { timeout: 60000 }
  );

  const coords = async sq => page.locator(`[data-sq="${sq}"]`).evaluate(el => {
    const r = el.getBoundingClientRect();
    return { x: r.x + r.width / 2, y: r.y + r.height / 2 };
  });

  const a = await coords("d2");
  const b = await coords("d4");

  await page.mouse.move(a.x, a.y);
  await page.mouse.down();

  console.log("AFTER DOWN", await page.evaluate(() => {
    const p = document.querySelector(".pc.dragging");
    return {
      draggingCount: document.querySelectorAll(".pc.dragging").length,
      className: p?.className ?? null,
      transform: p?.style.transform ?? null,
      connected: p?.isConnected ?? false
    };
  }));

  await page.mouse.move(b.x, b.y, { steps: 6 });

  console.log("AFTER MOVE", await page.evaluate(() => {
    const p = document.querySelector(".pc.dragging");
    return {
      draggingCount: document.querySelectorAll(".pc.dragging").length,
      className: p?.className ?? null,
      transform: p?.style.transform ?? null,
      connected: p?.isConnected ?? false,
      hoveredSquares: document.querySelectorAll(".sq.over").length
    };
  }));

  await page.mouse.up();
} finally {
  await browser.close();
}
