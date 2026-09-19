import { test, expect, type Page } from "@playwright/test";

// Explicit browser fixtures; these records are never loaded by the application
// or persisted to its database.
const profile = { user_id: "viewer", display_name: "김민준", bio: "작은 프로젝트를 함께 만들며 배우고 있어요.", avatar_url: null, name_is_public: true, bio_is_public: true, avatar_is_public: false, revision: 1 };
const preferences = { coffee_chat_available: true, project_available: true, learning_stage: "learning", activity_goal: "첫 프로젝트 완성", hours_per_week: 6, collaboration_mode: "online", is_public: true, revision: 1 };
const user = { id: "viewer", login_email: "fixture@example.test", profile, preferences, school_affiliations: [{ id: "school-1", university_id: "u1", university_name: "국민대학교", department: "소프트웨어학부", enrollment_status: "student" }], tags: [{ id: "tag1", tag_id: "skill1", name: "백엔드", usage: "interested", is_public: true }] };
const appointment = { id: "b1", request_id: "c1", starts_at: "2026-09-20T14:30:00Z", ends_at: "2026-09-20T15:30:00Z", meeting_mode: "online", meeting_location: "자정을 넘기는 커피챗", status: "confirmed", revision: 1 };
const later = { ...appointment, id: "b2", request_id: "c2", starts_at: "2026-09-23T10:00:00Z", ends_at: "2026-09-23T11:00:00Z", meeting_location: "다음 페이지의 약속" };
const past = { ...appointment, id: "b3", starts_at: "2026-09-18T10:00:00Z", ends_at: "2026-09-18T11:00:00Z", meeting_location: "지난 대화" };
const request = { id: "c1", requester_id: "other", recipient_id: "viewer", purpose: "첫 백엔드 프로젝트가 궁금해요", introduction: "서버 개발을 배우고 있어요.", questions: "처음 프로젝트에서 어떤 역할을 맡으셨나요?", revision: 1, status: "pending", booking_id: null, proposed_slots: [{ id: "slot1", starts_at: appointment.starts_at, ends_at: appointment.ends_at }] };
const empty = { items: [], next_cursor: null };

async function fixtures(page: Page) {
  await page.clock.setFixedTime(new Date("2026-09-19T03:00:00Z"));
  await page.route("**/api/v1/**", async route => {
    const url = new URL(route.request().url());
    const path = url.pathname.replace("/api/v1", "");
    let result: unknown = empty;
    if (path === "/auth/refresh") result = { access_token: "browser-fixture-only" };
    else if (path === "/me") result = user;
    else if (path === "/me/bookings") result = url.searchParams.has("cursor") ? { items: [later, past], next_cursor: null } : { items: [appointment], next_cursor: "fixture-page-two" };
    else if (path === "/me/preferences") result = preferences;
    else if (path === "/me/tags") result = { items: user.tags, revision: 1 };
    else if (path === "/search/filters") result = { universities: [{ id: "u1", name: "국민대학교" }, { id: "u2", name: "숭실대학교" }], tags: [{ id: "skill1", name: "백엔드", kind: "skill" }, { id: "role1", name: "기획", kind: "role" }, { id: "interest1", name: "게임", kind: "interest" }] };
    else if (path === "/search/interpret") result = { purpose: "team_building", match_direction: "complementary", filters: { university_ids: ["u1", "u2"], role_tag_ids: ["role1"], interest_tag_ids: ["interest1"], activity_goal: "함께 게임 만들기", collaboration_mode: "online", coffee_chat_available: false } };
    else if (path === "/search/users") result = { items: [{ user: { ...user, id: "other", display_name: "김서준", bio: "서버를 만들고, 배운 것을 나누고 있어요.", verifications: [], career_events: [], project_members: [] }, reason: "선택한 탐색 조건에 맞는 동문입니다." }], next_cursor: null };
    else if (path === "/coffee-chats") result = { items: [request], next_cursor: null };
    else if (path === "/coffee-chats/c1") result = request;
    else if (path === "/bookings/b1") result = { ...appointment, requester_id: "viewer", recipient_id: "other", changes: [{ id: "change1", proposer_id: "other", change_kind: "reschedule", status: "pending", proposed_value: { slot: { starts_at: "2026-09-22T10:00:00Z", ends_at: "2026-09-22T11:00:00Z" }, meeting_location: "변경된 도서관" } }] };
    await route.fulfill({ status: 200, json: result });
  });
}

