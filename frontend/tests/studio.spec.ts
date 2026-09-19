import { test, expect, type Page } from "@playwright/test";

const person = { id: "viewer", profile: { display_name: "김민준", bio: "프로젝트를 만드는 개발자", revision: 1 }, school_affiliations: [], tags: [], preferences: { activity_goal: "첫 프로젝트" } };
const fixtureDocument = { title: "My Portfolio", headline: "Hello", summary: "My real experience", sections: [{ id: "work", heading: "Experience", body: "A project", items: [] }], accent: "#7060d9", font: "sans-serif", spacing: 24 };
const code = { html: '<h1 data-field="title">My Portfolio</h1><section data-section="work"><p data-field="body">A project</p></section>', css: "body{color:black}", javascript: "" };
const version = { id: "v1", site_id: "s1", version_number: 1, style_id: "linear", status: "preview_ready", instruction: "", gui: fixtureDocument, code, site_revision: 1, facts_current: true, validation: { model: "fixture-model" }, created_at: "2026-09-19T03:00:00Z", preview_html: "<h1>Saved document</h1>" };

async function fixtures(page: Page, plan: "free" | "premium" = "premium", codexImages = true) {
  const references: { id: string; site_kind: string; display_name: string; reference_format: "pdf" | "png" | "jpg" | "txt" | "html" | "docx"; content_type: string; byte_size: number; revision: number; created_at: string }[] = [];
  let generation: unknown;
  await page.route("**/api/v1/**", async route => {
    const request = route.request();
    const path = new URL(request.url()).pathname.replace("/api/v1", "");
    let result: unknown = { items: [], next_cursor: null };
    if (path === "/auth/refresh") result = { access_token: "fixture-only" };
    else if (path === "/me") result = person;
    else if (path === "/me/subscription") result = { plan };
    else if (path === "/me/ai-settings") result = codexImages ? { transport: "cli", cli_provider: "codex", cli_connections: [{ provider: "codex", current_pc: true, status: "connected" }] } : { transport: "api", cli_provider: "codex", cli_connections: [] };
    else if (path === "/portfolio-styles") result = { items: ["linear", "notion", "spotify"].map(id => ({ id, name: id, description: `${id} reference`, reference_image: `/styles/${id}.png`, mobile_reference_image: `/styles/${id}-mobile.png` })) };
    else if (path === "/users/viewer") result = { ...person, display_name: "김민준", bio: "Public facts", career_events: [] };
    else if (path === "/me/sites") result = { items: [{ id: "s1", site_kind: "portfolio", revision: 1, versions: [version] }] };
    else if (path === "/me/site-versions/v1") result = version;
    else if (path === "/me/site-versions/generated") result = { ...version, id: "generated", status: "queued" };
    else if (path.startsWith("/me/document-references")) {
      if (request.method() === "POST") {
        const content = request.postDataBuffer() || Buffer.alloc(0);
        const name = content.toString().includes("resume.txt") ? "resume.txt" : "reference.txt";
        const item = { id: `reference-${references.length + 1}`, site_kind: path.split("/").pop() || "portfolio", display_name: name, reference_format: "txt" as const, content_type: "text/plain", byte_size: content.length, revision: 1, created_at: "2026-09-20T00:00:00Z" };
        references.push(item); result = item;
      } else if (request.method() === "DELETE") {
        const id = path.split("/").pop();
        const index = references.findIndex(item => item.id === id);
        if (index >= 0) references.splice(index, 1);
        await route.fulfill({ status: 204 }); return;
      } else result = { items: references };
    } else if (path === "/me/sites/portfolio/versions" && request.method() === "POST") {
      generation = request.postDataJSON(); result = { ...version, id: "generated", status: "queued" };
    }
    await route.fulfill({ status: 200, json: result });
  });
  return { references, generation: () => generation };
}

