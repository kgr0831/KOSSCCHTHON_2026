import { test, expect, type Page } from "@playwright/test";

const user = { id: "viewer", profile: { user_id: "viewer", display_name: "김민준", bio: "프로젝트를 만드는 개발자", revision: 1, name_is_public: true, bio_is_public: true, avatar_is_public: false }, school_affiliations: [], tags: [], preferences: { user_id: "viewer", activity_goal: "첫 프로젝트", collaboration_mode: "online", learning_stage: "learning", revision: 1 } };
async function fixtures(page: Page, guest = false) {
  let loggedIn = !guest;
  await page.route("**/api/v1/**", async route => {
    const path = new URL(route.request().url()).pathname.replace("/api/v1", "");
    let result: unknown = { items: [], next_cursor: null };
    if (path === "/auth/refresh") { await route.fulfill({ status: loggedIn ? 200 : 401, json: loggedIn ? { access_token: "fixture-only" } : {} }); return; }
    if (path === "/dev/accounts") result = { items: [{ id: "viewer", name: "김민준", school: "국민대", role: "개발" }] };
    if (path === "/dev/login") { loggedIn = true; result = { access_token: "fixture-only" }; }
    if (path === "/me") result = user;
    if (path === "/me/preferences") result = user.preferences;
    if (path === "/projects") result = { items: [{ id: "p1", title: "작은 아이디어를 함께 완성하는 프로젝트", summary: "내용 ".repeat(60), project_status: "planning", visibility: "private", member_count: 3 }], next_cursor: null };
    if (path === "/recruitment-posts") result = { items: [{ id: "post1", project_id: "p1", project_title: "사람을 연결하는 서비스", description: "함께 만들어요.", role_openings: [{ id: "r1", role: "웹과모바일의반응형사용자경험을개발하는프론트엔드담당자", filled: 0, capacity: 1 }] }], next_cursor: null };
    if (path === "/portfolio-styles") result = { items: [{ id: "linear", name: "Linear", description: "reference", reference_image: "/styles/linear.png", mobile_reference_image: "/styles/linear-mobile.png" }] };
    if (path === "/users/viewer") result = { ...user, display_name: "김민준", bio: "공개 경험", career_events: [] };
    await route.fulfill({ status: 200, json: result });
  });
}

test("internal views preserve address, current location, history, and refresh", async ({ page }) => {
  await fixtures(page);
  await page.goto("/projects");
  await expect(page.getByRole("heading", { name: "함께 만드는 프로젝트" })).toBeVisible();
  const address = page.url();
  const personal = page.getByRole("navigation", { name: "나의 공간", exact: true });
  await expect(personal.getByRole("link", { name: "프로젝트", exact: true })).toHaveAttribute("aria-current", "page");
  await personal.getByRole("link", { name: "AI 스튜디오", exact: true }).click();
  await expect(page.getByRole("heading", { name: "나를 담는 AI 스튜디오" })).toBeVisible();
  expect(page.url()).toBe(address);
  await expect(personal.getByRole("link", { name: "AI 스튜디오" })).toHaveAttribute("aria-current", "page");
  await page.reload();
  await expect(page.getByRole("heading", { name: "나를 담는 AI 스튜디오" })).toBeVisible();
  await page.goBack();
  await expect(page.getByRole("heading", { name: "함께 만드는 프로젝트" })).toBeVisible();
  await page.goForward();
  await expect(page.getByRole("heading", { name: "나를 담는 AI 스튜디오" })).toBeVisible();
});

test("mobile login retains the selected view and all five navigation positions", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await fixtures(page, true);
  await page.goto("/projects");
  const nav = page.getByRole("navigation", { name: "모바일 주요 메뉴" });
  await expect(page.getByRole("link", { name: "학교 이메일로 시작하기" })).toBeVisible();
  const address = page.url(), before = await nav.boundingBox();
  await page.getByRole("link", { name: "학교 이메일로 시작하기" }).click();
  const dialog = page.getByRole("dialog", { name: "로그인 · 회원가입", exact: true });
  await expect(dialog).toBeVisible();
  await dialog.getByRole("button", { name: /김민준/ }).click();
  await expect(dialog).not.toBeVisible();
  await expect(page.getByRole("heading", { name: "함께 만드는 프로젝트" })).toBeVisible();
  expect(page.url()).toBe(address);
  expect(await nav.boundingBox()).toEqual(before);
  await expect(nav.getByRole("link", { name: "마이", exact: true })).toHaveAttribute("aria-current", "page");
  await expect(page.getByLabel("현재 화면")).toContainText("프로젝트");
});

