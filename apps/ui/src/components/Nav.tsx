"use client";

/** Sidebar navigation for the platform UI. */

import Link from "next/link";
import { usePathname } from "next/navigation";

const LINKS = [
  { href: "/", label: "仪表盘" },
  { href: "/chat", label: "对话调试" },
  { href: "/agents", label: "Agent 管理" },
  { href: "/sessions", label: "会话" },
  { href: "/monitoring", label: "监控" },
  { href: "/settings", label: "设置" },
];

export default function Nav() {
  const pathname = usePathname();
  return (
    <nav className="w-52 shrink-0 border-r border-zinc-800 bg-zinc-950 p-4 flex flex-col gap-1">
      <div className="mb-4 px-2">
        <div className="text-lg font-bold tracking-tight text-zinc-50">fakzed</div>
        <div className="text-xs text-zinc-500">Agent 平台控制台</div>
      </div>
      {LINKS.map((link) => {
        const active =
          link.href === "/" ? pathname === "/" : pathname.startsWith(link.href);
        return (
          <Link
            key={link.href}
            href={link.href}
            className={`rounded-md px-3 py-2 text-sm transition-colors ${
              active
                ? "bg-zinc-800 text-zinc-50"
                : "text-zinc-400 hover:bg-zinc-900 hover:text-zinc-200"
            }`}
          >
            {link.label}
          </Link>
        );
      })}
    </nav>
  );
}
