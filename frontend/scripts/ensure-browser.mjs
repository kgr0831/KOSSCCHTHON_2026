import { chromium } from "@playwright/test";
import { spawnSync } from "node:child_process";
import { createRequire } from "node:module";
import { dirname, join } from "node:path";
const require = createRequire(import.meta.url);
let available = false;
for (const options of [{ channel: "msedge", headless: true }, { headless: true }]) {
  try { const browser = await chromium.launch(options); await browser.close(); available = true; break; } catch {}
}
if (!available) {
  console.log("[setup] Installing the browser used for design reference images...");
  const result = spawnSync(process.execPath, [join(dirname(require.resolve("playwright/package.json")), "cli.js"), "install", "chromium", "--only-shell"], { stdio: "inherit" });
  if (result.status !== 0) process.exit(1);
  try { const browser = await chromium.launch({ headless: true }); await browser.close(); }
  catch { console.error("[setup] The reference browser could not start. Retry browser installation."); process.exit(1); }
}