for (const width of [320, 390, 768, 1024, 1440]) {
  test(`responsive navigation and cards at ${width}px`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: 1000 });
    await fixtures(page);
    await page.goto("/");
    await expect(page.getByRole("heading", { name: "안녕하세요, 김민준님" })).toBeVisible();
    await expect(page.getByRole("region", { name: "커피챗 캘린더" })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    const nav = page.getByRole("navigation", { name: width < 768 ? "모바일 주요 메뉴" : "주요 메뉴", exact: true });
    await expect(nav).toBeVisible();
    await expect(nav.getByRole("link", { name: "홈", exact: true })).toHaveAttribute("aria-current", "page");
    await page.screenshot({ path: testInfo.outputPath(`home-${width}.png`), fullPage: true });
    await page.getByRole("button", { name: width < 768 ? "등록" : "등록하기", exact: true }).click();
    const dialog = page.getByRole("dialog", { name: "무엇을 시작할까요?" });
    await expect(dialog).toBeVisible();
    await expect(dialog.getByRole("button", { name: "등록 메뉴 닫기" })).toBeFocused();
    await page.screenshot({ path: testInfo.outputPath(`registration-${width}.png`), fullPage: true });
    await page.keyboard.press("Escape");
    await expect(dialog).not.toBeVisible();
    await expect(page.getByRole("button", { name: width < 768 ? "등록" : "등록하기", exact: true })).toBeFocused();
    await nav.getByRole("link", { name: "마이", exact: true }).click();
    await expect(page.getByRole("heading", { name: "마이", exact: true })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    await page.screenshot({ path: testInfo.outputPath(`my-${width}.png`), fullPage: true });
  });
}

test("calendar loads all pages, groups midnight locally, and switches views", async ({ page }) => {
  await fixtures(page);
  await page.goto("/coffee");
  const upcoming = page.locator(".coffee-upcoming");
  await expect(upcoming).toBeVisible();
  await expect(upcoming.locator(".coffee-upcoming-card")).toHaveCount(2);
  expect((await upcoming.boundingBox())!.y).toBeLessThan((await page.locator(".coffee-tabs").boundingBox())!.y);
  const calendar = page.getByRole("region", { name: "커피챗 캘린더" });
  await calendar.getByRole("button", { name: "9월 21일 월요일, 일정 1개", exact: true }).click();
  await expect(calendar.locator(".calendar-selected")).toContainText("자정을 넘기는 커피챗");
  await expect(calendar.locator(".agenda-time")).toContainText("9/20 23:30–9/21 00:30");
  await calendar.getByRole("button", { name: "9월 23일 수요일, 일정 1개", exact: true }).click();
  await expect(calendar.locator(".calendar-selected")).toContainText("다음 페이지의 약속");
  await calendar.getByRole("button", { name: "주", exact: true }).click();
  await expect(calendar.locator(".week-agenda")).toContainText("다음 페이지의 약속");
  await calendar.getByRole("button", { name: "다음 주" }).click();
  await expect(calendar.locator(".calendar-selected")).toContainText("9월 30일");
  await calendar.getByRole("button", { name: "월", exact: true }).click();
  await calendar.getByRole("button", { name: "다음 달" }).click();
  await expect(calendar.locator(".calendar-toolbar")).toContainText("2026년 10월");
  await page.getByRole("button", { name: "지난 약속", exact: true }).click();
  await expect(page.locator(".coffee-main")).toContainText("지난 대화");
  await page.clock.setFixedTime(new Date("2026-09-20T15:01:00Z"));
  await page.evaluate(() => document.dispatchEvent(new Event("visibilitychange")));
  await calendar.getByRole("button", { name: "오늘", exact: true }).click();
  await expect(calendar.locator(".calendar-selected")).toContainText("9월 21일");
});

