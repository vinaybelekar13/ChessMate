import { chromium } from "playwright";

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1280, height: 1400 } });

await page.goto("http://localhost:8787", { waitUntil: "networkidle" });
await page.waitForFunction(
  () => document.getElementById("engineStatus")?.textContent === "ready",
  null,
  { timeout: 60000 }
);

console.log("DRAW_BOARD_ACCESS", JSON.stringify(await page.evaluate(() => ({
  windowFunction: typeof window.drawBoard,
  scriptCount: document.scripts.length,
  boardExists: !!document.querySelector("#board"),
  squares: document.querySelectorAll("#board [data-sq]").length
}))));

await browser.close();
