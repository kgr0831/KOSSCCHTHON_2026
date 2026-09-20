"use client";

import { QueryClient, QueryClientProvider, useQuery, useQueryClient } from "@tanstack/react-query";
import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { NavigationProvider } from "./app-navigation";
import { FeedbackProvider } from "./feedback";
import { api, ApiError, refreshSession, setAccessToken, setSessionIdentity, type UserSelf } from "@/lib/api";

const AuthContext = createContext<{ user?: UserSelf; ready: boolean; connectionError: string; reconnect: () => void; login: (token: string) => Promise<void>; logout: () => Promise<void> }>({ ready: false, connectionError: "", reconnect: () => {}, login: async () => {}, logout: async () => {} });
export const useAuth = () => useContext(AuthContext);

function realtimeEndpoint() {
  const configuredOrigin = process.env.NEXT_PUBLIC_SELF_HOSTED === "1"
    ? window.location.origin
    : process.env.NEXT_PUBLIC_WS_ORIGIN;
  try {
    const endpoint = new URL("/api/v1/realtime", configuredOrigin || window.location.origin);
    endpoint.protocol = endpoint.protocol === "https:" ? "wss:" : "ws:";
    return endpoint.toString();
  } catch {
    const scheme = window.location.protocol === "https:" ? "wss" : "ws";
    return `${scheme}://${window.location.host}/api/v1/realtime`;
  }
}

function useRealtime(userId: string | undefined) {
  const client = useQueryClient();
  useEffect(() => {
    if (!userId) return;
    let stopped = false, socket: WebSocket | null = null, retry: number | undefined, heartbeat: number | undefined, delay = 500;
    const seen = new Set<string>();
    const clearRetry = () => { if (retry !== undefined) window.clearTimeout(retry); retry = undefined; };
    const clearHeartbeat = () => { if (heartbeat !== undefined) window.clearInterval(heartbeat); heartbeat = undefined; };
    const schedule = () => { if (!stopped) { retry = window.setTimeout(() => { void connect(); }, delay); delay = Math.min(delay * 2, 10_000); } };
    const connect = async () => {
      clearRetry();
      try {
        // A short-lived ticket is fetched with the existing Bearer session.
        // WebSocket itself receives it as a subprotocol, never in its URL.
        const ticket = await api<{ token: string }>("/realtime/tickets", { method: "POST" });
        if (stopped) return;
        const current = new WebSocket(realtimeEndpoint(), ["dudri", ticket.token]);
        socket = current;
        current.onopen = () => {
          if (stopped || socket !== current) { current.close(); return; }
          delay = 500;
          clearHeartbeat();
          heartbeat = window.setInterval(() => { if (current.readyState === WebSocket.OPEN) current.send("ping"); }, 25_000);
        };
        current.onmessage = event => {
          if (socket !== current) return;
          let message: { type?: string; id?: string };
          try { message = JSON.parse(event.data); } catch { return; }
          // `ready` only confirms the socket is open. The account queries were
          // just fetched to obtain the ticket, so refetching all of them here
          // causes an avoidable second burst on every page load/reconnect.
          if (message.type === "ready") return;
          if (message.type !== "event" || !message.id || seen.has(message.id)) return;
          seen.add(message.id);
          if (seen.size > 500) seen.delete(seen.values().next().value!);
          // Events are opaque invalidations; data always comes back through
          // the ordinary authorized query that owns its permissions.
          void client.invalidateQueries();
        };
        current.onerror = () => current.close();
        current.onclose = () => {
          if (socket !== current) return;
          socket = null;
          clearHeartbeat();
          schedule();
        };
      } catch { schedule(); }
    };
    void connect();
    return () => { stopped = true; clearRetry(); clearHeartbeat(); const current = socket; socket = null; current?.close(); };
  }, [client, userId]);
}

function SessionProvider({ children }: { children: React.ReactNode }) {
  const client = useQueryClient();
  const [ready, setReady] = useState(false);
  const [authenticated, setAuthenticated] = useState(false);
  const [connectionError, setConnectionError] = useState("");
  const [reconnectAttempt, setReconnectAttempt] = useState(0);
  const epoch = useRef(0);
  useEffect(() => {
    let active = true;
    const generation = epoch.current;
    refreshSession().then(async ok => {
      if (!active || generation !== epoch.current) return;
      // Finish identity refresh before enabling any cached account queries.
      await client.cancelQueries();
      if (!active || generation !== epoch.current) return;
      client.clear();
      if (ok) {
        const identity = await api<UserSelf>("/me", {}, false);
        if (!active || generation !== epoch.current) return;
        client.setQueryData(["me"], identity);
        setSessionIdentity(identity.id);
      }
      setAuthenticated(ok); setConnectionError(""); setReady(true);
    }).catch(error => {
      if (active && generation === epoch.current) { setConnectionError(error.message); setReady(true); }
    });
    return () => { active = false; };
  }, [client, reconnectAttempt]);
  const me = useQuery({ queryKey: ["me"], queryFn: () => api<UserSelf>("/me"), enabled: ready && authenticated, retry: false });
  useRealtime(ready && authenticated ? me.data?.id : undefined);
  const login = useCallback(async (token: string) => { epoch.current++; client.clear(); setAccessToken(token); setAuthenticated(true); setReady(true); const identity = await client.fetchQuery({ queryKey: ["me"], queryFn: () => api<UserSelf>("/me") }); setSessionIdentity(identity.id); setConnectionError(""); }, [client]);
  const logout = useCallback(async () => { epoch.current++; await api("/auth/logout", { method: "POST" }); setAccessToken(null); client.clear(); setAuthenticated(false); setReady(true); }, [client]);
  const reconnect = useCallback(() => { epoch.current++; setReady(false); setAuthenticated(false); setReconnectAttempt(attempt => attempt + 1); }, []);
  useEffect(() => { const changed = () => { client.clear(); reconnect(); }; window.addEventListener("dudri:session-changed", changed); return () => window.removeEventListener("dudri:session-changed", changed); }, [client, reconnect]);
  return <AuthContext.Provider value={{ user: ready && authenticated ? me.data : undefined, ready: ready && (!authenticated || !me.isPending), connectionError: connectionError || (me.error?.message ?? ""), reconnect, login, logout }}>{children}</AuthContext.Provider>;
}

export default function Providers({ children }: { children: React.ReactNode }) {
  const [client] = useState(() => new QueryClient({ defaultOptions: { queries: { staleTime: 30_000, retry: (attempt, error) => error instanceof ApiError && error.status < 500 ? false : attempt < 1, refetchOnWindowFocus: true } } }));
  return <QueryClientProvider client={client}><SessionProvider><FeedbackProvider><NavigationProvider>{children}</NavigationProvider></FeedbackProvider></SessionProvider></QueryClientProvider>;
}
