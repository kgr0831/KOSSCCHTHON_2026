import { chromium } from '@playwright/test';
import { mkdir, readdir } from 'node:fs/promises';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

const root = path.resolve(import.meta.dirname, '../..');
const input = path.join(root, '.runtime/style-previews');
const output = path.join(root, 'frontend/public/styles');
await mkdir(output, { recursive: true });
const browser = await chromium.launch({ channel: 'msedge', headless: true });
try {
  for (const name of await readdir(input)) {
    if (!name.endsWith('.html')) continue;
    for (const mobile of [false, true]) {
      const page = await browser.newPage({ viewport: { width: mobile ? 390 : 1440, height: 1000 }, deviceScaleFactor: 1 });
      await page.goto(pathToFileURL(path.join(input, name)).href);
      await page.evaluate(() => document.fonts.ready);
      await page.screenshot({ path: path.join(output, name.replace('.html', mobile ? '-mobile.png' : '.png')), fullPage: true });
      await page.close();
    }
  }
} finally { await browser.close(); }
console.log('Saved desktop and mobile reference images.');
