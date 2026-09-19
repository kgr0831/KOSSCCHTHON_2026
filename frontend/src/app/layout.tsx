import type { Metadata, Viewport } from "next";
import Providers from "@/components/providers";
import Shell from "@/components/shell";
import "./globals.css";
import "./app-ui.css";

export const metadata: Metadata = { title: { default: "두드리 — 다음 가능성을 두드리다", template: "%s · 두드리" }, description: "같은 학교, 서로 다른 경험. 동문과 나누는 커피챗부터 함께 만드는 첫 프로젝트까지." };
export const viewport: Viewport = { width: "device-width", initialScale: 1, viewportFit: "cover", interactiveWidget: "resizes-content" };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return <html lang="ko"><body><a href="#main" className="skip-link">본문으로 이동</a><Providers><Shell>{children}</Shell></Providers></body></html>;
}
