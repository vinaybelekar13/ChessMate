import { chromium } from "playwright";

const browser = await chromium.launch();
try {
  const page = await browser.newPage();
  const errors = [];
  page.on("pageerror", e => errors.push(e.message));

  await page.goto("http://localhost:8787", { waitUntil: "networkidle" });
  await page.waitForFunction(
    () => document.getElementById("engineStatus")?.textContent === "ready",
    null,
    { timeout: 60000 }
  );

  const snapshot = async label => console.log(label, JSON.stringify(
    await page.evaluate(() => ({
      status: document.getElementById("engineStatus")?.textContent,
      e2: document.querySelectorAll('[data-sq="e2"] .pc').length,
      e4: document.querySelectorAll('[data-sq="e4"] .pc').length,
      selected: document.querySelectorAll(".sq.sel").length,
      targets: document.querySelectorAll(".target").length,
      dragging: document.querySelectorAll(".pc.dragging").length,
      grabbable: document.querySelectorAll(".sq.grabbable").length,
      board: (() => {
        const b = document.getElementById("board");
        const r = b?.getBoundingClientRect();
        return r && { x:r.x, y:r.y, width:r.width, height:r.height };
      })()
    }))
  ));

  await snapshot("BEFORE");

  const from = await page.locator('[data-sq="e2"]').boundingBox();
  const to = await page.locator('[data-sq="e4"]').boundingBox();
  if (!from || !to) throw new Error("Board squares e2/e4 not found");

  await page.mouse.move(from.x + from.width / 2, from.y + from.height / 2);
  await page.mouse.down();
  await page.waitForTimeout(100);
  await snapshot("AFTER POINTER DOWN");

  await page.mouse.move(to.x + to.width / 2, to.y + to.height / 2, { steps: 8 });
  await snapshot("DURING DRAG");

  await page.mouse.up();
  await page.waitForTimeout(300);
  await snapshot("AFTER POINTER UP");

  console.log("PAGE ERRORS:", JSON.stringify(errors));
} finally {
  await browser.close();
}
