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
