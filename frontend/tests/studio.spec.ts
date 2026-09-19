import { test, expect, type Page } from "@playwright/test";

const person = { id: "viewer", profile: { display_name: "김민준", bio: "프로젝트를 만드는 개발자", revision: 1 }, school_affiliations: [], tags: [], preferences: { activity_goal: "첫 프로젝트" } };
const fixtureDocument = { title: "My Portfolio", headline: "Hello", summary: "My real experience", sections: [{ id: "work", heading: "Experience", body: "A project", items: [] }], accent: "#7060d9", font: "sans-serif", spacing: 24 };
const code = { html: '<h1 data-field="title">My Portfolio</h1><section data-section="work"><p data-field="body">A project</p></section>', css: "body{color:black}", javascript: "" };
const version = { id: "v1", site_id: "s1", version_number: 1, style_id: "linear", status: "preview_ready", instruction: "", gui: fixtureDocument, code, site_revision: 1, facts_current: true, validation: { model: "fixture-model" }, created_at: "2026-09-19T03:00:00Z", preview_html: "<h1>Saved document</h1>" };

async function fixtures(page: Page) {
  await page.route("**/api/v1/**", async route => {
    const path = new URL(route.request().url()).pathname.replace("/api/v1", "");
    let result: unknown = { items: [], next_cursor: null };
    if (path === "/auth/refresh") result = { access_token: "fixture-only" };
    else if (path === "/me") result = person;
    else if (path === "/portfolio-styles") result = { items: ["linear", "notion", "spotify"].map(id => ({ id, name: id, description: `${id} reference`, reference_image: `/styles/${id}.png`, mobile_reference_image: `/styles/${id}-mobile.png` })) };
    else if (path === "/users/viewer") result = { ...person, display_name: "김민준", bio: "Public facts", career_events: [] };
    else if (path === "/me/sites") result = { items: [{ id: "s1", site_kind: "portfolio", revision: 1, versions: [version] }] };
    else if (path === "/me/site-versions/v1") result = version;
    await route.fulfill({ status: 200, json: result });
  });
}

for (const width of [390, 1440]) {
  test(`style references and saved editor at ${width}`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: 1000 });
    await fixtures(page);
    await page.goto("/studio");
    await expect(page.getByRole("heading", { name: "나를 담는 AI 스튜디오" })).toBeVisible();
    await expect(page.locator(".style-card")).toHaveCount(3);
    for (const image of await page.locator(".style-card img").all()) expect(await image.evaluate((img: HTMLImageElement) => img.complete && img.naturalWidth > 0)).toBe(true);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({ path: testInfo.outputPath(`studio-${width}.png`), fullPage: true });
    await page.getByRole("button", { name: /PC · 모바일 예시 크게 보기/ }).first().click();
    await expect(page.getByRole("dialog")).toBeVisible();
    await expect.poll(async () => {
      const box = await page.getByRole("dialog").boundingBox();
      const center = await page.evaluate(() => ({ x: innerWidth / 2, y: innerHeight / 2 }));
      return Math.abs(box!.x + box!.width / 2 - center.x) + Math.abs(box!.y + box!.height / 2 - center.y);
    }).toBeLessThan(3);
    await page.keyboard.press("Escape");
    await page.getByRole("button", { name: /버전 1/ }).click();
    await expect(page.getByTitle("저장된 문서 미리보기")).toHaveAttribute("sandbox", "allow-scripts");
    await page.getByRole("button", { name: "내용·디자인" }).click();
    await page.getByRole("textbox", { name: "문서 제목", exact: true }).fill("Changed draft");
    await expect(page.getByRole("button", { name: "이 버전 게시", exact: true })).toBeDisabled();
    await expect(page.getByText("저장하지 않은 변경이 있어요.", { exact: false })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({ path: testInfo.outputPath(`studio-editor-${width}.png`), fullPage: true });
  });
}