test("UI text and images do not drag while code and introductions stay selectable", async ({ page }) => {
  await fixtures(page);
  await page.goto("/studio");
  const heading = page.getByRole("heading", { name: "나를 담는 AI 스튜디오" });
  await expect(heading).toBeVisible();
  expect(await heading.evaluate(el => getComputedStyle(el).userSelect)).toBe("none");
  const headingBox = (await heading.boundingBox())!;
  await page.mouse.move(headingBox.x + 2, headingBox.y + headingBox.height / 2);
  await page.mouse.down();
  await page.mouse.move(headingBox.x + headingBox.width - 2, headingBox.y + headingBox.height / 2, { steps: 8 });
  await page.mouse.up();
  expect(await page.evaluate(() => window.getSelection()?.toString())).toBe("");
  const image = page.locator(".style-card img").first();
  expect(await image.evaluate(el => !el.dispatchEvent(new DragEvent("dragstart", { bubbles: true, cancelable: true })))).toBe(true);
  await page.getByText("AI에 전달할 공개 프로필 확인", { exact: true }).click();
  const bio = page.getByText("Public facts", { exact: true });
  await bio.scrollIntoViewIfNeeded();
  expect(await bio.evaluate(el => getComputedStyle(el).userSelect)).toBe("text");
  const bioBox = (await bio.boundingBox())!;
  await page.mouse.move(bioBox.x + 1, bioBox.y + bioBox.height / 2);
  await page.mouse.down();
  await page.mouse.move(bioBox.x + bioBox.width - 1, bioBox.y + bioBox.height / 2, { steps: 8 });
  await page.mouse.up();
  expect(await page.evaluate(() => window.getSelection()?.toString())).toContain("Public facts");
  expect(await page.evaluate(() => window.scrollY)).toBeGreaterThan(0);
  await page.getByRole("button", { name: /버전 1/ }).click();
  await page.getByRole("button", { name: "코드", exact: true }).click();
  const editor = page.getByRole("textbox", { name: "HTML 편집" });
  await editor.click();
  await editor.press("ControlOrMeta+A");
  expect(await editor.evaluate((el: HTMLTextAreaElement) => el.selectionEnd - el.selectionStart)).toBe(code.html.length);
});

test("Premium members select a private reference file for one Studio generation", async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 900 });
  const fixture = await fixtures(page);
  await page.goto("/studio");
  const picker = page.getByRole("heading", { name: "생성 메모리 · 참고 파일" }).locator("..").locator("..");
  await expect(picker).toBeVisible();
  await page.getByLabel("문서 참고 파일").setInputFiles({ name: "resume.txt", mimeType: "text/plain", buffer: Buffer.from("I built the API.") });
  const reference = page.getByRole("checkbox", { name: "resume.txt 참고에 사용" });
  await expect(reference).toBeVisible();
  await reference.check();
  await page.getByRole("checkbox", { name: /공개 프로필.*작성 요청/ }).check();
  await page.getByRole("button", { name: "AI로 포트폴리오 만들기" }).click();
  await expect.poll(() => fixture.generation()).toMatchObject({ reference_ids: ["reference-1"] });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

test("Free members cannot upload or generate with reference files", async ({ page }) => {
  await fixtures(page, "free");
  await page.goto("/studio");
  await expect(page.getByText("Premium 전용 AI 생성", { exact: true })).toBeVisible();
  await expect(page.getByLabel("문서 참고 파일")).toHaveCount(0);
  await expect(page.getByText("저장한 참고 파일은 삭제할 수 있어요.", { exact: false })).toBeVisible();
  await expect(page.getByRole("button", { name: "AI로 포트폴리오 만들기" })).toBeDisabled();
});

test("image references are unavailable until this PC has a Codex CLI connection", async ({ page }) => {
  await fixtures(page, "premium", false);
  await page.goto("/studio");
  const input = page.getByLabel("문서 참고 파일");
  await expect(input).toBeVisible();
  await expect(input).not.toHaveAttribute("accept", /\.png/);
  await expect(page.getByText("PNG/JPG를 참고하려면 AI 연결 설정에서 이 PC의 Codex CLI를 연결한 뒤", { exact: false })).toBeVisible();
});

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
