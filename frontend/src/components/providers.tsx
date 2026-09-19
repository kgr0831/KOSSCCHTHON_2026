"use client";

import { QueryClient, QueryClientProvider, useQuery, useQueryClient } from "@tanstack/react-query";
import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { NavigationProvider } from "./app-navigation";
import { FeedbackProvider } from "./feedback";
import { api, ApiError, refreshSession, setAccessToken, setSessionIdentity, type UserSelf } from "@/lib/api";

const AuthContext = createContext<{ user?: UserSelf; ready: boolean; connectionError: string; reconnect: () => void; login: (token: string) => Promise<void>; logout: () => Promise<void> }>({ ready: false, connectionError: "", reconnect: () => {}, login: async () => {}, logout: async () => {} });
export const useAuth = () => useContext(AuthContext);

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
