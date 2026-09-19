"use client";

import { createContext, lazy, Suspense, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { useFeedback } from "./feedback";
import { usePathname as useEntryPath } from "next/navigation";

const screens = {
  "/": lazy(() => import("@/app/page")),
  "/explore": lazy(() => import("@/app/explore/page")),
  "/my": lazy(() => import("@/app/my/page")),
  "/profile": lazy(() => import("@/app/profile/page")),
  "/studio": lazy(() => import("@/app/studio/page")),
  "/materials": lazy(() => import("@/app/materials/page")),
  "/pricing": lazy(() => import("@/app/pricing/page")),
  "/career": lazy(() => import("@/app/career/page")),
  "/settings/ai": lazy(() => import("@/app/settings/ai/page")),
  "/notifications": lazy(() => import("@/app/notifications/page")),
  "/coffee": lazy(() => import("@/app/coffee/page")),
  "/coffee/new": lazy(() => import("@/app/coffee/new/page")),
  "/coffee/:id": lazy(() => import("@/app/coffee/[id]/page")),
  "/bookings/:id": lazy(() => import("@/app/bookings/[id]/page")),
  "/users/:id": lazy(() => import("@/app/users/[id]/page")),
  "/projects": lazy(() => import("@/app/projects/page")),
  "/projects/new": lazy(() => import("@/app/projects/new/page")),
  "/projects/:id": lazy(() => import("@/app/projects/[id]/page")),
  "/auth/callback": lazy(() => import("@/app/auth/callback/page")),
  "/auth/confirm": lazy(() => import("@/app/auth/confirm/page")),
  "/github/callback": lazy(() => import("@/app/github/callback/page")),
};
const sensitiveCallbackPaths = new Set(["/auth/confirm", "/auth/callback", "/github/callback"]);
function screenKey(path: string) { return path in screens ? path as keyof typeof screens : path.replace(/\/(users|coffee|bookings|projects)\/[^/]+$/, "/$1/:id") as keyof typeof screens; }
function normalize(href: string) {
  const url = new URL(href, window.location.origin);
  if (url.origin !== window.location.origin) return null;
  if (url.pathname === "/projects/requests") return "/projects#requests";
  if (url.pathname === "/auth") return "/auth";
  if (!screens[screenKey(url.pathname)]) return null;
  // Authentication fragments must never be persisted to app history or storage.
  if (sensitiveCallbackPaths.has(url.pathname)) return url.pathname;
  return url.pathname + url.search + url.hash;
}
type Options = { scroll?: boolean };
type Navigation = { route: string; ready: boolean; authOpen: boolean; closeAuth: () => void; finishLogin: () => void; registerBlocker: (blocker: () => boolean) => () => void; push: (href: string, options?: Options) => void; replace: (href: string, options?: Options) => void };
const Context = createContext<Navigation | null>(null);
export function useAppNavigation() { const value = useContext(Context); if (!value) throw new Error("App navigation is unavailable"); return value; }
export function usePathname() { return useAppNavigation().route.split(/[?#]/)[0]; }
export function useSearchParams() { const { route } = useAppNavigation(); return useMemo(() => new URLSearchParams(route.split("?")[1]?.split("#")[0] || ""), [route]); }
export function useParams<T extends Record<string, string>>() { const path = usePathname(); return { id: decodeURIComponent(path.split("/")[2] || "") } as unknown as T; }
export function useRouter() { const { push, replace } = useAppNavigation(); return useMemo(() => ({ push, replace }), [push, replace]); }

export function NavigationProvider({ children }: { children: React.ReactNode }) {
  const entry = useEntryPath();
  const feedback = useFeedback(), blockers = useRef(new Set<() => boolean>());
  const registerBlocker = useCallback((blocker: () => boolean) => { blockers.current.add(blocker); return () => { blockers.current.delete(blocker); }; }, []);
  const canLeave = useCallback(async () => ![...blockers.current].some(block => block()) || await feedback({ title: "저장하지 않은 변경이 있어요", message: "화면을 이동하기 전에 새 버전 또는 프로필 저장을 눌러 주세요. 지금 이동할까요?", confirmLabel: "이동하기", cancelLabel: "계속 편집" }), [feedback]);
  const [route, setRoute] = useState(entry === "/auth" ? "/" : entry);
  const currentRoute = useRef(route);
  const initialized = useRef(false);
  currentRoute.current = route;
  const [ready, setReady] = useState(false), [authOpen, setAuthOpen] = useState(false);
  useEffect(() => {
    if (!initialized.current) {
      initialized.current = true;
      const confirm = sensitiveCallbackPaths.has(window.location.pathname);
      const initial = normalize(window.history.state?.dudriView || window.location.href) || "/";
      setRoute(initial === "/auth" ? "/" : initial); setAuthOpen(initial === "/auth"); setReady(true);
      if (!confirm) window.history.replaceState({ ...window.history.state, dudriView: initial === "/auth" ? "/" : initial }, "", "/");
    }
    const back = async () => {
      const next = normalize(window.history.state?.dudriView || window.location.href) || "/";
      if (!await canLeave()) { window.history.pushState({ ...window.history.state, dudriView: currentRoute.current }, "", "/"); return; }
      setRoute(next === "/auth" ? "/" : next); setAuthOpen(false);
    };
    window.addEventListener("popstate", back);
    return () => window.removeEventListener("popstate", back);
  }, [canLeave]);
  const navigate = useCallback(async (href: string, replace: boolean, options?: Options) => {
    const next = normalize(href);
    if (!next) return;
    if (next === "/auth") {
      try { sessionStorage.setItem("dudri.authReturn", sensitiveCallbackPaths.has(route) ? "/profile" : route); } catch {}
      setAuthOpen(true); return;
    }
    if (next === route) return;
    if (next.split("#")[0] !== route.split("#")[0] && !await canLeave()) return;
    setAuthOpen(false);
    window.history[replace ? "replaceState" : "pushState"]({ ...window.history.state, dudriView: next }, "", "/");
    setRoute(next);
    if (options?.scroll !== false && next.split(/[?#]/)[0] !== route.split(/[?#]/)[0]) window.scrollTo({ top: 0, behavior: "instant" });
  }, [route, canLeave]);
  const push = useCallback((href: string, options?: Options) => navigate(href, false, options), [navigate]);
  const replace = useCallback((href: string, options?: Options) => navigate(href, true, options), [navigate]);
  const closeAuth = useCallback(() => setAuthOpen(false), []);
  const finishLogin = useCallback(() => {
    setAuthOpen(false);
    if (sensitiveCallbackPaths.has(route)) {
      let destination = "/profile";
      try { destination = normalize(sessionStorage.getItem("dudri.authReturn") || "/profile") || "/profile"; sessionStorage.removeItem("dudri.authReturn"); } catch {}
      replace(sensitiveCallbackPaths.has(destination) || destination === "/auth" ? "/profile" : destination);
    }
  }, [route, replace]);
  useEffect(() => {
    const hash = route.split("#")[1];
    if (!hash || route.startsWith("/auth/")) return;
    const find = () => { const target = document.getElementById(hash); if (!target) return false; target.scrollIntoView({ block: "start" }); return true; };
    if (find()) return;
    const observer = new MutationObserver(() => { if (find()) observer.disconnect(); });
    observer.observe(document.body, { childList: true, subtree: true });
    const timeout = setTimeout(() => observer.disconnect(), 15_000);
    return () => { observer.disconnect(); clearTimeout(timeout); };
  }, [route, authOpen]);
  return <Context.Provider value={{ route, ready, authOpen, closeAuth, finishLogin, registerBlocker, push, replace }}><div className="app-navigation" onClickCapture={event => {
    if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    const anchor = (event.target as Element).closest<HTMLAnchorElement>("a[href]");
    if (!anchor || anchor.target || anchor.hasAttribute("download")) return;
    if (anchor.getAttribute("href")?.startsWith("#")) { event.preventDefault(); push(route.split("#")[0] + anchor.getAttribute("href")); return; }
    if (sensitiveCallbackPaths.has(new URL(anchor.href).pathname)) return;
    if (normalize(anchor.href)) { event.preventDefault(); push(anchor.href); }
  }}>{children}</div></Context.Provider>;
}

export function AppOutlet({ fallback }: { fallback: React.ReactNode }) {
  const { ready } = useAppNavigation(), path = usePathname();
  const Screen = screens[screenKey(path)];
  if (!ready) return <div className="loading" role="status">화면을 준비하고 있어요</div>;
  return <div key={path} className="app-view"><Suspense fallback={<div className="loading" role="status">불러오는 중이에요</div>}>{Screen ? <Screen /> : fallback}</Suspense></div>;
}
