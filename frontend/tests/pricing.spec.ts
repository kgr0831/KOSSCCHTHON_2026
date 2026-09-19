import { expect, test } from "@playwright/test";

test("a member can choose an AI plan without a payment flow", async ({ page }) => {
  let plan: "free" | "premium" = "free";
  let saved: unknown;
  const requests: string[] = [];
  await page.route("**/api/v1/**", async route => {
    const request = route.request();
    const path = new URL(request.url()).pathname.replace("/api/v1", "");
    requests.push(path);
    if (path === "/auth/refresh") return route.fulfill({ json: { access_token: "fixture", user_id: "viewer" } });
    if (path === "/me") return route.fulfill({ json: { id: "viewer", profile: { display_name: "Fixture" }, school_affiliations: [], tags: [], preferences: {} } });
    if (path === "/me/subscription") {
      if (request.method() === "PUT") {
        saved = request.postDataJSON();
        plan = (saved as { plan: typeof plan }).plan;
      }
      return route.fulfill({ json: { plan } });
    }
    return route.fulfill({ json: { items: [], next_cursor: null } });
  });

  await page.goto("/pricing");
  await expect(page.getByRole("heading", { name: "요금제와 AI 생성 범위" })).toBeVisible();
  await expect(page.getByText("결제 처리 없음", { exact: true })).toBeVisible();
  await expect(page.getByRole("article", { name: /Free 플랜, 현재 이용 중/ })).toBeVisible();
  await expect(page.getByText("커피챗 요청·모집 게시·참여 지원 월 5회", { exact: true })).toBeVisible();
  await expect(page.getByText("커피챗 요청·모집 게시·참여 지원 월 20회", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Premium 선택" }).click();
  await expect.poll(() => saved).toEqual({ plan: "premium" });
  await expect(page.getByRole("article", { name: /Premium 플랜, 현재 이용 중/ })).toBeVisible();
  expect(requests.some(path => /payment|checkout|charge/i.test(path))).toBe(false);

  await page.goto("/my");
  await expect(page.getByRole("link", { name: "요금제 · AI 생성 범위" })).toBeVisible();
});
