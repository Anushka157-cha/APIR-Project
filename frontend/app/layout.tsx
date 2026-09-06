import "./globals.css";
import type { ReactNode } from "react";
import { Nav } from "@/components/Nav";

export const metadata = {
  title: "APIR — Incident Resolver",
  description: "Autonomous Production Incident Resolver",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-panel">
        <Nav />
        <main className="mx-auto max-w-7xl px-6 py-6">{children}</main>
      </body>
    </html>
  );
}
