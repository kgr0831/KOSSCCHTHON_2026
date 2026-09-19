import { chromium } from "@playwright/test";

let html = "";
for await (const chunk of process.stdin) html += chunk;
const browser = await chromium.launch({ channel: "msedge", headless: true }).catch(() => chromium.launch({ headless: true }));
try {
  const context = await browser.newContext({ reducedMotion: "reduce" });
  await context.route("**/*", route => route.abort());
  const page = await context.newPage();
  const images = {};
  for (const [name, width, height] of [["reference_image", 1440, 1050], ["mobile_reference_image", 390, 1000]]) {
    await page.setViewportSize({ width, height });
    await page.setContent('<html><head><meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'; frame-src \'self\';"></head><body style="margin:0"><iframe sandbox="" style="border:0;width:100%;height:100vh" title="Reference"></iframe></body></html>');
    await page.locator("iframe").evaluate((frame, content) => { frame.srcdoc = content; }, html);
    await page.frameLocator("iframe").locator("h1").waitFor({ state: "visible", timeout: 10000 });
    await page.screenshot({ animations: "disabled" }).then(buffer => { images[name] = `data:image/png;base64,${buffer.toString("base64")}`; });
  }
  process.stdout.write(JSON.stringify(images));
} finally { await browser.close(); }