test("upcoming coffee chats stay above requests and the calendar at desktop and mobile widths", async ({ page }) => {
  await fixtures(page);
  for (const width of [390, 1440]) {
    await page.setViewportSize({ width, height: 900 });
    await page.goto("/coffee");
    const upcoming = page.locator(".coffee-upcoming");
    await expect(upcoming).toBeVisible();
    expect((await upcoming.boundingBox())!.y).toBeLessThan((await page.locator(".coffee-tabs").boundingBox())!.y);
    await expect(page.getByRole("region", { name: "커피챗 캘린더" })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  }
});

test("empty upcoming coffee state stays compact", async ({ page }) => {
  await fixtures(page);
  await page.route("**/api/v1/me/bookings**", route => route.fulfill({ json: empty }));
  for (const width of [390, 1440]) {
    await page.setViewportSize({ width, height: 900 });
    await page.goto("/coffee");
    const compact = page.locator(".coffee-upcoming-empty");
    await expect(compact).toBeVisible();
    await expect(page.locator(".coffee-upcoming .empty")).toHaveCount(0);
    expect((await compact.boundingBox())!.height).toBeLessThan(180);
  }
});

test("interpreted conditions are visible and editable before search", async ({ page }, testInfo) => {
  await fixtures(page);
  await page.goto("/explore");
  await page.getByRole("textbox", { name: "찾고 싶은 동문" }).fill("게임을 함께 만들 동료");
  const interpret = page.getByRole("button", { name: "AI로 조건 정리" });
  await expect(interpret).toHaveAttribute("type", "button");
  await interpret.click();
  await expect(page.locator("#ai-condition-status")).toHaveAttribute("role", "status");
  await expect(page.locator("#ai-condition-status")).toContainText("AI가 조건을 정리했어요");
  await expect(page.getByLabel("국민대학교", { exact: true })).toBeChecked();
  await expect(page.getByLabel("숭실대학교", { exact: true })).toBeChecked();
  await expect(page.getByLabel("기획", { exact: true })).toBeChecked();
  await expect(page.getByLabel("게임", { exact: true })).toBeChecked();
  await expect(page.getByLabel("활동 목표", { exact: true })).toHaveValue("함께 게임 만들기");
  await page.getByLabel("기획", { exact: true }).uncheck();
  const sent = page.waitForRequest(r => r.url().endsWith("/search/users"));
  await page.getByRole("button", { name: "동문 찾기", exact: true }).click();
  expect((await sent).postDataJSON().filters.role_tag_ids).toEqual([]);
  await expect(page.getByRole("heading", { name: "김서준" })).toBeVisible();
  await page.getByRole("button", { name: "상세 조건", exact: true }).click();
  await page.screenshot({ path: testInfo.outputPath("explore-desktop.png"), fullPage: true });
});

test("AI condition failures are announced without hiding editable filters", async ({ page }) => {
  await fixtures(page);
  await page.route("**/api/v1/search/interpret", route => route.fulfill({ status: 422, json: { detail: "조건을 해석할 수 없어요." } }));
  await page.goto("/explore");
  await page.getByRole("textbox", { name: "찾고 싶은 동문" }).fill("모호한 조건");
  await page.getByRole("button", { name: "AI로 조건 정리" }).click();
  const status = page.locator("#ai-condition-status");
  await expect(status).toHaveAttribute("role", "alert");
  await expect(status).toContainText("AI 조건 정리에 실패했어요");
  await expect(page.getByRole("button", { name: "AI로 조건 정리" })).toBeEnabled();
});

test("AI condition pending work is announced before editable filters are applied", async ({ page }) => {
  await fixtures(page);
  let finish!: () => void;
  const response = new Promise<void>(resolve => { finish = resolve; });
  await page.route("**/api/v1/search/interpret", async route => {
    await response;
    await route.fulfill({ json: { purpose: "coffee_chat", match_direction: "similar", filters: { university_ids: [], coffee_chat_available: true } } });
  });
  await page.goto("/explore");
  await page.getByRole("textbox", { name: "찾고 싶은 동문" }).fill("백엔드 동료");
  await page.getByRole("button", { name: "AI로 조건 정리" }).click();
  await expect(page.locator("#ai-condition-status")).toContainText("AI가 입력한 문장을 검색 조건으로 정리하고 있어요");
  finish();
  await expect(page.locator("#ai-condition-status")).toContainText("AI가 조건을 정리했어요");
});

test("booking shows proposed changes and validates reschedule input", async ({ page }) => {
  await fixtures(page);
  await page.goto("/bookings/b1");
  await expect(page.getByText("새 장소: 변경된 도서관")).toBeVisible();
  await expect(page.getByText(/새 일정:.*2026/)).toBeVisible();
  await page.getByRole("button", { name: "변경 제안 보내기" }).click();
  expect(await page.getByLabel("새 시작 시각").evaluate((input: HTMLInputElement) => input.validity.valueMissing)).toBe(true);
  const validation = page.getByRole("dialog", { name: "입력 내용을 확인해 주세요" });
  await expect(validation).toBeVisible();
  await validation.getByRole("button", { name: "확인", exact: true }).click();
  await page.getByLabel("새 시작 시각").fill("2026-09-24T20:00");
  await page.getByLabel("새 종료 시각").fill("2026-09-24T19:00");
  await page.getByRole("button", { name: "변경 제안 보내기" }).click();
  await expect(page.getByRole("main").getByRole("alert")).toContainText("종료 시각은 시작 시각 이후");
  await page.getByLabel("변경 종류").selectOption("cancel");
  await expect(page.getByLabel("새 시작 시각")).toHaveCount(0);
});

test("forms and detail cards fit narrow and wide screens with reduced motion", async ({ page }, testInfo) => {
  const errors: string[] = [];
  page.on("pageerror", error => errors.push(error.message));
  await fixtures(page);
  await page.emulateMedia({ reducedMotion: "reduce" });
  for (const width of [320, 1440]) {
    await page.setViewportSize({ width, height: 900 });
    for (const path of ["/explore", "/profile", "/coffee", "/coffee/c1", "/bookings/b1"]) {
      await page.goto(path);
      await expect(page.getByRole("main").getByRole("heading", { level: 1 })).toBeVisible();
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), path).toBe(true);
      if (path === "/coffee" || path === "/profile") await page.screenshot({ path: testInfo.outputPath(`${path.slice(1)}-${width}.png`), fullPage: true });
    }
    const activeIcon = page.locator(width < 768 ? ".bottom-nav .active .nav-icon" : ".sidebar .active .nav-icon");
    await expect(activeIcon).toHaveCSS("animation-name", "none");
  }
  expect(errors).toEqual([]);
});
