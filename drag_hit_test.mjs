import { chromium } from "playwright";
const browser = await chromium.launch();
try {
  const page = await browser.newPage();
  await page.goto("http://localhost:8787", {waitUntil:"networkidle"});
  await page.waitForFunction(() => document.getElementById("engineStatus")?.textContent === "ready", null, {timeout:60000});
  console.log(JSON.stringify(await page.evaluate(() => {
    const sq = document.querySelector('[data-sq="e2"]');
    const pc = sq?.querySelector(".pc");
    const r = (pc || sq)?.getBoundingClientRect();
    const hit = r && document.elementFromPoint(r.x + r.width/2, r.y + r.height/2);
    return {
      squareHTML: sq?.outerHTML,
      pieceHTML: pc?.outerHTML,
      pieceStyle: pc && {pointerEvents:getComputedStyle(pc).pointerEvents, touchAction:getComputedStyle(pc).touchAction, cursor:getComputedStyle(pc).cursor},
      squareStyle: sq && {pointerEvents:getComputedStyle(sq).pointerEvents, cursor:getComputedStyle(sq).cursor},
      pieceRect: r && {x:r.x,y:r.y,width:r.width,height:r.height},
      hitTag: hit?.tagName,
      hitClass: hit?.className?.baseVal ?? hit?.className,
      hitHTML: hit?.outerHTML?.slice(0,400),
      dragListeners: typeof window.onpointerdown,
      boardPointerEvents: getComputedStyle(document.getElementById("board")).pointerEvents
    };
  }),null,2));
} finally { await browser.close(); }
