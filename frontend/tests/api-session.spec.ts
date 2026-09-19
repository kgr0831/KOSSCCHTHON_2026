import { test, expect } from "@playwright/test";
import { api, setAccessToken } from "../src/lib/api";

const originalFetch = globalThis.fetch;
test.afterEach(() => { globalThis.fetch = originalFetch; setAccessToken(null); });

function deferredResponse() {
  let resolve!: (response: Response) => void;
  const promise = new Promise<Response>(done => { resolve = done; });
  return { promise, resolve };
}

test("an expired mutation cannot refresh or replay after switching accounts", async () => {
  const response = deferredResponse();
  const requests: RequestInit[] = [];
  setAccessToken("account-a-fixture");
  globalThis.fetch = async (_input, options) => { requests.push(options!); return response.promise; };
  const pending = api("/me", { method: "PATCH", body: '{"bio":"A draft"}' });
  const rejected = expect(pending).rejects.toMatchObject({ code: "SESSION_CHANGED" });
  setAccessToken("account-b-fixture");
  response.resolve(Response.json({ detail: "Expired" }, { status: 401 }));
  await rejected;
  expect(requests).toHaveLength(1);
  expect(new Headers(requests[0].headers).get("Authorization")).toBe("Bearer account-a-fixture");
});

test("switching accounts during refresh cannot replay a mutation", async () => {
  const refresh = deferredResponse();
  const started = deferredResponse();
  const paths: string[] = [];
  setAccessToken("account-a-fixture");
  globalThis.fetch = async input => {
    paths.push(String(input));
    if (String(input).endsWith("/auth/refresh")) {
      started.resolve(new Response());
      return refresh.promise;
    }
    return Response.json({ detail: "Expired" }, { status: 401 });
  };
  const pending = api("/me", { method: "PATCH", body: '{"bio":"A draft"}' });
  const rejected = expect(pending).rejects.toMatchObject({ code: "SESSION_CHANGED" });
  await started.promise;
  setAccessToken("account-b-fixture");
  refresh.resolve(Response.json({ access_token: "account-a-refreshed-fixture" }));
  await rejected;
  expect(paths).toEqual(["/api/v1/me", "/api/v1/auth/refresh"]);
  globalThis.fetch = async (_input, options) => {
    expect(new Headers(options?.headers).get("Authorization")).toBe("Bearer account-b-fixture");
    return Response.json({ id: "b" });
  };
  await expect(api("/me")).resolves.toEqual({ id: "b" });
});

test("the same login can refresh and retry a mutation once", async () => {
  const headers: string[] = [];
  setAccessToken("account-a-fixture");
  globalThis.fetch = async (input, options) => {
    if (String(input).endsWith("/auth/refresh")) return Response.json({ access_token: "account-a-refreshed-fixture" });
    headers.push(new Headers(options?.headers).get("Authorization")!);
    return headers.length === 1 ? Response.json({}, { status: 401 }) : Response.json({ saved: true });
  };
  await expect(api("/me", { method: "PATCH", body: '{"bio":"A draft"}' })).resolves.toEqual({ saved: true });
  expect(headers).toEqual(["Bearer account-a-fixture", "Bearer account-a-refreshed-fixture"]);
});

test("logging out while a request is in flight cannot refresh the session", async () => {
  const response = deferredResponse();
  let calls = 0;
  setAccessToken("account-a-fixture");
  globalThis.fetch = async () => { calls++; return response.promise; };
  const pending = api("/me", { method: "PATCH", body: '{"bio":"A draft"}' });
  const rejected = expect(pending).rejects.toMatchObject({ code: "SESSION_CHANGED" });
  setAccessToken(null);
  response.resolve(Response.json({}, { status: 401 }));
  await rejected;
  expect(calls).toBe(1);
});
