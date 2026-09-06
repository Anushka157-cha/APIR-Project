"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";

const links = [
  ["/dashboard", "Overview"],
  ["/incidents", "Incidents"],
  ["/incidents/compare", "Compare"],
  ["/services", "Service map"],
  ["/failure-injection", "Failure injection"],
  ["/replay", "Replay"],
  ["/evaluation", "Evaluation"],
];

export function Nav() {
  const path = usePathname();
  const router = useRouter();
  if (path === "/login") return null;
  return (
    <header className="border-b border-line bg-card">
      <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-3">
        <div className="flex items-center gap-3">
          <span className="rounded bg-accent/20 px-2 py-1 font-mono text-sm text-accent">APIR</span>
          <span className="text-sm text-neutral-400">Production incident resolver</span>
        </div>
        <nav className="flex gap-4 text-sm">
          {links.map(([href, label]) => (
            <Link
              key={href}
              href={href}
              className={path.startsWith(href) ? "text-accent" : "text-neutral-400 hover:text-white"}
            >
              {label}
            </Link>
          ))}
          <button
            className="text-neutral-500"
            onClick={() => {
              localStorage.removeItem("apir_token");
              router.push("/login");
            }}
          >
            Sign out
          </button>
        </nav>
      </div>
    </header>
  );
}
