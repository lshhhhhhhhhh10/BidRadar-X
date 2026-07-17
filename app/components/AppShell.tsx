import type { ReactNode } from "react";

import { WorkspaceSidebar } from "./WorkspaceSidebar";


export function AppShell({ active, children }: { active: string; children: ReactNode }) {
  return (
    <div className="app-shell">
      <WorkspaceSidebar active={active} />
      <div className="app-shell-content">
        <main>{children}</main>
      </div>
    </div>
  );
}
