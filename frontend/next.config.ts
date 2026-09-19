import type { NextConfig } from "next";

const selfHosted = process.env.NEXT_PUBLIC_SELF_HOSTED === "1";
const apiOrigin = selfHosted ? "http://127.0.0.1:8000" : process.env.API_ORIGIN || "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  agentRules: false,
  devIndicators: false,
  output: "standalone",
  // A Vercel frontend reaches the separately hosted API directly. The
  // self-hosted image instead keeps its browser socket same-origin and its
  // custom Node server upgrades only the realtime route to the loopback API.
  env: {
    NEXT_PUBLIC_SELF_HOSTED: selfHosted ? "1" : "0",
    NEXT_PUBLIC_WS_ORIGIN: selfHosted ? "" : apiOrigin,
  },
  experimental: { proxyTimeout: 210_000 },
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${apiOrigin}/api/:path*` }];
  },
  async headers() {
    return [{ source: "/:path*", headers: [
      { key: "Referrer-Policy", value: "no-referrer" },
      { key: "X-Content-Type-Options", value: "nosniff" },
      { key: "Permissions-Policy", value: "camera=(self), geolocation=(self), microphone=()" },
    ] }];
  },
};
export default nextConfig;
