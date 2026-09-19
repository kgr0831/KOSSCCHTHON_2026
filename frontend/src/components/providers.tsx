"use client";

import { QueryClient, QueryClientProvider, useQuery, useQueryClient } from "@tanstack/react-query";
import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { NavigationProvider } from "./app-navigation";
import { FeedbackProvider } from "./feedback";
import { api, ApiError, refreshSession, setAccessToken, type UserSelf } from "@/lib/api";

const AuthContext = createContext<{ user?: UserSelf; ready: boolean; login: (token: string) => Promise<void>; logout: () => Promise<void> }>({ ready: false, login: async () => {}, logout: async () => {} });
export const useAuth = () => useContext(AuthContext);

function SessionProvider({ children }: { children: React.ReactNode }) {
  const client = useQueryClient();
  const [ready, setReady] = useState(false);
  const [authenticated, setAuthenticated] = useState(false);
  const epoch = useRef(0);
  useEffect(() => { let active = true; const generation = epoch.current; refreshSession().then(ok => { if (active && generation === epoch.current) { setAuthenticated(ok); setReady(true); } }); return () => { active = false; }; }, []);
  const me = useQuery({ queryKey: ["me"], queryFn: () => api<UserSelf>("/me"), enabled: ready && authenticated, retry: false });
  const login = useCallback(async (token: string) => { epoch.current++; client.clear(); setAccessToken(token); setAuthenticated(true); setReady(true); await client.fetchQuery({ queryKey: ["me"], queryFn: () => api<UserSelf>("/me") }); }, [client]);
  const logout = useCallback(async () => { epoch.current++; await api("/auth/logout", { method: "POST" }); setAccessToken(null); client.clear(); setAuthenticated(false); setReady(true); }, [client]);
  return <AuthContext.Provider value={{ user: me.data, ready: ready && (!authenticated || !me.isPending), login, logout }}>{children}</AuthContext.Provider>;
}

export default function Providers({ children }: { children: React.ReactNode }) {
  const [client] = useState(() => new QueryClient({ defaultOptions: { queries: { staleTime: 30_000, retry: (attempt, error) => error instanceof ApiError && error.status < 500 ? false : attempt < 1, refetchOnWindowFocus: true } } }));
  return <QueryClientProvider client={client}><SessionProvider><FeedbackProvider><NavigationProvider>{children}</NavigationProvider></FeedbackProvider></SessionProvider></QueryClientProvider>;
}
