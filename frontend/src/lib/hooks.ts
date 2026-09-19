"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useRef, useState, type SetStateAction } from "react";
import { api, jsonBody } from "./api";
import { useAppNavigation } from "@/components/app-navigation";

export function useCommand<T = unknown>() {
  const client = useQueryClient();
  const retryKeys = useRef(new Map<string, string>());
  return useMutation({
    mutationFn: ({ path, body, method = "POST", idempotent = false }: { path: string; body?: unknown; method?: string; idempotent?: boolean }) => {
      const fingerprint = `${method}:${path}:${jsonBody(body)}`;
      if (!retryKeys.current.has(fingerprint)) retryKeys.current.set(fingerprint, crypto.randomUUID());
      return api<T>(path, { method, body: body === undefined ? undefined : jsonBody(body), headers: idempotent ? { "Idempotency-Key": retryKeys.current.get(fingerprint)! } : undefined });
    },
    onSuccess: async () => { await client.invalidateQueries(); },
  });
}

export function useUnsavedChanges(dirty: boolean) {
  const { registerBlocker } = useAppNavigation();
  useEffect(() => registerBlocker(() => dirty), [dirty, registerBlocker]);
}

// Same-tab drafts survive refresh without a native browser beforeunload prompt.
export function useSessionDraft<T>(key: string) {
  const storageKey = `dudri.draft.${key}`;
  const [draft, setDraft] = useState<T | null>(() => { try { return JSON.parse(sessionStorage.getItem(storageKey) || "null"); } catch { return null; } });
  const set = useCallback((value: SetStateAction<T | null>) => setDraft(previous => {
    const next = typeof value === "function" ? (value as (previous: T | null) => T | null)(previous) : value;
    try { if (next === null) sessionStorage.removeItem(storageKey); else sessionStorage.setItem(storageKey, JSON.stringify(next)); } catch {}
    return next;
  }), [storageKey]);
  return [draft, set] as const;
}
