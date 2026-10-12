import { chromium } from "playwright";

const browser = await chromium.launch();
try {
  const page = await browser.newPage();
  await page.goto("http://localhost:8787", { waitUntil: "networkidle" });
  await page.waitForFunction(
    () => document.getElementById("engineStatus")?.textContent === "ready",
    null,
    { timeout: 60000 }
  );

  console.log("BEFORE:", JSON.stringify(await page.locator("#movelist").innerText()));

  const from = await page.locator('[data-sq="e2"]').boundingBox();
  const to = await page.locator('[data-sq="e4"]').boundingBox();

  if (!from || !to) throw new Error("Could not locate e2/e4 board squares.");

  await page.mouse.move(from.x + from.width / 2, from.y + from.height / 2);
  await page.mouse.down();
  await page.mouse.move(to.x + to.width / 2, to.y + to.height / 2, { steps: 8 });
  await page.mouse.up();
  await page.waitForTimeout(200);

  console.log("AFTER:", JSON.stringify(await page.locator("#movelist").innerText()));
  console.log("PIECES:", JSON.stringify({
    e4: await page.locator('[data-sq="e4"] .pc').count(),
    e2: await page.locator('[data-sq="e2"] .pc').count()
  }));
} finally {
  await browser.close();
}
