"use client";

import { useEffect, useRef, useState } from "react";
import { authorizedFetch } from "@/lib/api";

type Props = {
  src?: string | null;
  name: string;
  className?: string;
  /** Fetch app-owned private assets with the in-memory Bearer session. */
  privateAccess?: boolean;
};

export function Avatar({ src, name, className = "avatar", privateAccess = false }: Props) {
  const [loaded, setLoaded] = useState<{ src: string; url: string } | null>(null);
  const [failed, setFailed] = useState(false);
  const loadedUrl = useRef<string | null>(null);
  const protectedAsset = !!src?.startsWith("/api/") && privateAccess;
  useEffect(() => {
    setFailed(false);
    if (loadedUrl.current) { URL.revokeObjectURL(loadedUrl.current); loadedUrl.current = null; }
    setLoaded(null);
    if (!protectedAsset || !src) return;
    const controller = new AbortController();
    let active = true;
    void authorizedFetch(src, { signal: controller.signal }).then(async response => {
      if (!response.ok) throw new Error("avatar unavailable");
      const url = URL.createObjectURL(await response.blob());
      if (!active) { URL.revokeObjectURL(url); return; }
      loadedUrl.current = url;
      setLoaded({ src, url });
    }).catch(() => { if (!controller.signal.aborted) setFailed(true); });
    return () => { active = false; controller.abort(); };
  }, [protectedAsset, src]);
  useEffect(() => () => { if (loadedUrl.current) URL.revokeObjectURL(loadedUrl.current); }, []);
  // Never reuse a private blob URL for a different API source while its fetch
  // is still in flight (for example during an account switch).
  const image = protectedAsset ? (loaded && loaded.src === src ? loaded.url : null) : src;
  return <div className={className}>{image && !failed ? <img src={image} alt="" onError={() => setFailed(true)} style={{ width: "100%", height: "100%", objectFit: "cover", borderRadius: "inherit" }} /> : name.slice(0, 1)}</div>;
}
