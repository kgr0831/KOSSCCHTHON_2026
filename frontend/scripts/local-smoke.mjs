import { chromium } from '@playwright/test';
import { mkdir, readFile } from 'node:fs/promises';
import path from 'node:path';

const root = path.resolve(import.meta.dirname, '../..');
const output = path.join(root, '.runtime/screenshots');
await mkdir(output, { recursive: true });
const browser = await chromium.launch({ channel: 'msedge', headless: true });
try {
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
  // No HAR, trace, storageState, headers, or auth response bodies are recorded.
  const page = await context.newPage();
  const errors = [];
  page.on('pageerror', error => errors.push(error.name));
  await page.goto('http://localhost:3000/auth');
  await page.locator('.demo-account').first().click();
  await page.waitForURL('http://localhost:3000/');
  await page.getByRole('heading', { name: /안녕하세요/ }).waitFor();
  for (const width of [390, 1440]) {
    await page.setViewportSize({ width, height: 1000 });
    for (const route of ['/studio', '/career', '/materials', '/projects', '/projects/new', '/settings/ai']) {
      await page.goto(`http://localhost:3000${route}`);
      await page.locator('h1').waitFor();
      await page.waitForTimeout(600);
      if (await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)) throw new Error(`Overflow on ${route} at ${width}`);
      if (await page.locator('.notice.error[role="alert"]').count()) throw new Error(`API/UI error on ${route}`);
      await page.screenshot({ path: path.join(output, `${route.replaceAll('/', '_')}-${width}.png`), fullPage: true, animations: "disabled" });
    }
  }
  const generated = JSON.parse(await readFile(path.join(root, '.runtime/live-generation.json'), 'utf8'));
  await page.goto(`http://localhost:3000/studio?kind=portfolio&version=${generated.version_id}`);
  await page.getByTitle('저장된 문서 미리보기').waitFor({ timeout: 10000 });
  await page.frameLocator('iframe[title="저장된 문서 미리보기"]').locator('h1').waitFor({ timeout: 10000 });
  const portfolio = page.frameLocator('iframe[title="저장된 문서 미리보기"]');
  if (await portfolio.locator('details').count()) {
    await portfolio.locator('details summary').first().click();
    if (!await portfolio.locator('details').first().evaluate(node => node.open)) throw new Error('Portfolio project disclosure failed');
  }
  await page.screenshot({ path: path.join(output, 'live-generated-portfolio.png'), fullPage: true, animations: "disabled" });
  await page.goto('http://localhost:3000/studio?kind=cv');
  await page.locator('.history-item').first().click();
  await page.frameLocator('iframe[title="저장된 문서 미리보기"]').locator('h1').waitFor({ timeout: 10000 });
  await page.frameLocator('iframe[title="저장된 문서 미리보기"]').locator('body').evaluate(async body => {
    await Promise.all(body.ownerDocument.getAnimations().filter(animation => Number.isFinite(Number(animation.effect?.getComputedTiming().endTime))).map(animation => animation.finished.catch(() => {})));
  });
  await page.screenshot({ path: path.join(output, 'live-generated-cv.png'), fullPage: true, animations: "disabled" });
  if (errors.length) throw new Error(`Browser exceptions: ${errors.join(',')}`);
  console.log('Live demo login, 6 screens at mobile/desktop, API data, saved generated preview: PASS');
} finally { await browser.close(); }
