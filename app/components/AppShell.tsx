"use client";

import Link from "next/link";
import type { ReactNode } from "react";


export function AppShell({ active, children }: { active: string; children: ReactNode }) {
  const links = [
    ["workbench", "/", "情报任务"],
    ["projects", "/projects", "项目事件"],
    ["reports", "/reports", "报告与记忆"],
  ];
  return (
    <div className="app-shell">
      <header className="topbar">
        <Link className="brand" href="/">
          <span className="brand-mark">E</span>
          <span>
            <strong>循证标讯</strong>
            <small>TENDER INTELLIGENCE</small>
          </span>
        </Link>
        <nav aria-label="主要页面">
          {links.map(([id, href, label]) => (
            <Link className={active === id ? "nav-link active" : "nav-link"} href={href} key={id}>
              {label}
            </Link>
          ))}
        </nav>
        <span className="local-badge">LOCAL · 仅本机</span>
      </header>
      <main>{children}</main>
    </div>
  );
}