for (const width of [390, 1440]) {
  test(`custom style dialog saves selected options at ${width}`, async ({ page }) => {
    await page.setViewportSize({ width, height: 1000 });
    await fixtures(page);
    let uploaded = "";
    const created = { id: "uploaded-fixture-style", name: "나의 작업 갤러리", status: "queued", description: "custom" };
    await page.route("**/api/v1/portfolio-styles/upload", async route => {
      uploaded = route.request().postData() || "";
      await route.fulfill({ status: 202, json: created });
    });
    await page.goto("/studio");
    await page.getByRole("button", { name: /원하는 스타일 만들기/ }).click();
    const dialog = page.getByRole("dialog", { name: "나만의 디자인 스타일" });
    await expect(dialog).toBeVisible();
    await expect.poll(async () => { const box = await dialog.boundingBox(); const center = await page.evaluate(() => ({ x: innerWidth / 2, y: innerHeight / 2 })); return Math.abs(box!.x + box!.width / 2 - center.x) + Math.abs(box!.y + box!.height / 2 - center.y); }).toBeLessThan(3);
    await dialog.getByRole("button", { name: "취소", exact: true }).click();
    expect(uploaded).toBe("");
    await page.getByRole("button", { name: /원하는 스타일 만들기/ }).click();
    await dialog.getByLabel("스타일 이름").fill("나의 작업 갤러리");
    await dialog.getByLabel("분위기", { exact: true }).selectOption("대담하고 창의적인");
    await dialog.getByLabel("추가로 원하는 점", { exact: false }).fill("대표 작업 세 개를 강조해 주세요.");
    await dialog.getByRole("checkbox").check();
    await page.route("**/api/v1/portfolio-styles", route => route.fulfill({ json: { items: [created] } }));
    await dialog.getByRole("button", { name: "스타일 저장 · 예시 만들기" }).click();
    await expect(dialog).not.toBeVisible();
    await expect(page.locator(".style-card.selected")).toContainText("나의 작업 갤러리");
    expect(uploaded).toContain("대담하고 창의적인");
    expect(uploaded).toContain("대표 작업 세 개를 강조해 주세요.");
    expect(uploaded).toContain("#faf8ff");
  });
}

test("backend outage is visible and session reconnect recovers", async ({ page }) => {
  await fixtures(page);
  let online = false;
  await page.route("**/api/v1/auth/refresh", route => online
    ? route.fulfill({ json: { access_token: "fixture-only" } })
    : route.fulfill({ status: 502, contentType: "text/plain", body: "Bad gateway" }));
  await page.goto("/");
  await expect(page.getByRole("alert").filter({ hasText: "백엔드 서버에 연결하지 못했어요" })).toBeVisible();
  online = true;
  await page.getByRole("button", { name: "다시 연결", exact: true }).click();
  await expect(page.getByRole("heading", { name: "안녕하세요, 김민준님" })).toBeVisible();
  await expect(page.getByRole("button", { name: "다시 연결", exact: true })).toHaveCount(0);
});

test("generated script cannot navigate its preview to an external URL", async ({ page }) => {
  await fixtures(page);
  await page.goto("/studio?kind=portfolio&version=v1");
  let attempts = 0;
  let navigationBlocked = false;
  page.on("console", message => { if (message.text().includes("frame-src") && message.text().includes("example.invalid")) navigationBlocked = true; });
  await page.route("https://example.invalid/**", route => { attempts++; return route.abort(); });
  await page.evaluate(() => { window.addEventListener("message", event => {
    if (event.data === "fixture-script-executed") document.documentElement.dataset.childExecuted = "yes";
  }); });
  // The app response owns frame-src. Sandboxed script can run locally but its
  // attempts to move the frame out of the allowed origins must be blocked.
  await page.getByTitle("저장된 문서 미리보기").evaluate((element: HTMLIFrameElement) => {
    element.srcdoc = '<body>Public document<script>parent.postMessage("fixture-script-executed","*");location.href="https://example.invalid/?content=fixture";</script></body>';
  });
  await expect(page.locator("html")).toHaveAttribute("data-child-executed", "yes");
  await expect.poll(() => navigationBlocked).toBe(true);
  expect(attempts).toBe(0);
});
