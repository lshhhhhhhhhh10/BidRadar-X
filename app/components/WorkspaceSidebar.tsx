"use client";

import Link from "next/link";

const NAV_ITEMS = [
  { id: "workbench", href: "/", icon: "⌕", label: "检索" },
  { id: "reports", href: "/reports", icon: "▤", label: "项目报告" },
  { id: "interfaces", href: "/interfaces", icon: "⌘", label: "接口" },
];

export function WorkspaceSidebar({ active }: { active: string }) {
  return (
    <aside className="workspace-sidebar" aria-label="工作台导航">
      <nav>
        {NAV_ITEMS.map((item) => (
          <Link
            className={active === item.id ? "workspace-nav-item is-active" : "workspace-nav-item"}
            href={item.href}
            key={item.id}
          >
            <span aria-hidden="true">{item.icon}</span>
            <small>{item.label}</small>
          </Link>
        ))}
      </nav>
      <div className="workspace-account" aria-label="当前本地用户">
        <span>LS</span>
        <small>本地</small>
      </div>
    </aside>
  );
}