test("direct auth entry opens the login dialog once", async ({ page }) => {
  await fixtures(page, true);
  await page.goto("/auth");
  const dialog = page.getByRole("dialog", { name: "로그인 · 회원가입", exact: true });
  await expect(dialog).toBeVisible();
  await dialog.getByRole("button", { name: /김민준/ }).click();
  await expect(dialog).not.toBeVisible();
  await expect(page.getByRole("heading", { name: "안녕하세요, 김민준님" })).toBeVisible();
});

test("project spacing, long roles, and sidebar controls fit short and narrow screens", async ({ page }, info) => {
  await fixtures(page);
  for (const [width, height] of [[320, 720], [390, 844], [768, 360], [1024, 320], [1440, 900]]) {
    await page.setViewportSize({ width, height });
    await page.goto("/projects");
    await expect(page.getByRole("heading", { name: "사람을 연결하는 서비스" })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    const boxes = await page.locator(".projects-section").evaluateAll(sections => sections.map(section => { const b = section.getBoundingClientRect(); return { top: b.top, bottom: b.bottom }; }));
    expect(boxes[1].top - boxes[0].bottom).toBeGreaterThanOrEqual(24);
    if (width >= 768) {
      expect(await page.locator(".sidebar").evaluate(sidebar => ({ scroll: sidebar.scrollHeight, height: sidebar.clientHeight }))).toEqual({ scroll: height, height });
      for (const item of await page.locator(".sidebar a:visible,.sidebar button:visible").all()) { const box = await item.boundingBox(); expect(box!.y + box!.height).toBeLessThanOrEqual(height); }
    }
    await page.screenshot({ path: info.outputPath(`projects-${width}-${height}.png`), fullPage: true });
  }
});

test("custom unsaved dialog cancels navigation and restores a draft after refresh", async ({ page }) => {
  const native: string[] = [];
  page.on("dialog", dialog => { native.push(dialog.type()); void dialog.dismiss(); });
  await fixtures(page);
  await page.goto("/my");
  await page.getByRole("navigation", { name: "나의 공간", exact: true }).getByRole("link", { name: "프로필 · 공개 범위" }).click();
  await page.getByRole("textbox", { name: "이름", exact: true }).fill("수정한 이름");
  await page.getByRole("navigation", { name: "나의 공간", exact: true }).getByRole("link", { name: "프로젝트", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "저장하지 않은 변경이 있어요" });
  await expect(dialog).toBeVisible();
  await dialog.getByRole("button", { name: "계속 편집" }).click();
  await expect(page.getByRole("textbox", { name: "이름", exact: true })).toHaveValue("수정한 이름");
  await page.goBack();
  await expect(dialog).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("textbox", { name: "이름", exact: true })).toHaveValue("수정한 이름");
  await page.reload();
  await expect(page.getByRole("textbox", { name: "이름", exact: true })).toHaveValue("수정한 이름");
  expect(native).toEqual([]);
});

test("design MD upload becomes a selectable saved style without a broken image", async ({ page }) => {
  await fixtures(page);
  let uploaded = false;
  await page.route("**/api/v1/portfolio-styles", route => route.fulfill({ json: { items: [{ id: "linear", name: "Linear", reference_image: "/styles/linear.png" }, ...(uploaded ? [{ id: "uploaded-test", name: "나의 디자인", status: "queued", reference_image: null }] : [])] } }));
  await page.route("**/api/v1/portfolio-styles/upload", async route => { uploaded = true; await route.fulfill({ status: 202, json: { id: "uploaded-test", name: "나의 디자인", status: "queued", reference_image: null } }); });
  await page.goto("/studio");
  await page.getByLabel("디자인 MD 파일", { exact: true }).setInputFiles({ name: "custom.md", mimeType: "text/markdown", buffer: Buffer.from("# My design\nTeal project cards") });
  await page.getByLabel("디자인 MD를 AI에 전송해 가상 인물의 예시 이미지를 만드는 데 동의합니다.").check();
  await page.getByRole("button", { name: "디자인 저장 · 예시 만들기" }).click();
  await expect(page.locator(".style-card.selected")).toContainText("나의 디자인");
  await expect(page.locator(".style-card.selected img")).toHaveCount(0);
  await expect(page.locator(".style-card.selected")).toContainText("예시 이미지 생성 중");
});
