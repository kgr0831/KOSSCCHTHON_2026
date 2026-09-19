import { NextResponse } from "next/server";

// Runtime origin: one Docker image works with the actual deployed site hostname.
export function proxy() {
  const response = NextResponse.next();
  const siteOrigin = process.env.DUDRI_SITE_ORIGIN || "http://127.0.0.1:8001";
  response.headers.set("Content-Security-Policy", `frame-src 'self' ${siteOrigin}; object-src 'none'; base-uri 'self'`);
  return response;
}

export const config = { matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"] };
