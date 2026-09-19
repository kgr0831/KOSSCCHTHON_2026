import { expect, test } from "@playwright/test";

test("My page presents points and monthly opportunities without a spending action", async ({ page }) => {
  let rewardRequests = 0;
  await page.route("**/api/v1/**", async route => {
    const request = route.request();
    const path = new URL(request.url()).pathname.replace("/api/v1", "");
    if (path === "/auth/refresh") return route.fulfill({ json: { access_token: "fixture", user_id: "viewer" } });
    if (path === "/me") return route.fulfill({ json: { id: "viewer", profile: { display_name: "Fixture" }, school_affiliations: [], tags: [], preferences: {} } });
    if (path === "/me/rewards") {
      rewardRequests++;
      return route.fulfill({ json: {
        points: 75,
        opportunities: { period: "2026-09", limit: 5, bonus: 2, used: 3, remaining: 4, resets_at: "2026-10-01T00:00:00Z" },
      } });
    }
    return route.fulfill({ json: { items: [], next_cursor: null } });
  });

  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/my");

  const card = page.getByRole("region", { name: "나의 연결 기회" });
  await expect(card).toBeVisible();
  await expect(card.getByText("현재 포인트 75P", { exact: true })).toBeVisible();
  await expect(card.getByText("4 / 5회 (+2 보너스)", { exact: true })).toBeVisible();
  await expect(card.getByText("커피챗 요청 · 팀원 모집 게시 · 프로젝트 참여 지원에 사용돼요.", { exact: true })).toBeVisible();
  await expect(card.getByText(/다음 초기화:.*2026.*10.*1/)).toBeVisible();
  await expect(card.getByRole("button", { name: /포인트|기회/ })).toHaveCount(0);
  await expect.poll(() => rewardRequests).toBe(1);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});
